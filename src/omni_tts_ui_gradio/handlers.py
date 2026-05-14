from __future__ import annotations

from pathlib import Path
from typing import Any

import gradio as gr

from omni_tts_core.service import TtsService
from omni_tts_shared.errors import OmniTtsError
from omni_tts_shared.languages import LANGUAGE_LABELS
from omni_tts_shared.schemas import GenerateSpeechRequest, ModelStatus
from omni_tts_shared.voice_presets import (
    NO_VOICE_PRESET_ID,
)
from omni_tts_shared.vieneu_codecs import NO_CODEC_ID, NO_CODEC_LABEL


service = TtsService()


def model_choices() -> list[tuple[str, str]]:
    return [(item.display_name, item.model_id) for item in service.list_tts_models()]


def all_model_choices() -> list[tuple[str, str]]:
    return [(item.display_name, item.model_id) for item in service.list_models()]


def voice_profile_choices() -> list[tuple[str, str]]:
    choices = [("Không dùng profile", "")]
    choices.extend((item.name, item.profile_id) for item in service.list_voice_profiles())
    return choices


def speaker_choices_for_model(model_id: str) -> list[tuple[str, str]]:
    caps = service.model_capabilities(model_id)
    return service.list_voice_presets(model_id, include_none=caps.supports_voice_profile)


def default_voice_preset_id(model_id: str) -> str | None:
    return service.default_voice_preset_id(model_id)


def has_voice_presets(model_id: str) -> bool:
    return service.has_voice_presets(model_id)


def model_supports_codec(model_id: str) -> bool:
    return service.supports_vieneu_codec(model_id)


def model_supports_sampling(model_id: str) -> bool:
    return service.supports_vieneu_sampling(model_id)


def codec_choices_for_model(model_id: str) -> list[tuple[str, str]]:
    if not service.supports_vieneu_codec(model_id):
        return [(NO_CODEC_LABEL, NO_CODEC_ID)]
    return service.list_vieneu_codecs(model_id)


def default_codec_repo(model_id: str) -> str:
    return service.default_vieneu_codec_repo(model_id) or NO_CODEC_ID


def default_temperature(model_id: str) -> float:
    return service.default_vieneu_temperature(model_id)


def default_top_k(model_id: str) -> int:
    return service.default_vieneu_top_k(model_id)


def language_choices_for_model(model_id: str) -> list[tuple[str, str]]:
    caps = service.model_capabilities(model_id)
    return [(LANGUAGE_LABELS.get(item, item), item) for item in caps.supported_languages]


def default_language_for_model(model_id: str, preferred: str = "vi") -> str:
    caps = service.model_capabilities(model_id)
    if preferred in caps.supported_languages:
        return preferred
    return caps.supported_languages[0]


def generation_control_updates(model_id: str, current_language: str):
    caps = service.model_capabilities(model_id)
    choices = [(LANGUAGE_LABELS.get(item, item), item) for item in caps.supported_languages]
    language = current_language if current_language in caps.supported_languages else caps.supported_languages[0]
    preset_value = service.default_voice_preset_id(model_id) or NO_VOICE_PRESET_ID
    preset_active = service.has_voice_presets(model_id)
    return (
        gr.update(choices=choices, value=language),
        gr.update(value=1.0, interactive=caps.supports_speed),
        gr.update(
            choices=[(item, item) for item in (caps.emotions or ["natural"])],
            value=(caps.emotions or ["natural"])[0],
            interactive=caps.supports_emotion,
        ),
        gr.update(value="", interactive=caps.supports_voice_profile and not preset_active),
        gr.update(
            choices=speaker_choices_for_model(model_id),
            value=preset_value,
            interactive=preset_active,
        ),
        gr.update(
            choices=codec_choices_for_model(model_id),
            value=default_codec_repo(model_id),
            interactive=service.supports_vieneu_codec(model_id),
        ),
        gr.update(value=default_temperature(model_id), interactive=service.supports_vieneu_sampling(model_id)),
        gr.update(value=default_top_k(model_id), interactive=service.supports_vieneu_sampling(model_id)),
    )


def profile_changed_updates(voice_profile_id: str, model_id: str):
    if voice_profile_id:
        return gr.update(value=NO_VOICE_PRESET_ID, interactive=False)
    default_preset = service.default_voice_preset_id(model_id) or NO_VOICE_PRESET_ID
    return gr.update(
        choices=speaker_choices_for_model(model_id),
        value=default_preset,
        interactive=service.has_voice_presets(model_id),
    )


