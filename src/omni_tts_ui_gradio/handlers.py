from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any

import gradio as gr

from omni_tts_core.user_state import restore_user_state
from omni_tts_core.service import TtsService
from omni_tts_core.runtime_devices import RUNTIME_TARGET_CHOICES
from omni_tts_shared.errors import OmniTtsError
from omni_tts_shared.languages import LANGUAGE_LABELS
from omni_tts_shared.schemas import GenerateSpeechRequest, ModelStatus
from omni_tts_shared.voice_presets import (
    NO_VOICE_PRESET_ID,
)
from omni_tts_shared.vieneu_codecs import NO_CODEC_ID, NO_CODEC_LABEL
from omni_tts_ui_gradio import chatterbox_settings, f5_settings


restore_user_state()
service = TtsService()

LANGUAGE_PROFILE_CHOICES = [
    (label, code)
    for code, label in LANGUAGE_LABELS.items()
    if code not in {"auto"}
]


def model_choices() -> list[tuple[str, str]]:
    return [
        (_model_label(service.registry.get(item.model_id)), item.model_id)
        for item in service.list_tts_models()
    ]


def all_model_choices() -> list[tuple[str, str]]:
    return [
        (_model_label(service.registry.get(item.model_id)), item.model_id)
        for item in service.list_models()
    ]


def _model_label(spec) -> str:
    info = spec.catalog_info
    badges: list[str] = []
    origin = {
        "official": "Official",
        "community": "Community",
        "custom": "Custom",
    }.get(str(info.get("origin") or ""), "")
    category = {
        "official-cpu": "Official",
        "official-gpu": "Official",
        "community": "Community",
        "experimental": "Debug/Legacy",
        "multilingual": "Multilingual",
        "support": "Support",
    }.get(str(info.get("category") or ""), "")
    variant = str(info.get("variant_badge") or "").strip()
    risk = {
        "test": "Test",
        "checkpoint": "Checkpoint",
        "debug": "Debug",
    }.get(str(info.get("risk") or ""), "")
    if origin:
        badges.append(origin)
    elif category:
        badges.append(category)
    if variant:
        badges.append(variant)
    if risk and risk not in badges:
        badges.append(risk)
    suffix = " ".join(f"[{item}]" for item in badges)
    return f"{spec.display_name} {suffix}" if suffix else spec.display_name


def voice_profile_choices() -> list[tuple[str, str]]:
    choices = [("Không dùng profile", "")]
    choices.extend((item.name, item.profile_id) for item in service.list_voice_profiles())
    return choices


def voice_profile_table() -> list[list[Any]]:
    rows = []
    for profile in service.list_voice_profiles():
        rows.append([
            profile.profile_id,
            profile.name,
            LANGUAGE_LABELS.get(profile.language, profile.language),
            f"{profile.duration_seconds:.1f}s" if profile.duration_seconds else "?",
            profile.project,
            str(profile.audio_path),
        ])
    return rows


def refresh_voice_profile_controls():
    choices = voice_profile_choices()
    edit_choices = [(label, value) for label, value in choices if value]
    return (
        voice_profile_table(),
        gr.update(choices=choices),
        gr.update(choices=edit_choices),
    )


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


model_supports_f5_settings = service.supports_f5_settings
model_supports_chatterbox_settings = service.supports_chatterbox_settings

def model_supports_pitch_shift(model_id: str) -> bool:
    return service.model_capabilities(model_id).supports_pitch_shift


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


def default_f5_setting(model_id: str, key: str, fallback):
    return f5_settings.default_setting(service, model_id, key, fallback)


def default_chatterbox_setting(model_id: str, key: str, fallback):
    return chatterbox_settings.default_setting(service, model_id, key, fallback)


def runtime_target_choices() -> list[tuple[str, str]]:
    return [(label, value) for label, value in RUNTIME_TARGET_CHOICES]


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
        gr.update(value=0.0, interactive=caps.supports_pitch_shift),
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
        *f5_settings.control_updates(service, model_id),
        *chatterbox_settings.control_updates(service, model_id),
    )


