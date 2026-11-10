from __future__ import annotations

import io
import json
import time
import uuid
from email.message import Message
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlencode, urlsplit
from urllib.request import urlopen

import pytest

from colin_colab_remote.google_mcp import GoogleColabProvider, ProviderError
from colin_colab_remote.oauth import COLAB_SCOPE, GoogleOAuth


class Response(io.BytesIO):
    def __init__(self, payload, content_type="application/json"):
        data = payload if isinstance(payload, bytes) else json.dumps(payload).encode("utf-8")
        super().__init__(data)
        self.headers = {"Content-Type": content_type}


class FakeOpener:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def open(self, request, *, timeout):
        self.requests.append((request, timeout))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class FakeOAuth:
    def __init__(self):
        self.refreshes = []

    def access_token(self, *, force_refresh=False):
        self.refreshes.append(force_refresh)
        return "synthetic-new-token" if force_refresh else "synthetic-token"


def tool(value):
    return Response({"jsonrpc": "2.0", "id": 1, "result": {"structuredContent": value}})


def error(status, details=None):
    return HTTPError("https://colaboratory.googleapis.com/mcp", status, "synthetic token must not appear",
                     Message(), io.BytesIO(json.dumps(details or {}).encode("utf-8")))


def provider(tmp_path, responses):
    result = GoogleColabProvider(tmp_path)
    result.oauth = FakeOAuth()
    result._opener = FakeOpener(responses)
    return result


def desktop_client(tmp_path, **changes):
    installed = {"client_id": "synthetic.apps.googleusercontent.com", "client_secret": "synthetic-secret"}
    installed.update(changes)
    path = tmp_path / "client.json"
    path.write_text(json.dumps({"installed": installed}), encoding="utf-8")
    return path


def authorized(oauth, **changes):
    with oauth._locked():
        record = oauth._read()
        record.update(refresh_token="synthetic-refresh", access_token="synthetic-access",
                      expires_at=time.time() + 3600, subject="subject-a", email="test@example.invalid")
        record.update(changes)
        oauth._write(record)


def test_list_values_decode_structured_and_text_results(tmp_path):
    specs = [{"key": {"variant": "VARIANT_GPU", "accelerator": "T4", "shape": "SHAPE_STANDARD"}, "eligible": True}]
    p = provider(tmp_path, [tool({"runtimeSpecs": specs}), Response({"result": {"content": [
        {"type": "text", "text": json.dumps({"runtimes": [{"name": "runtimes/owned-a"}]})}
    ]}})])
    assert p.list_runtime_specs() == specs
    assert p.list_runtimes() == [{"name": "runtimes/owned-a"}]
    assert [json.loads(req.data)["params"]["name"] for req, _ in p._opener.requests] == ["list_runtime_specs", "list_runtimes"]


def test_create_keeps_stable_request_and_eligible_spec(tmp_path):
    runtime = {"name": "runtimes/owned-a"}
    p = provider(tmp_path, [tool(runtime)])
    request_id = str(uuid.uuid4())
    spec = {"variant": "VARIANT_GPU", "accelerator": "T4", "shape": "SHAPE_STANDARD"}
    assert p.create_runtime("owned-a", request_id, {"key": spec, "eligible": True}) == runtime
    arguments = json.loads(p._opener.requests[0][0].data)["params"]["arguments"]
    assert arguments == {"runtimeId": "owned-a", "requestId": request_id, "runtime": {"runtimeSpec": spec}}


def test_create_rejects_unstable_or_wrong_runtime_without_duplicate(tmp_path):
    p = provider(tmp_path, [tool({"name": "runtimes/someone-else"})])
    spec = {"variant": "VARIANT_GPU", "accelerator": "T4", "shape": "SHAPE_STANDARD"}
    with pytest.raises(ProviderError) as caught:
        p.create_runtime("owned-a", "", spec)
    assert caught.value.code == "invalid_request"
    assert p._opener.requests == []
    with pytest.raises(ProviderError) as caught:
        p.create_runtime("owned-a", str(uuid.uuid4()), spec)
    assert caught.value.code == "provider_error"
    assert len(p._opener.requests) == 1