def speaker_changed_updates(speaker_id: str, model_id: str):
    caps = service.model_capabilities(model_id)
    if service.valid_voice_preset_id(model_id, speaker_id):
        return gr.update(value="", interactive=False)
    return gr.update(interactive=caps.supports_voice_profile)


def refresh_model_table() -> list[list[Any]]:
    return [_status_row(item) for item in service.list_models()]


def refresh_runtime_table() -> list[list[Any]]:
    return [
        [
            item.display_name,
            item.provider,
            "Đã cài" if item.installed else "Chưa cài",
            "Có" if item.gpu_available else "Không",
            item.actual_device,
            item.device_name,
            item.message,
        ]
        for item in service.list_runtime_statuses()
    ]


def startup_notice() -> str:
    missing = service.missing_required_models()
    if not missing:
        return "Sẵn sàng. Các model bắt buộc đã có trong dự án."
    names = ", ".join(item.display_name for item in missing)
    return f"Cần tải model bắt buộc còn thiếu: {names}."


def download_selected_model(model_id: str) -> tuple[str, list[list[Any]]]:
    try:
        status = service.download_model(model_id)
        message = f"Đã tải xong: {status.display_name}"
    except OmniTtsError as exc:
        message = f"Lỗi: {exc}"
    return message, refresh_model_table()


def download_required_models() -> tuple[str, list[list[Any]]]:
    try:
        downloaded = service.download_missing_required_models()
        if not downloaded:
            message = "Các model bắt buộc đã có sẵn."
        else:
            names = ", ".join(item.display_name for item in downloaded)
            message = f"Đã tải xong model bắt buộc: {names}."
    except OmniTtsError as exc:
        message = f"Lỗi: {exc}"
    return message, refresh_model_table()


def generate_speech(
    text: str,
    language: str,
    model_id: str,
    codec_repo: str,
    voice_profile_id: str,
    reference_audio: str | None,
    reference_text: str,
    speaker_id: str,
    speed: float,
    emotion: str,
    temperature: float,
    top_k: int,
    sentence_pause_ms: int,
    max_chunk_chars: int,
    split_output: bool,
    output_srt: bool,
):
    try:
        if not text.strip():
            return "Bạn chưa nhập nội dung cần đọc.", None, None, None
        request = GenerateSpeechRequest(
            text=text,
            language=language,
            model_id=model_id,
            codec_repo=service.valid_vieneu_codec_repo(model_id, codec_repo),
            voice_profile_id=voice_profile_id or None,
            reference_audio_path=_audio_path(reference_audio),
            reference_text=reference_text.strip() or None,
            speaker_id=_speaker_id(model_id, speaker_id, voice_profile_id),
            speed=float(speed),
            emotion=emotion,
            temperature=float(temperature) if service.supports_vieneu_sampling(model_id) else None,
            top_k=int(top_k) if service.supports_vieneu_sampling(model_id) else None,
            sentence_pause_ms=int(sentence_pause_ms),
            max_chunk_chars=int(max_chunk_chars),
            output_mode="split" if split_output else "merged",
            output_srt=bool(output_srt),
        )
        result = service.generate_audio(request)
        message = (
            f"{result.message} Job: {result.job_id}. "
            f"{result.segment_count} đoạn, {result.duration_seconds:.1f} giây."
        )
        srt_path = str(result.srt_path) if result.srt_path else None
        return message, str(result.audio_path), str(result.audio_path), srt_path
    except OmniTtsError as exc:
        return f"Chưa tạo được audio: {exc}", None, None, None
    except Exception as exc:
        return f"Lỗi không mong muốn: {exc}", None, None, None


def _status_row(item: ModelStatus) -> list[Any]:
    return [
        item.display_name,
        item.model_type,
        "Có" if item.required else "Không",
        "Đã tải" if item.installed else "Chưa tải",
        item.size_mb,
        str(item.local_path),
        item.hf_repo,
    ]


def _audio_path(value: str | None) -> Path | None:
    if not value:
        return None
    return Path(value)


def _speaker_id(model_id: str, value: str | None, voice_profile_id: str | None) -> str | None:
    if voice_profile_id:
        return None
    return service.valid_voice_preset_id(model_id, value)