def profile_compat_update(voice_profile_id: str, model_id: str) -> str:
    if not voice_profile_id or not model_id:
        return ""
    try:
        compat = service.profile_quality_for_model(voice_profile_id, model_id)
        return compat.message
    except Exception:
        return ""


def profile_duration_info(voice_profile_id: str) -> str:
    if not voice_profile_id:
        return ""
    try:
        profile = service.voice_profiles.get_profile(voice_profile_id)
        dur = profile.duration_seconds
        sr = profile.sample_rate
        if dur == 0.0:
            return "(chưa có metadata — lưu lại profile để cập nhật)"
        sr_text = f"{sr // 1000}kHz" if sr > 0 else ""
        return f"{dur:.1f}s" + (f"  |  {sr_text}" if sr_text else "")
    except Exception:
        return ""


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
            _runtime_device_label(item.actual_device),
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


def ui_preferences() -> dict[str, Any]:
    path = service.settings.project_root / "config" / "ui_tkinter.json"
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


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


def preview_remove_model(model_id: str) -> tuple[str, list[list[Any]]]:
    try:
        message = service.model_removal_preview(model_id)
    except OmniTtsError as exc:
        message = f"Lỗi: {exc}"
    return message, refresh_model_table()


def remove_selected_model(model_id: str) -> tuple[str, list[list[Any]]]:
    try:
        status = service.remove_model(model_id)
        message = f"Đã gỡ phần lưu trữ riêng của: {status.display_name}"
    except OmniTtsError as exc:
        message = f"Lỗi: {exc}"
    return message, refresh_model_table()


def install_gpu_for_model(model_id: str) -> tuple[str, list[list[Any]]]:
    try:
        message = service.install_gpu_acceleration(model_id)
    except Exception as exc:
        message = f"Chưa cài được GPU: {exc}"
    return message, refresh_runtime_table()


def get_model_catalog_html() -> dict:
    from omni_tts_core.model_catalog import generate_catalog_html
    html = generate_catalog_html(service.settings.app_name)
    return gr.update(value=html, visible=True)


