from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from omni_tts_core.authoring.schemas import AiProviderSettings

GEMINI_MODELS = (
    "gemini-3.6-flash",
    "gemini-3.5-flash",
    "gemini-3.5-flash-lite",
    "gemini-flash-latest",
    "gemini-flash-lite-latest",
    "gemini-3.1-flash-lite",
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
)

_MODELS_WITHOUT_TEMPERATURE = {
    "gemini-3.6-flash",
    "gemini-3.5-flash-lite",
    "gemini-flash-latest",
    "gemini-flash-lite-latest",
}


class AuthoringProviderError(RuntimeError):
    pass


@dataclass(frozen=True)
class AuthoringCallUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    finish_reason: str = ""


def supports_sampling_temperature(model: str) -> bool:
    return model.strip() not in _MODELS_WITHOUT_TEMPERATURE


class GeminiAuthoringProvider:
    """Gemini adapter isolated behind an authoring-provider boundary."""

    def __init__(self, api_key: str, settings: AiProviderSettings) -> None:
        try:
            from openai import OpenAI
        except ImportError as error:
            raise AuthoringProviderError(
                "Thiếu package 'openai'. Hãy cập nhật môi trường ứng dụng."
            ) from error
        self.settings = settings
        self._client = OpenAI(
            api_key=api_key,
            base_url=settings.base_url,
            timeout=settings.timeout_seconds,
            max_retries=0,
        )

    def call_json(
        self,
        system: str,
        user: str,
    ) -> tuple[dict[str, Any], AuthoringCallUsage]:
        kwargs: dict[str, Any] = {
            "model": self.settings.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "response_format": {"type": "json_object"},
        }
        if supports_sampling_temperature(self.settings.model):
            kwargs["temperature"] = self.settings.temperature
        if self.settings.max_output_tokens:
            kwargs["max_tokens"] = self.settings.max_output_tokens
        try:
            response = self._client.chat.completions.create(**kwargs)
            choice = response.choices[0]
            raw = choice.message.content or "{}"
            payload = _parse_json_object(raw)
            usage = response.usage
            return payload, AuthoringCallUsage(
                input_tokens=int(getattr(usage, "prompt_tokens", 0) or 0),
                output_tokens=int(getattr(usage, "completion_tokens", 0) or 0),
                finish_reason=str(choice.finish_reason or ""),
            )
        except AuthoringProviderError:
            raise
        except Exception as error:
            raise AuthoringProviderError(f"{type(error).__name__}: {error}") from error

    def test_connection(self) -> str:
        payload, _usage = self.call_json(
            "Return only a JSON object.",
            'Return {"status":"ok"}.',
        )
        if str(payload.get("status", "")).lower() != "ok":
            raise AuthoringProviderError(f"Phản hồi kiểm tra không hợp lệ: {payload}")
        return f"Gemini hoạt động · model={self.settings.model}"

    def list_models(self) -> list[str]:
        try:
            items = self._client.models.list()
            result = [
                str(getattr(item, "id", "")).strip()
                for item in items
                if str(getattr(item, "id", "")).startswith("gemini-")
            ]
            return sorted(dict.fromkeys(item for item in result if item))
        except Exception as error:
            raise AuthoringProviderError(
                f"Không lấy được danh sách model: {type(error).__name__}: {error}"
            ) from error


def _parse_json_object(raw: str) -> dict[str, Any]:
    clean = raw.strip()
    if clean.startswith("```"):
        clean = clean.split("\n", 1)[-1]
        clean = clean.rsplit("```", 1)[0].strip()
    try:
        payload = json.loads(clean)
    except json.JSONDecodeError as error:
        raise AuthoringProviderError(
            f"Gemini không trả JSON hợp lệ: {error}"
        ) from error
    if not isinstance(payload, dict):
        raise AuthoringProviderError("Gemini phải trả về một JSON object.")
    return payload