def test_operation_result_is_polled_and_bound_to_requested_runtime(tmp_path, monkeypatch):
    monkeypatch.setattr("colin_colab_remote.google_mcp.time.sleep", lambda _: None)
    p = provider(tmp_path, [tool({"name": "operations/allocation-a", "done": False}),
                            Response({"done": True, "response": {"name": "runtimes/owned-a"}})])
    spec = {"variant": "VARIANT_CPU", "accelerator": "NONE", "shape": "SHAPE_STANDARD"}
    assert p.create_runtime("owned-a", str(uuid.uuid4()), spec)["name"] == "runtimes/owned-a"
    assert p._opener.requests[1][0].full_url.endswith("/v1/operations/allocation-a")
    p = provider(tmp_path, [tool({"done": True, "response": {"name": "runtimes/wrong-a"}})])
    with pytest.raises(ProviderError) as caught:
        p.create_runtime("owned-a", str(uuid.uuid4()), spec)
    assert caught.value.code == "provider_error"


def test_sse_progress_and_terminal_unicode_result(tmp_path):
    chunks = [
        {"jsonrpc": "2.0", "method": "notifications/progress", "params": {"message": "Đang tải model"}},
        {"jsonrpc": "2.0", "id": "result", "result": {"structuredContent": {"stdout": "Sẵn sàng\n", "session": "runtimes/owned-a/sessions/worker-a"}}},
    ]
    stream = "".join("event: message\ndata: " + json.dumps(item, ensure_ascii=False) + "\n\n" for item in chunks).encode("utf-8")
    p = provider(tmp_path, [Response(stream, "text/event-stream")])
    progress = []
    p.on_progress = progress.append
    execution_id = str(uuid.uuid4())
    assert p.execute("print('Sẵn sàng')", "runtimes/owned-a/sessions/worker-a", execution_id)["stdout"] == "Sẵn sàng\n"
    assert len(progress) == 1
    call = json.loads(p._opener.requests[0][0].data)
    assert call["params"]["arguments"]["executionId"] == execution_id
    assert call["params"]["_meta"]["progressToken"]


def test_incomplete_stream_and_python_failure_are_not_success(tmp_path):
    p = provider(tmp_path, [Response(b": ping\n\n", "text/event-stream"),
                            tool({"executionError": {"name": "ValueError", "value": "synthetic-secret"}})])
    for expected in ("timeout", "execution_error"):
        with pytest.raises(ProviderError) as caught:
            p.execute("pass", "runtimes/owned-a/sessions/worker-a", str(uuid.uuid4()))
        assert caught.value.code == expected
        assert "synthetic-secret" not in str(caught.value)


@pytest.mark.parametrize("status,detail,expected", [
    (429, {}, "quota"),
    (503, {}, "unavailable"),
    (403, {"error": {"details": [{"reason": "SERVICE_DISABLED"}]}}, "setup_required"),
    (403, {}, "permission_denied"),
    (404, {}, "not_found"),
])
def test_http_errors_are_categorized_and_redacted(tmp_path, status, detail, expected):
    p = provider(tmp_path, [error(status, detail)])
    with pytest.raises(ProviderError) as caught:
        p.get_subscription()
    assert caught.value.code == expected
    assert "synthetic" not in str(caught.value)
    assert "https://" not in str(caught.value)


def test_delete_accepts_canonical_hosted_mcp_not_found_response(tmp_path):
    p = provider(tmp_path, [tool({}), Response({"result": {
        "isError": True, "content": [{"type": "text", "text": "Requested entity was not found."}]
    }})])
    assert p.delete_runtime("runtimes/owned-a") == {"name": "runtimes/owned-a", "released": True}


def test_hosted_mcp_precondition_is_actionable_and_private(tmp_path):
    p = provider(tmp_path, [Response({"result": {
        "isError": True, "content": [{"type": "text", "text": "Precondition check failed."}]
    }})])
    with pytest.raises(ProviderError) as caught:
        p.create_runtime("owned-a", str(uuid.uuid4()),
                         {"variant": "VARIANT_CPU", "accelerator": "NONE", "shape": "SHAPE_STANDARD"})
    assert caught.value.code == "precondition"
    assert not caught.value.retryable
    assert "Precondition check failed" not in str(caught.value)


def test_runtime_creation_allows_provider_cold_start_before_timeout(tmp_path):
    p = provider(tmp_path, [tool({"name": "runtimes/owned-a"})])
    p.create_runtime("owned-a", str(uuid.uuid4()),
                     {"variant": "VARIANT_CPU", "accelerator": "NONE", "shape": "SHAPE_STANDARD"})
    assert p._opener.requests[0][1] == 120


