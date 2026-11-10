from __future__ import annotations

import io
import wave
from datetime import datetime, timezone
from threading import Event
from types import SimpleNamespace

import pytest

from colin_colab_remote import context, lifecycle
from colin_colab_remote.broker.models import (
    PairingPreview,
    RemoteJobStatus,
    RemoteTtsJob,
    RemoteTtsRequest,
    WorkerCapabilities,
    WorkerModelCapability,
    WorkerProfile,
    WorkerRecord,
)
from colin_colab_remote.broker.profiles import WorkerProfileDocument, WorkerProfileStore
from colin_colab_remote.context import ManagedExecution
from colin_colab_remote.oauth import ProviderError
from colin_colab_remote.settings import ColabSettings
from colin_colab_remote.store import ColabStore
from omni_tts_shared.errors import GenerationCancelled, GenerationError


class FakeProvider:
    def __init__(self, store):
        self.store = store
        self.created = []
        self.sessions = []
        self.executions = []
        self.deleted = []
        self.ready = False
        self.creation_timeout = False
        self.deletion_timeout = False

    def get_subscription(self):
        return {"tier": "SUBSCRIPTION_TIER_PRO"}

    def list_runtime_specs(self):
        return [
            {"eligible": True, "key": {"variant": "VARIANT_GPU", "accelerator": "T4", "shape": "SHAPE_STANDARD"}},
            {"eligible": True, "key": {"variant": "VARIANT_CPU", "accelerator": "NONE", "shape": "SHAPE_STANDARD"}},
        ]

    def create_runtime(self, runtime_id, request_id, spec):
        record = self.store.state("runtime")
        assert record["phase"] == "allocating"
        assert record["runtime_id"] == runtime_id
        assert record["request_id"] == request_id
        self.created.append((runtime_id, request_id, spec))
        if self.creation_timeout:
            self.creation_timeout = False
            raise ProviderError("timeout", "Creation accepted but response lost.", retryable=True)
        return {"name": "runtimes/" + runtime_id}

    def create_session(self, runtime_name, session_id):
        self.sessions.append((runtime_name, session_id))
        return {"name": runtime_name + "/sessions/" + session_id}

    def execute(self, code, session, execution_id):
        self.executions.append((code, session, execution_id))
        record = self.store.state("runtime")
        if "_colin_managed.begin" in code:
            return {"value": {"worker_id": record["worker_id"], "launch_id": record["launch_id"], "user_code": "ABCD-EFGH"}}
        if "_colin_managed.launch" in code:
            self.ready = True
            return {"value": {"status": "started"}}
        return {"value": {"status": "running"}}

    def delete_runtime(self, name):
        assert self.store.state("runtime")["phase"] == "release_pending"
        self.deleted.append(name)
        if self.deletion_timeout:
            self.deletion_timeout = False
            raise ProviderError("timeout", "Deletion response lost.", retryable=True)
        self.ready = False
        return {"name": name, "released": True}


class FakeBroker:
    def __init__(self, store, provider):
        self.store, self.provider = store, provider
        self.approved = []
        self.revoked = []
        self.submitted = []
        self.downloaded = []
        self.cancelled = []
        self.jobs = {}
        self.start_status = RemoteJobStatus.SUCCEEDED
        self.on_get_job = None
        self.preview_launch_id = None
        self.approval_timeout = False

    def health(self):
        return {"status": "ok", "pairing": "enabled", "managed_colab": "enabled"}

    def inspect_pairing(self, user_code):
        record = self.store.state("runtime")
        return PairingPreview(
            pairing_id="pairing-current-launch",
            worker_id=record["worker_id"],
            launch_id=self.preview_launch_id or record["launch_id"],
            provider=record["provider"],
            device=record["device"],
            expires_at=datetime.now(timezone.utc).isoformat(),
            session_hours=12,
        )

    def approve_pairing(self, user_code, preview):
        self.approved.append((user_code, preview))
        if self.approval_timeout:
            self.approval_timeout = False
            raise GenerationError("Pairing approved but response lost")
        return {"status": "approved"}

    def get_pairing_launch(self, launch_id):
        for _code, preview in self.approved:
            if preview.launch_id == launch_id:
                return {"status": "approved", "worker_id": preview.worker_id,
                        "provider": preview.provider, "device": preview.device, "launch_id": launch_id}
        return {"status": "pending", "launch_id": launch_id}

    def list_workers(self):
        if not self.provider.ready:
            return []
        record = self.store.state("runtime")
        return [WorkerRecord(
            last_seen_at=datetime.now(timezone.utc).isoformat(),
            capabilities=WorkerCapabilities(
                worker_id=record["worker_id"],
                launch_id=record["launch_id"],
                display_name="Owned test worker",
                models=(WorkerModelCapability(
                    model_id=record["model_id"],
                    provider_id=record["provider"],
                    execution_backend=record["device"],
                    sample_rate=48000,
                    supports_batch=True,
                    supports_profile_clone=True,
                ),),
            ),
        )]

    def revoke_pairing(self, worker_id):
        self.revoked.append(worker_id)
        return {"status": "revoked", "sessions": 1}

    def get_job_by_idempotency(self, key):
        if key not in self.jobs:
            raise GenerationError("Broker HTTP 404")
        return self.jobs[key]

    def submit(self, request, *, worker_id=""):
        self.submitted.append((request, worker_id))
        job = RemoteTtsJob(job_id="broker-job-1", request=request, status=self.start_status)
        self.jobs[request.idempotency_key] = job
        return job

    def get_job(self, job_id):
        if self.on_get_job is not None:
            callback, self.on_get_job = self.on_get_job, None
            callback()
        return next(job for job in self.jobs.values() if job.job_id == job_id)

    def cancel(self, job_id):
        self.cancelled.append(job_id)
        job = next(job for job in self.jobs.values() if job.job_id == job_id)
        job.status = RemoteJobStatus.CANCELLED
        return job

    def download_result(self, job, destination):
        self.downloaded.append(job.job_id)
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as output:
            output.setnchannels(1)
            output.setsampwidth(2)
            output.setframerate(48000)
            output.writeframes(b"\x01\x00" * 480)
        destination.write_bytes(buffer.getvalue())
        return destination