def generate_speech(
    text: str,
    source_files,
    language: str,
    model_id: str,
    codec_repo: str,
    voice_profile_id: str,
    reference_audio: str | None,
    reference_text: str,
    speaker_id: str,
    speed: float,
    pitch_shift: float,
    emotion: str,
    runtime_target: str,
    temperature: float,
    top_k: int,
    f5_nfe_step: int, f5_cfg_strength: float, f5_sway_sampling_coef: float,
    f5_cross_fade_duration: float, f5_target_rms: float, f5_fix_duration: float,
    f5_seed: float | None, f5_remove_silence: bool,
    chatterbox_temperature: float, chatterbox_top_p: float, chatterbox_top_k: int,
    chatterbox_repetition_penalty: float, chatterbox_seed: float | None,
    chatterbox_norm_loudness: bool,
    sentence_pause_ms: int,
    paragraph_pause_ms: int,
    max_chunk_chars: int,
    output_stem: str,
    output_dir: str,
    output_audio_format: str,
    mp3_bitrate_kbps: int,
    overwrite: bool,
    split_output: bool,
    output_srt: bool,
    join_split_output_audio: bool,
):
    try:
        sources = _source_paths(source_files)
        if not sources and not text.strip():
            return "Bạn chưa nhập nội dung hoặc upload file nguồn.", None, None, None, None
        f5_kwargs = f5_settings.request_kwargs(
            service, model_id, f5_nfe_step, f5_cfg_strength, f5_sway_sampling_coef,
            f5_cross_fade_duration, f5_target_rms, f5_fix_duration, f5_seed, f5_remove_silence,
        )
        chatterbox_kwargs = chatterbox_settings.request_kwargs(
            service,
            model_id,
            chatterbox_temperature,
            chatterbox_top_p,
            chatterbox_top_k,
            chatterbox_repetition_penalty,
            chatterbox_seed,
            chatterbox_norm_loudness,
        )

        request = _generation_request(
            text=text.strip() or "source file",
            language=language,
            model_id=model_id,
            codec_repo=service.valid_vieneu_codec_repo(model_id, codec_repo),
            voice_profile_id=voice_profile_id or None,
            reference_audio_path=_audio_path(reference_audio),
            reference_text=reference_text.strip() or None,
            speaker_id=_speaker_id(model_id, speaker_id, voice_profile_id),
            speed=float(speed),
            pitch_shift=float(pitch_shift or 0.0),
            emotion=emotion,
            runtime_target=runtime_target or "auto",
            temperature=float(temperature) if service.supports_vieneu_sampling(model_id) else None,
            top_k=int(top_k) if service.supports_vieneu_sampling(model_id) else None,
            **f5_kwargs,
            **chatterbox_kwargs,
            sentence_pause_ms=int(sentence_pause_ms),
            paragraph_pause_ms=int(paragraph_pause_ms),
            srt_file_padding_ms=int(paragraph_pause_ms),
            max_chunk_chars=int(max_chunk_chars),
            output_dir=_optional_path(output_dir),
            output_stem=output_stem.strip() or None,
            overwrite=bool(overwrite),
            output_mode="split" if split_output else "merged",
            output_audio_format=output_audio_format or "wav",
            mp3_bitrate_kbps=int(mp3_bitrate_kbps),
            output_srt=bool(output_srt),
            join_split_output_audio=bool(join_split_output_audio),
        )
        _save_generation_preferences(
            {
                "language": language,
                "model_id": model_id,
                "voice_profile_id": voice_profile_id or None,
                "speaker_id": _speaker_id(model_id, speaker_id, voice_profile_id),
                "output_dir": (output_dir or "").strip(),
                "output_stem": (output_stem or "").strip(),
                "speed": float(speed),
                "pitch_shift": float(pitch_shift or 0.0),
                "emotion": emotion,
                "runtime_target": runtime_target or "auto",
                "codec_repo": service.valid_vieneu_codec_repo(model_id, codec_repo),
                "temperature": float(temperature) if service.supports_vieneu_sampling(model_id) else None,
                "top_k": int(top_k) if service.supports_vieneu_sampling(model_id) else None,
                **f5_kwargs,
                **chatterbox_kwargs,
                "sentence_pause_ms": int(sentence_pause_ms),
                "paragraph_pause_ms": int(paragraph_pause_ms),
                "srt_file_padding_ms": int(paragraph_pause_ms),
                "max_chunk_chars": int(max_chunk_chars),
                "overwrite": bool(overwrite),
                "split_output": bool(split_output),
                "output_audio_format": output_audio_format or "wav",
                "mp3_bitrate_kbps": int(mp3_bitrate_kbps),
                "output_srt": bool(output_srt),
                "join_split_output_audio": bool(join_split_output_audio),
            }
        )

        if sources:
            batch_id, batch_dir = service.job_store.create_job_dir()
            target_dir = request.output_dir or batch_dir
            results = [
                service.generate_from_source_file(source, request, output_dir=target_dir)
                for source in sources
            ]
            package_path = _zip_results(results, batch_dir / f"{batch_id}_outputs.zip")
            message = _results_message(results, package_path)
        else:
            result = service.generate_audio(request)
            results = [result]
            package_path = _zip_results(results, result.job_dir / f"{result.job_id}_outputs.zip")
            message = _results_message(results, package_path)

        audio_path = _first_audio(results)
        srt_path = _first_srt(results)
        return (
            message,
            str(audio_path) if audio_path else None,
            str(audio_path) if audio_path else None,
            str(srt_path) if srt_path else None,
            str(package_path) if package_path else None,
        )
    except OmniTtsError as exc:
        return f"Chưa tạo được audio: {exc}", None, None, None, None
    except Exception as exc:
        return f"Lỗi không mong muốn: {exc}", None, None, None, None


