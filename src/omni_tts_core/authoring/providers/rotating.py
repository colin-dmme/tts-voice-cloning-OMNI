from __future__ import annotations

import threading
import time
from collections.abc import Callable
from threading import Event
from typing import Any

from omni_tts_core.authoring.key_store import (
    AuthoringKeyStore,
    classify_provider_error,
)
from omni_tts_core.authoring.providers.gemini import (
    AuthoringCallUsage,
    AuthoringProviderError,
    GeminiAuthoringProvider,
)
from omni_tts_core.authoring.schemas import AiProviderSettings

NoticeCallback = Callable[[str], None]


class RotatingAuthoringProvider:
    def __init__(
        self,
        key_store: AuthoringKeyStore,
        settings: AiProviderSettings,
        *,
        client_factory=GeminiAuthoringProvider,
    ) -> None:
        self.key_store = key_store
        self.settings = settings
        self.client_factory = client_factory

    def call_json(
        self,
        system: str,
        user: str,
        *,
        on_notice: NoticeCallback | None = None,
        cancel_event: Event | None = None,
    ) -> tuple[dict[str, Any], AuthoringCallUsage]:
        key_tries = 0
        busy_retries = 0
        attempt = 0
        last_error: Exception | None = None
        self._notice(
            on_notice,
            f"[AI] Chuẩn bị · provider={self.settings.provider_id} · "
            f"model={self.settings.model} · input_chars={len(user):,}",
        )
        while key_tries < self.settings.max_key_tries:
            _check_cancel(cancel_event)
            pair = self.key_store.get_next_key(self.settings.provider_id)
            if pair is None:
                raise AuthoringProviderError(
                    "Không còn Gemini API key active. Mở mục AI / API để kiểm tra."
                )
            key_name, key_value = pair
            attempt += 1
            started = time.monotonic()
            stop = threading.Event()
            heartbeat = self._heartbeat(
                stop,
                started,
                attempt,
                key_name,
                on_notice,
            )
            try:
                self._notice(
                    on_notice,
                    f"[AI] Gửi request · attempt={attempt} · key={key_name}",
                )
                provider = self.client_factory(key_value, self.settings)
                payload, usage = provider.call_json(system, user)
                self.key_store.release_key(self.settings.provider_id, key_name)
                self._notice(
                    on_notice,
                    f"[AI] Thành công · key={key_name} · "
                    f"elapsed={time.monotonic() - started:.1f}s · "
                    f"tokens={usage.input_tokens:,}→{usage.output_tokens:,}",
                )
                return payload, usage
            except AuthoringProviderError as error:
                last_error = error
                category = classify_provider_error(str(error))
                self._notice(
                    on_notice,
                    f"[AI] Thất bại · key={key_name} · category={category} · "
                    f"error={_short_error(error)}",
                )
                if category in {"quota_exceeded", "invalid"}:
                    self.key_store.mark_key_error(
                        self.settings.provider_id,
                        key_name,
                        str(error),
                    )
                    key_tries += 1
                    continue
                self.key_store.release_key(self.settings.provider_id, key_name)
                if (
                    category == "server_busy"
                    and busy_retries < self.settings.max_busy_retries
                ):
                    delay = min(15.0, 2.0 * (2**busy_retries))
                    busy_retries += 1
                    self._notice(
                        on_notice,
                        f"[AI] Server bận · chờ {delay:.0f}s · "
                        f"retry={busy_retries}/{self.settings.max_busy_retries}",
                    )
                    _wait(delay, cancel_event)
                    continue
                raise
            finally:
                stop.set()
                if heartbeat:
                    heartbeat.join(timeout=0.2)
        raise AuthoringProviderError(
            f"Đã thử {self.settings.max_key_tries} key nhưng chưa thành công. "
            f"Lỗi cuối: {last_error}"
        ) from last_error

    def _heartbeat(
        self,
        stop: Event,
        started: float,
        attempt: int,
        key_name: str,
        on_notice: NoticeCallback | None,
    ) -> threading.Thread | None:
        if on_notice is None:
            return None

        def run() -> None:
            while not stop.wait(10.0):
                self._notice(
                    on_notice,
                    f"[AI] Đang chờ Gemini · attempt={attempt} · key={key_name} · "
                    f"elapsed={time.monotonic() - started:.0f}s/"
                    f"{self.settings.timeout_seconds:.0f}s",
                )

        thread = threading.Thread(target=run, daemon=True)
        thread.start()
        return thread

    @staticmethod
    def _notice(callback: NoticeCallback | None, message: str) -> None:
        if callback:
            callback(message)


def _check_cancel(cancel_event: Event | None) -> None:
    if cancel_event is not None and cancel_event.is_set():
        raise AuthoringProviderError("Đã hủy phân tích AI.")


def _wait(seconds: float, cancel_event: Event | None) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        _check_cancel(cancel_event)
        time.sleep(min(0.2, deadline - time.monotonic()))


def _short_error(error: Exception, limit: int = 500) -> str:
    value = " ".join(str(error).split())
    return value if len(value) <= limit else value[: limit - 1] + "…"
