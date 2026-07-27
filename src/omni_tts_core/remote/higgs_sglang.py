from __future__ import annotations

import base64
import io
import mimetypes
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import soundfile as sf

from omni_tts_core.remote.endpoint import RemoteEndpointTransport
from omni_tts_core.higgs.script import apply_delivery_defaults
from omni_tts_shared.errors import ConfigError, GenerationError
from omni_tts_shared.schemas import HiggsTtsOptions, RemoteEndpointOptions


@dataclass(frozen=True)
class EndpointCheckResult:
    ok: bool
    message: str
    model_ids: tuple[str, ...] = ()


class HiggsSglangClient:
    """Protocol adapter for SGLang, Boson, and compatible Higgs speech routes."""

    def __init__(
        self,
        endpoint: RemoteEndpointOptions,
        options: HiggsTtsOptions,
    ) -> None:
        self.endpoint = endpoint
        self.options = options
        self.transport = RemoteEndpointTransport(endpoint)

    def check(self) -> EndpointCheckResult:
        if self.endpoint.api_flavor == "boson":
            models = self.transport.get_json(self.transport.paths.models_url)
            ids = _model_ids(models)
            detail = "Boson API hoạt động"
            if ids:
                detail += " · model: " + ", ".join(ids)
            return EndpointCheckResult(True, detail, ids)
        health_response = self.transport.get(self.transport.paths.health_url)
        models = self.transport.get_json(self.transport.paths.models_url)
        ids = _model_ids(models)
        health_text = health_response.body.decode("utf-8", errors="replace").strip()
        detail = f"Endpoint hoạt động · health={health_text or health_response.status}"
        if ids:
            detail += " · model: " + ", ".join(ids)
        return EndpointCheckResult(True, detail, ids)

    def synthesize(
        self,
        *,
        text: str,
        reference_audio_path: Path | None = None,
        reference_text: str | None = None,
    ) -> tuple[np.ndarray, int]:
        payload = self.build_payload(
            text=text,
            reference_audio_path=reference_audio_path,
            reference_text=reference_text,
        )
        response = self.transport.post_json(self.transport.paths.speech_url, payload)
        content_type = response.headers.get("content-type", "").split(";", 1)[0].lower()
        if self.options.response_format == "pcm" or content_type in {
            "audio/pcm",
            "application/octet-stream",
        }:
            sample_rate = _positive_int(response.headers.get("x-sample-rate"), 24000)
            channels = _positive_int(response.headers.get("x-channels"), 1)
            audio = np.frombuffer(response.body, dtype="<i2").astype(np.float32) / 32768.0
            if channels > 1:
                audio = audio.reshape(-1, channels).mean(axis=1)
            return audio.copy(), sample_rate
        try:
            audio, sample_rate = sf.read(io.BytesIO(response.body), dtype="float32")
        except Exception as exc:
            raise GenerationError(
                "Endpoint không trả về PCM/WAV hợp lệ. Hãy kiểm tra response_format và stream."
            ) from exc
        if audio.ndim > 1:
            audio = audio.mean(axis=1)
        return np.asarray(audio, dtype=np.float32), int(sample_rate)

    def build_payload(
        self,
        *,
        text: str,
        reference_audio_path: Path | None = None,
        reference_text: str | None = None,
    ) -> dict:
        tagged_text = apply_delivery_defaults(text, self.options)
        payload: dict[str, object] = {
            "input": tagged_text,
            "voice": self.options.voice,
            "response_format": self.options.response_format,
            "stream": self.options.stream,
            "max_new_tokens": self.options.max_new_tokens,
        }
        if self.endpoint.api_flavor == "sglang":
            payload["initial_codec_chunk_frames"] = (
                self.options.initial_codec_chunk_frames
            )
        if self.options.model:
            payload["model"] = self.options.model
        elif self.endpoint.api_flavor == "boson":
            payload["model"] = "higgs-tts-3"
        for key in ("temperature", "top_p", "top_k", "seed"):
            value = getattr(self.options, key)
            if value is not None:
                payload[key] = value
        if reference_audio_path:
            encoded = audio_data_uri(reference_audio_path)
            transcript = (reference_text or "").strip()
            if self.endpoint.api_flavor == "boson":
                payload["ref_audio"] = encoded
                payload["ref_text"] = transcript
            else:
                payload["references"] = [
                    {
                        "audio_path": encoded,
                        "text": transcript,
                    }
                ]
        return payload


def audio_data_uri(path: Path) -> str:
    source = Path(path)
    if not source.is_file():
        raise ConfigError(f"Không tìm thấy audio tham chiếu: {source}")
    mime = mimetypes.guess_type(source.name)[0] or "audio/wav"
    encoded = base64.b64encode(source.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def _model_ids(payload: object) -> tuple[str, ...]:
    if not isinstance(payload, dict):
        return ()
    data = payload.get("data")
    if not isinstance(data, list):
        return ()
    return tuple(
        str(item["id"])
        for item in data
        if isinstance(item, dict) and item.get("id")
    )


def _positive_int(value: str | None, fallback: int) -> int:
    try:
        parsed = int(str(value))
    except (TypeError, ValueError):
        return fallback
    return parsed if parsed > 0 else fallback