def save_voice_profile(
    profile_id: str,
    name: str,
    audio_file,
    transcript: str,
    language: str,
    project: str,
    notes: str,
):
    try:
        audio_path = _first_uploaded_path(audio_file)
        if profile_id and audio_path is None:
            audio_path = service.voice_profiles.get_profile(profile_id).audio_path
        if audio_path is None:
            return (
                "Hãy upload file giọng mẫu.",
                voice_profile_table(),
                gr.update(),
                gr.update(),
                profile_id or "",
            )
        profile, warnings = service.save_voice_profile(
            name=name,
            audio_path=audio_path,
            transcript=transcript or "",
            language=language or "vi",
            project=project or "",
            notes=notes or "",
            profile_id=profile_id or None,
        )
        warning_text = "\n".join(item.message for item in warnings)
        message = f"Đã lưu profile: {profile.name}"
        if warning_text:
            message = f"{message}\n{warning_text}"
    except Exception as exc:
        message = f"Chưa lưu được profile: {exc}"
    choices = voice_profile_choices()
    edit_choices = [(label, value) for label, value in choices if value]
    return (
        message,
        voice_profile_table(),
        gr.update(choices=choices, value=profile.profile_id if "profile" in locals() else None),
        gr.update(choices=edit_choices, value=profile.profile_id if "profile" in locals() else None),
        profile.profile_id if "profile" in locals() else profile_id or "",
    )


def load_voice_profile_form(profile_id: str):
    if not profile_id:
        return "", "", None, "", "vi", "", ""
    try:
        profile = service.voice_profiles.get_profile(profile_id)
    except Exception:
        return "", "", None, "", "vi", "", ""
    return (
        profile.profile_id,
        profile.name,
        None,
        profile.transcript,
        profile.language,
        profile.project,
        profile.notes,
    )


def clear_voice_profile_form():
    return "", "", None, "", "vi", "", ""


def delete_voice_profile(profile_id: str):
    if not profile_id:
        return "Hãy chọn profile cần xóa.", voice_profile_table(), gr.update(), gr.update(), ""
    try:
        service.delete_voice_profile(profile_id)
        message = "Đã xóa profile."
    except Exception as exc:
        message = f"Chưa xóa được profile: {exc}"
    choices = voice_profile_choices()
    edit_choices = [(label, value) for label, value in choices if value]
    return (
        message,
        voice_profile_table(),
        gr.update(choices=choices, value=""),
        gr.update(choices=edit_choices, value=None),
        "",
    )


def _generation_request(**kwargs) -> GenerateSpeechRequest:
    return GenerateSpeechRequest(**kwargs)


def _save_generation_preferences(update: dict[str, Any]) -> None:
    path = service.settings.project_root / "config" / "ui_tkinter.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    data = ui_preferences()
    data.update(update)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _source_paths(value) -> list[Path]:
    if not value:
        return []
    if isinstance(value, (str, Path)):
        return [Path(value)]
    paths: list[Path] = []
    for item in value:
        path = _first_uploaded_path(item)
        if path is not None:
            paths.append(path)
    return paths


def _first_uploaded_path(value) -> Path | None:
    if not value:
        return None
    if isinstance(value, (str, Path)):
        return Path(value)
    if isinstance(value, dict):
        name = value.get("name") or value.get("path")
        return Path(name) if name else None
    name = getattr(value, "name", None)
    return Path(name) if name else None


def _optional_path(value: str | None) -> Path | None:
    text = (value or "").strip()
    return Path(text).expanduser() if text else None