@pytest.fixture
def system(tmp_path, monkeypatch):
    store = ColabStore(tmp_path / "managed")
    profiles = WorkerProfileStore(tmp_path / "workers.json")
    profiles.save(WorkerProfileDocument(profiles=[WorkerProfile(
        profile_id="google-pro-1", label="Test account", worker_id="google-pro-1", broker_url="https://broker.test",
    )]))
    provider = FakeProvider(store)
    broker = FakeBroker(store, provider)
    monkeypatch.setattr(lifecycle, "BrokerClient", lambda options: broker)
    control = SimpleNamespace(status=lambda **kwargs: SimpleNamespace(local_healthy=True))
    monkeypatch.setattr(lifecycle, "LocalBrokerManager", lambda: control)
    monkeypatch.setattr(context.time, "sleep", lambda seconds: None)
    settings = ColabSettings(enabled=True)
    manager = lifecycle.ColabLifecycle(store, settings, provider, profiles)
    return SimpleNamespace(store=store, profiles=profiles, provider=provider, broker=broker, lifecycle=manager)


def request(**updates):
    values = dict(client_job_id="call-1", inference_unit_id="chunk-1", idempotency_key="call-1:chunk-1",
                  model_id="zerotts_202m_official", text="Nội dung dùng kiểm thử.")
    return RemoteTtsRequest(**{**values, **updates})


def new_context(system):
    job = system.store.create("generate", {"text": "Nội dung dùng kiểm thử."})
    return job["job_id"], ManagedExecution(system.store, job["job_id"], system.lifecycle)


def test_runtime_identity_is_persisted_before_allocation_and_reused_after_uncertain_create(system):
    system.provider.creation_timeout = True
    with pytest.raises(ProviderError, match="response lost"):
        system.lifecycle.ensure("vieneu_v3_turbo", lambda: None, lambda message: None)
    first = system.store.state("runtime")
    assert first["phase"] == "allocating"
    assert first["launch_id"]

    system.lifecycle.ensure("vieneu_v3_turbo", lambda: None, lambda message: None)
    current = system.store.state("runtime")
    assert current["phase"] == "ready"
    assert len(system.provider.created) == 2
    assert system.provider.created[0] == system.provider.created[1]
    assert current["runtime_id"] == first["runtime_id"]
    assert current["launch_id"] == first["launch_id"]
    assert system.broker.approved[0][0] == "ABCD-EFGH"
    assert system.broker.approved[0][1].launch_id == first["launch_id"]


def test_pairing_from_another_launch_is_rejected_before_approval(system):
    system.broker.preview_launch_id = "another-owned-runtime"
    with pytest.raises(GenerationError, match="không khớp"):
        system.lifecycle.ensure("vieneu_v3_turbo", lambda: None, lambda message: None)
    assert system.broker.approved == []
    assert not system.provider.ready


def test_uncertain_pairing_approval_is_reconciled_without_approving_twice(system):
    system.broker.approval_timeout = True
    system.lifecycle.ensure("vieneu_v3_turbo", lambda: None, lambda message: None)
    before = system.lifecycle.record()
    assert before["phase"] == "ready"
    system.lifecycle.ensure("vieneu_v3_turbo", lambda: None, lambda message: None)
    assert system.lifecycle.record()["phase"] == "ready"
    assert system.lifecycle.record()["launch_id"] == before["launch_id"]
    assert len(system.broker.approved) == 1
    assert len(system.provider.created) == 1
    begin_calls = [call for call in system.provider.executions if "_colin_managed.begin" in call[0]]
    assert len(begin_calls) == 1