def test_auth_refresh_only_retries_rejected_401(tmp_path):
    p = provider(tmp_path, [error(401), tool({"tier": "SUBSCRIPTION_TIER_PRO"})])
    assert p.get_subscription()["tier"] == "SUBSCRIPTION_TIER_PRO"
    assert p.oauth.refreshes == [False, True]
    assert len(p._opener.requests) == 2
    p = provider(tmp_path, [error(401), error(401)])
    with pytest.raises(ProviderError) as caught:
        p.get_subscription()
    assert caught.value.code == "needs_auth"
    assert len(p._opener.requests) == 2


@pytest.mark.parametrize("failure", [
    error(409),
    Response({"result": {"isError": True, "structuredContent": {"error": {"status": "ALREADY_EXISTS"}},
                          "content": [{"type": "text", "text": '{"message":"synthetic-secret"}'}]}}),
    TimeoutError("synthetic-secret"),
])
def test_create_session_reconciles_exact_existing_session(tmp_path, failure):
    expected = {"name": "runtimes/owned-a/sessions/worker-a"}
    p = provider(tmp_path, [failure, tool({"sessions": [
        {"name": "runtimes/other-a/sessions/worker-a"}, expected,
        {"name": "runtimes/owned-a/sessions/user-session"},
    ]})])
    assert p.create_session("runtimes/owned-a", "worker-a") == expected
    assert len(p._opener.requests) == 2
    assert json.loads(p._opener.requests[1][0].data)["params"] == {
        "name": "list_sessions", "arguments": {"parent": "runtimes/owned-a"},
    }


def test_create_session_never_adopts_similar_or_other_runtime_sessions(tmp_path):
    p = provider(tmp_path, [error(409), tool({"sessions": [
        {"name": "runtimes/other-a/sessions/worker-a"},
        {"name": "runtimes/owned-a/sessions/worker-ab"},
    ]})])
    with pytest.raises(ProviderError) as caught:
        p.create_session("runtimes/owned-a", "worker-a")
    assert caught.value.code == "already_exists"
    assert len(p._opener.requests) == 2
    p = provider(tmp_path, [tool({"name": "runtimes/owned-a/sessions/other-session"})])
    with pytest.raises(ProviderError) as caught:
        p.create_session("runtimes/owned-a", "worker-a")
    assert caught.value.code == "provider_error"


def test_nested_mcp_error_body_is_categorized_without_provider_text(tmp_path):
    p = provider(tmp_path, [Response({"result": {"isError": True, "content": [{
        "type": "text", "text": json.dumps({"error": {"code": 429, "message": "synthetic-secret"}}),
    }]}})])
    with pytest.raises(ProviderError) as caught:
        p.get_subscription()
    assert caught.value.code == "quota"
    assert "synthetic-secret" not in str(caught.value)


def test_delete_requires_confirmed_missing_runtime(tmp_path):
    p = provider(tmp_path, [tool({}), error(404)])
    assert p.delete_runtime("runtimes/owned-a") == {"name": "runtimes/owned-a", "released": True}
    call = json.loads(p._opener.requests[0][0].data)
    assert call["params"]["arguments"] == {"name": "runtimes/owned-a", "allowMissing": True}
    assert json.loads(p._opener.requests[1][0].data)["params"]["name"] == "get_runtime"


def test_sse_socket_timeout_is_recoverable_and_cancel_prevents_start(tmp_path):
    import threading
    p = provider(tmp_path, [TimeoutError("must not be logged")])
    with pytest.raises(ProviderError) as caught:
        p.get_subscription()
    assert caught.value.code == "timeout"
    assert caught.value.retryable
    p.cancel_event = threading.Event()
    p.cancel_event.set()
    with pytest.raises(ProviderError) as caught:
        p.get_subscription()
    assert caught.value.code == "cancelled"
    assert len(p._opener.requests) == 1


def test_oauth_client_is_per_account_and_protected(tmp_path):
    oauth = GoogleOAuth(tmp_path, "google-pro-1", allow_unencrypted=True)
    assert oauth.configure_client(desktop_client(tmp_path))["configured"]
    authorized(oauth)
    assert oauth.status()["authorized"]
    assert not GoogleOAuth(tmp_path, "google-pro-2", allow_unencrypted=True).status()["configured"]
    import os
    if os.name == "nt":
        assert b"synthetic-secret" not in oauth.path.read_bytes()
        assert b"synthetic-refresh" not in oauth.path.read_bytes()
    else:
        assert oauth.path.stat().st_mode & 0o077 == 0