def _result_paths(result) -> list[Path]:
    paths: list[Path] = []
    if result.audio_path:
        paths.append(result.audio_path)
    paths.extend(result.item_audio_paths)
    if result.item_srt_paths:
        paths.extend(result.item_srt_paths)
    elif result.srt_path:
        paths.append(result.srt_path)
    return [path for path in paths if path and Path(path).exists()]


def _zip_results(results, zip_path: Path) -> Path | None:
    files: list[Path] = []
    for result in results:
        files.extend(_result_paths(result))
    unique_files = []
    seen = set()
    for path in files:
        resolved = Path(path).resolve()
        if resolved not in seen:
            seen.add(resolved)
            unique_files.append(Path(path))
    if not unique_files:
        return None
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    used_names: set[str] = set()
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in unique_files:
            arcname = path.name
            if arcname in used_names:
                arcname = f"{path.parent.name}_{path.name}"
            used_names.add(arcname)
            archive.write(path, arcname)
    return zip_path


def _results_message(results, package_path: Path | None) -> str:
    total_segments = sum(item.segment_count for item in results)
    total_duration = sum(item.duration_seconds for item in results)
    audio_count = sum(_result_audio_count(item) for item in results)
    messages = "; ".join(item.message for item in results)
    package_text = f" Gói tải về: {package_path.name}." if package_path else ""
    return (
        f"{messages} {audio_count} file audio, {total_segments} đoạn, "
        f"{total_duration:.1f} giây.{package_text}"
    )


def _result_audio_count(result) -> int:
    paths = []
    if result.audio_path:
        paths.append(Path(result.audio_path))
    paths.extend(Path(path) for path in result.item_audio_paths)
    seen = {path.resolve() for path in paths if path.exists() and path.suffix.lower() in {".wav", ".mp3"}}
    return len(seen) or 1


def _first_audio(results) -> Path | None:
    for result in results:
        if result.audio_path and Path(result.audio_path).exists():
            return result.audio_path
    return None


def _first_srt(results) -> Path | None:
    for result in results:
        if result.srt_path and Path(result.srt_path).exists():
            return result.srt_path
    return None


def _status_row(item: ModelStatus) -> list[Any]:
    if item.worker_installed is False:
        status = "Chưa cài worker"
    elif item.hf_cached is False:
        status = "Thiếu HF cache"
    elif item.installed:
        status = "Sẵn sàng" if item.worker_installed is not True else "Worker + model OK"
    elif item.worker_installed is True:
        status = "Worker OK, thiếu model"
    else:
        status = "Chưa tải"
    return [
        item.display_name,
        _short_text(item.usage, 100),
        item.provider,
        "Có" if item.required else "Không",
        status,
        _format_model_size(item),
        item.storage_kind,
        str(item.storage_path or item.local_path),
        item.hf_repo,
    ]


def _format_model_size(item: ModelStatus) -> str:
    total = item.total_size_mb if item.total_size_mb else item.size_mb
    if total >= 1024:
        return f"{total / 1024:.2f} GB"
    return f"{total:.0f} MB"


def _short_text(value: str, limit: int) -> str:
    text = " ".join((value or "").split())
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"


def _audio_path(value: str | None) -> Path | None:
    if not value:
        return None
    return Path(value)


def _speaker_id(model_id: str, value: str | None, voice_profile_id: str | None) -> str | None:
    if voice_profile_id:
        return None
    return service.valid_voice_preset_id(model_id, value)


def _runtime_device_label(value: str | None) -> str:
    return {
        "auto-cuda": "Auto → CUDA",
        "auto-cpu": "Auto → CPU",
        "cuda-unavailable": "CUDA chưa sẵn sàng",
        "cuda-partial": "CUDA chưa đủ backend",
        "not-installed": "Chưa cài",
        "missing": "Thiếu model",
        "worker": "Worker",
        "cuda": "CUDA",
        "cpu": "CPU",
        "auto": "Auto",
    }.get(str(value or ""), str(value or "Không rõ"))