def test_release_retries_only_the_recorded_runtime_after_timeout(system):
    system.lifecycle.ensure("zerotts_202m_official", lambda: None, lambda message: None)
    original = system.lifecycle.record()
    system.provider.deletion_timeout = True
    with pytest.raises(ProviderError, match="response lost"):
        system.lifecycle.release()
    assert system.lifecycle.record()["phase"] == "release_pending"
    assert system.broker.revoked == []

    system.lifecycle.release()
    assert system.provider.deleted == [original["name"], original["name"]]
    assert system.broker.revoked == [original["worker_id"]]
    assert system.lifecycle.record() == {}


def test_release_without_an_owned_runtime_has_no_provider_side_effect(system):
    system.lifecycle.release()
    assert system.provider.deleted == []
    assert system.broker.revoked == []


def test_resumed_unit_uses_verified_cache_and_does_not_submit_again(system, tmp_path):
    job_id, execution = new_context(system)
    first = tmp_path / "first.wav"
    execution.execute(request(), first)
    resumed_store = ColabStore(system.store.directory)
    resumed = ManagedExecution(resumed_store, job_id, system.lifecycle)
    second = tmp_path / "second.wav"
    resumed.execute(request(idempotency_key="different-caller-retry-key"), second)
    assert second.read_bytes() == first.read_bytes()
    assert len(system.broker.submitted) == 1
    assert len(system.broker.downloaded) == 1
    assert resumed_store.state(job_id + ":verified_units") == 1


def test_corrupt_cached_unit_is_downloaded_again_under_the_same_broker_key(system, tmp_path):
    job_id, execution = new_context(system)
    first = tmp_path / "first.wav"
    execution.execute(request(), first)
    cache = next(execution.units.glob("*.wav"))
    cache.write_bytes(b"corrupted")
    resumed = ManagedExecution(ColabStore(system.store.directory), job_id, system.lifecycle)
    second = tmp_path / "second.wav"
    resumed.execute(request(), second)
    assert second.read_bytes() == first.read_bytes()
    assert len(system.broker.submitted) == 1
    assert len(system.broker.downloaded) == 2


def test_verified_cached_unit_can_resume_without_allocating_google_resources(system, tmp_path, monkeypatch):
    job_id, execution = new_context(system)
    execution.execute(request(), tmp_path / "first.wav")
    system.lifecycle.release()
    resumed = ManagedExecution(ColabStore(system.store.directory), job_id, system.lifecycle)

    def unexpected_provision(*args, **kwargs):
        pytest.fail("A verified local result should be restored before provisioning Google compute.")

    monkeypatch.setattr(system.lifecycle, "ensure", unexpected_provision)
    resumed.execute(request(), tmp_path / "second.wav")
    assert len(system.provider.created) == 1


def test_paused_and_cancelled_jobs_persist_across_store_reopen(system):
    job_id, execution = new_context(system)
    system.store.control(job_id, "pause")
    restored = ColabStore(system.store.directory)
    assert restored.get(job_id)["paused"]
    assert restored.next_job() is None
    restored.control(job_id, "cancel")
    current = system.store.get(job_id)
    assert current["cancel_requested"]
    assert not current["paused"]
    assert current["status"] == "cancelling"
    with pytest.raises(GenerationCancelled):
        execution.check()
    assert system.provider.created == []


def test_paused_execution_waits_before_provisioning_and_can_resume(system, tmp_path, monkeypatch):
    job_id, execution = new_context(system)
    system.store.control(job_id, "pause")
    waited = []

    def resume_on_wait(seconds):
        assert system.provider.created == []
        waited.append(seconds)
        system.store.control(job_id, "resume")

    monkeypatch.setattr(context.time, "sleep", resume_on_wait)
    execution.execute(request(), tmp_path / "voice.wav")
    assert waited
    assert len(system.broker.submitted) == 1


def test_store_cancellation_cancels_the_same_inflight_broker_job(system, tmp_path):
    job_id, execution = new_context(system)
    system.broker.start_status = RemoteJobStatus.RUNNING
    system.broker.on_get_job = lambda: system.store.control(job_id, "cancel")
    with pytest.raises(GenerationCancelled):
        execution.execute(request(), tmp_path / "cancelled.wav")
    assert system.broker.cancelled == ["broker-job-1"]
    assert system.provider.deleted == []
    assert execution._active_broker_job is None


def test_cancel_event_interrupts_inflight_work_and_requests_broker_cancel(system, tmp_path):
    _job_id, execution = new_context(system)
    cancelled = Event()
    system.broker.start_status = RemoteJobStatus.RUNNING
    system.broker.on_get_job = cancelled.set

    def guard_against_ignored_event():
        if cancelled.is_set() and not system.broker.cancelled:
            pytest.fail("The caller's cancellation event must cancel the current broker job.")
        return next(iter(system.broker.jobs.values()))

    original_get = system.broker.get_job
    calls = []

    def get_job(job_id):
        calls.append(job_id)
        if len(calls) > 2:
            return guard_against_ignored_event()
        return original_get(job_id)

    system.broker.get_job = get_job
    with pytest.raises(GenerationCancelled):
        execution.execute(request(), tmp_path / "cancelled.wav", cancel_event=cancelled)
    assert system.broker.cancelled == ["broker-job-1"]