def test_oauth_rejects_untrusted_token_endpoint(tmp_path):
    oauth = GoogleOAuth(tmp_path, allow_unencrypted=True)
    with pytest.raises(ProviderError) as caught:
        oauth.configure_client(desktop_client(tmp_path, token_uri="https://example.invalid/steal"))
    assert caught.value.code == "invalid_client"
    assert not oauth.status()["configured"]


def test_expired_oauth_refreshes_without_opening_browser(tmp_path, monkeypatch):
    oauth = GoogleOAuth(tmp_path, allow_unencrypted=True)
    oauth.configure_client(desktop_client(tmp_path))
    authorized(oauth, expires_at=0)
    requests = []

    def token_request(url, *, form=None, token=""):
        requests.append(form)
        return {"access_token": "new-synthetic-access", "expires_in": 3600, "scope": COLAB_SCOPE}

    monkeypatch.setattr(oauth, "_json_request", token_request)
    assert oauth.access_token() == "new-synthetic-access"
    assert oauth.access_token() == "new-synthetic-access"
    assert len(requests) == 1
    assert requests[0]["grant_type"] == "refresh_token"
    assert oauth.status()["authorized"]


def test_invalid_refresh_becomes_needs_auth(tmp_path, monkeypatch):
    oauth = GoogleOAuth(tmp_path, allow_unencrypted=True)
    oauth.configure_client(desktop_client(tmp_path))
    authorized(oauth, expires_at=0)

    def denied(*args, **kwargs):
        raise ProviderError("needs_auth", "Google cần xác thực lại.")

    monkeypatch.setattr(oauth, "_json_request", denied)
    with pytest.raises(ProviderError):
        oauth.access_token()
    assert not oauth.status()["authorized"]
    assert oauth.status()["state"] == "needs_auth"


def test_loopback_auth_checks_state_pkce_identity_and_single_use(tmp_path, monkeypatch):
    oauth = GoogleOAuth(tmp_path, allow_unencrypted=True)
    oauth.configure_client(desktop_client(tmp_path))
    requests = []

    def auth_response(url, *, form=None, token=""):
        if form:
            requests.append(form)
            return {"access_token": "synthetic-access", "refresh_token": "synthetic-refresh", "expires_in": 3600,
                    "scope": "openid email " + COLAB_SCOPE}
        return {"sub": "subject-a", "email": "test@example.invalid", "email_verified": True}

    monkeypatch.setattr(oauth, "_json_request", auth_response)
    session = oauth.begin_auth()
    try:
        query = parse_qs(urlsplit(session.url).query)
        assert query["code_challenge_method"] == ["S256"]
        assert query["access_type"] == ["offline"]
        with pytest.raises(HTTPError) as caught:
            urlopen(session.callback_url + "?" + urlencode({"state": "wrong", "code": "synthetic"}), timeout=3)
        assert caught.value.code == 400
        assert session.status()["state"] == "pending"
        with urlopen(session.callback_url + "?" + urlencode({"state": session.state, "code": "synthetic-code"}), timeout=3) as response:
            assert response.status == 200
        assert session.status()["state"] == "complete"
        assert oauth.status()["authorized"]
        assert requests[0]["code_verifier"]
        assert requests[0]["redirect_uri"] == session.callback_url
    finally:
        session.close()


def test_reauth_with_different_google_subject_preserves_existing_owner(tmp_path, monkeypatch):
    oauth = GoogleOAuth(tmp_path, allow_unencrypted=True)
    oauth.configure_client(desktop_client(tmp_path))
    authorized(oauth)

    def wrong_identity(url, *, form=None, token=""):
        if form:
            return {"access_token": "different-access", "refresh_token": "different-refresh", "expires_in": 3600}
        return {"sub": "subject-b", "email": "other@example.invalid", "email_verified": True}

    monkeypatch.setattr(oauth, "_json_request", wrong_identity)
    with pytest.raises(ProviderError) as caught:
        oauth._complete_auth(oauth._read(), "synthetic-code", "synthetic-verifier", "http://127.0.0.1/callback", lambda: True)
    assert caught.value.code == "wrong_account"
    assert oauth.status()["email"] == "test@example.invalid"
    assert oauth.access_token() == "synthetic-access"
