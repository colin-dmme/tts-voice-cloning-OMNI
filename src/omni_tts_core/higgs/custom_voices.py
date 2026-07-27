from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from omni_tts_core.paths import ensure_dir
from omni_tts_core.remote.endpoint import RemoteEndpointTransport
from omni_tts_core.remote.higgs_sglang import audio_data_uri
from omni_tts_shared.errors import ConfigError, GenerationError
from omni_tts_shared.schemas import HiggsCustomVoice, RemoteEndpointOptions


class HiggsCustomVoiceClient:
    def __init__(self, endpoint: RemoteEndpointOptions) -> None:
        self.endpoint = endpoint
        self.transport = RemoteEndpointTransport(endpoint)

    def create(
        self,
        *,
        title: str,
        reference_audio_path: Path,
        reference_text: str,
    ) -> HiggsCustomVoice:
        clean_title = title.strip()
        clean_text = reference_text.strip()
        if not clean_title:
            raise ConfigError("Tên Custom Voice không được để trống.")
        if not clean_text:
            raise ConfigError(
                "Custom Voice cần transcript chính xác của audio tham chiếu."
            )
        response = self.transport.post_json(
            self.transport.paths.voices_url,
            {
                "title": clean_title,
                "ref_audio": audio_data_uri(reference_audio_path),
                "ref_text": clean_text,
            },
        )
        try:
            payload = json.loads(response.body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise GenerationError("API tạo Custom Voice trả về JSON không hợp lệ.") from exc
        voice_id = str(payload.get("voice_id") or payload.get("id") or "").strip()
        if not voice_id:
            raise GenerationError("API tạo Custom Voice không trả về voice_id.")
        return HiggsCustomVoice(
            voice_id=voice_id,
            title=str(payload.get("title") or clean_title),
            endpoint_id=self.endpoint.endpoint_id,
            api_flavor=self.endpoint.api_flavor,
            ref_text=str(payload.get("ref_text") or clean_text),
            created_at=str(
                payload.get("created_at")
                or datetime.now().isoformat(timespec="seconds")
            ),
        )


class HiggsCustomVoiceStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or (ensure_dir("voices") / "higgs_custom_voices.json")

    def list(self, endpoint_id: str) -> list[HiggsCustomVoice]:
        return sorted(
            (
                voice
                for voice in self._read_all()
                if voice.endpoint_id == endpoint_id
            ),
            key=lambda voice: voice.title.casefold(),
        )

    def save(self, voice: HiggsCustomVoice) -> HiggsCustomVoice:
        voices = self._read_all()
        by_key = {
            (item.endpoint_id, item.voice_id): item
            for item in voices
        }
        by_key[(voice.endpoint_id, voice.voice_id)] = voice
        payload = [
            item.model_dump(mode="json")
            for item in sorted(
                by_key.values(),
                key=lambda item: (item.endpoint_id, item.title.casefold()),
            )
        ]
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return voice

    def _read_all(self) -> list[HiggsCustomVoice]:
        if not self.path.exists():
            return []
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ConfigError(
                f"Danh sách Higgs Custom Voice không hợp lệ: {self.path}"
            ) from exc
        if not isinstance(payload, list):
            raise ConfigError(
                f"Danh sách Higgs Custom Voice không hợp lệ: {self.path}"
            )
        return [HiggsCustomVoice.model_validate(item) for item in payload]
