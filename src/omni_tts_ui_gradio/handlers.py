from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any

import gradio as gr

from omni_tts_core.chapter_music import (
    ChapterMusicLibrary,
    ChapterMusicSelector,
    music_duration_note,
    preview_chapter_music,
)
from omni_tts_core.runtime_devices import RUNTIME_TARGET_CHOICES
from omni_tts_core.service import TtsService
from omni_tts_core.text.epub_reader import read_epub
from omni_tts_core.user_state import restore_user_state
from omni_tts_shared.epub import EpubOptions
from omni_tts_shared.errors import OmniTtsError
from omni_tts_shared.languages import LANGUAGE_LABELS
from omni_tts_shared.schemas import GenerateSpeechRequest, ModelStatus
from omni_tts_shared.vieneu_codecs import NO_CODEC_ID, NO_CODEC_LABEL
from omni_tts_shared.voice_presets import (
    NO_VOICE_PRESET_ID,
)
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


def refresh_setup_table(model_id: str | None = None) -> list[list[Any]]:
    return [_setup_row(item) for item in service.setup_statuses(model_id or None)]


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


def install_gpu_for_model(model_id: str) -> tuple[str, list[list[Any]], list[list[Any]]]:
    try:
        message = service.install_gpu_acceleration(model_id)
    except Exception as exc:
        message = f"Chưa cài được GPU: {exc}"
    return message, refresh_setup_table(model_id), refresh_runtime_table()


def install_base_for_model(model_id: str) -> tuple[str, list[list[Any]], list[list[Any]]]:
    try:
        message = service.install_base_runtime_for_model(model_id)
    except Exception as exc:
        message = f"Chưa cài được worker/môi trường: {exc}"
    return message, refresh_setup_table(model_id), refresh_runtime_table()


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
    epub_start=1, epub_end=0, epub_titles=True, epub_volumes=True, epub_mode="chapters",
    epub_title_pause=1.2, epub_chapter_pause=2.5, epub_scene_pause=1.2, epub_volume_pause=1.8,
    music_enabled=False, music_track_id=None, music_volume=30, music_between=True, music_after_title=False,
    music_mode="fixed", music_theme=None, music_seed=0,
    music_duration_mode="fit_pause",
    title_break_mode=None, title_duration_mode="fit_pause", title_fade_in=.12, title_fade_out=.35,
    chapter_break_mode=None, chapter_duration_mode="fit_pause", chapter_fade_in=.12, chapter_fade_out=.35,
    music_preset_id=None,music_theme_ids=None,music_track_ids=None,music_excluded_ids=None,
    content_skip_references=True,content_url_mode="skip",content_read_notes=True,content_han_mode="prefer_vietnamese",
    content_frontmatter=True,content_appendices=True,content_technical=False,content_export=True,content_han_readings="",
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
            epub_options=EpubOptions(chapter_start=int(epub_start), chapter_end=int(epub_end),
                read_titles=bool(epub_titles), include_volumes=bool(epub_volumes), output_mode=epub_mode,
                title_pause_ms=round(epub_title_pause * 1000), chapter_pause_ms=round(epub_chapter_pause * 1000),
                scene_pause_ms=round(epub_scene_pause * 1000), volume_pause_ms=round(epub_volume_pause * 1000)),
            # Filled below so the same shared EPUB schema validates every UI.
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
        request.epub_options.content = epub_content_options(content_skip_references,content_url_mode,content_read_notes,content_han_mode,
            content_frontmatter,content_appendices,content_technical,content_export,content_han_readings)
        request.epub_options.music = request.epub_options.music.model_validate({
            "enabled": bool(music_enabled), "track_id": music_track_id,
            "volume_percent": int(music_volume), "between_chapters": bool(music_between),
            "after_title": bool(music_after_title),
            "selection_mode": music_mode, "theme": music_theme, "random_seed": int(music_seed),
            "duration_mode": music_duration_mode,
            'preset_id':music_preset_id,'theme_ids':music_theme_ids or [],'track_ids':music_track_ids or [],
            'excluded_track_ids':music_excluded_ids or [],
            "track_overrides": ui_preferences().get("epub_options", {}).get("music", {}).get("track_overrides", {}),
        })
        from omni_tts_shared.epub import EpubBreakOptions
        for kind, mode, seconds, duration_mode, fade_in, fade_out in (
            ('title', title_break_mode, epub_title_pause, title_duration_mode, title_fade_in, title_fade_out),
            ('chapter', chapter_break_mode, epub_chapter_pause, chapter_duration_mode, chapter_fade_in, chapter_fade_out),
        ):
            if mode is not None:
                request.epub_options.breaks[kind] = EpubBreakOptions(mode=mode,
                    duration_ms=round(seconds*1000),duration_mode=duration_mode,
                    fade_in_ms=round(fade_in*1000),fade_out_ms=round(fade_out*1000))
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
                "epub_options": request.epub_options.model_dump(),
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


def chapter_music_choices():
    return [(t.name, t.track_id) for t in ChapterMusicLibrary().list_tracks()]


def chapter_music_themes():
    return [(f"{g['name']} ({g['count']} bản)", g['theme']) for g in ChapterMusicLibrary().list_themes()]


def chapter_music_preset_choices():
    from omni_tts_core.music_presets import MusicPresetStore
    return [(p.name,p.preset_id) for p in MusicPresetStore().list_presets()]


def music_selection_note(track_id,mode,theme,preset_id,themes,tracks,excluded):
    if mode in ('fixed','random_theme'):return chapter_music_note(track_id,mode,theme,source_only=True)
    from omni_tts_shared.epub import ChapterMusicOptions
    try:
        selector=ChapterMusicSelector(ChapterMusicOptions(selection_mode=mode,preset_id=preset_id,
            theme_ids=themes or [],track_ids=tracks or [],excluded_track_ids=excluded or []))
        return f'Random trong {len(selector.pool)} bản đã chọn, không tính trùng giữa các nhóm. Loại nghỉ/thời lượng/fade chỉnh theo từng vị trí.'
    except OmniTtsError as exc:return str(exc)


def chapter_music_note(track_id, selection_mode="fixed", theme=None, duration_mode="fit_pause", source_only=False):
    tracks = ChapterMusicLibrary().list_tracks()
    item = next((t for t in tracks if t.track_id == track_id), None)
    note = "Nguồn nhạc dùng chung; thời lượng và fade chỉnh riêng tại từng vị trí nghỉ." if source_only else music_duration_note(duration_mode)
    if selection_mode == "random_theme":
        pool = ChapterMusicLibrary().list_tracks(theme=theme) if theme else []
        note += f"\n\nNhóm {theme or 'chưa chọn'}: {len(pool)} bản. Trộn hết nhóm trước khi lặp, giữ lượt trộn để tiếp tục tác vụ."
        if pool:
            note += "\n\n" + "; ".join(t.name for t in pool)
        if any(t.provenance.get('generated_plan') == 'free' for t in pool):
            note += "\n\nCó mẫu ElevenLabs Free: dùng cá nhân; chưa có quyền thương mại."
        return note
    if item:
        note += f"\n\n{item.description or 'Chưa có mô tả.'}\n\nChủ đề: {', '.join(item.themes)}. Tag: {', '.join(item.tags)}."
    if item and item.provenance.get("generated_plan") == "free":
        note += " Mẫu ElevenLabs Free: dùng cá nhân; chưa có quyền thương mại."
    return note


def preview_epub_music(track_id, duration_seconds, volume_percent, selection_mode="fixed", theme=None, random_seed=0, duration_mode="fit_pause", fade_in_seconds=.12, fade_out_seconds=.35,
                       preset_id=None,theme_ids=None,track_ids=None,excluded_track_ids=None):
    import secrets

    from omni_tts_shared.epub import ChapterMusicOptions
    options = ChapterMusicOptions(track_id=track_id, selection_mode=selection_mode, theme=theme, random_seed=int(random_seed), duration_mode=duration_mode,
        preset_id=preset_id,theme_ids=theme_ids or [],track_ids=track_ids or [],excluded_track_ids=excluded_track_ids or [])
    track_id = ChapterMusicSelector(options, context=secrets.token_hex(8)).choose("preview").track_id
    return str(preview_chapter_music(track_id, duration_ms=round(duration_seconds * 1000), volume_percent=int(volume_percent), duration_mode=duration_mode,
        fade_in_ms=round(fade_in_seconds*1000),fade_out_ms=round(fade_out_seconds*1000)))


def epub_break_updates(available, mode, duration_mode, seconds):
    musical = mode == 'music'
    full = musical and duration_mode == 'full_track'
    audible = musical and (full or seconds > 0)
    note = ('Theo độ dài bản nhạc; số giây không áp dụng, không cộng thêm khoảng lặng. SRT tự cập nhật.' if full
            else 'Không chèn khoảng nghỉ.' if mode == 'none'
            else 'Khoảng lặng theo số giây; không phát nhạc.' if not musical
            else 'Nhạc cắt/fade vừa số giây; fade dài tự co theo nhịp ngắn.')
    if not available:
        note = 'Vị trí này bị tắt vì không đọc tên chương.'
    return [gr.update(interactive=bool(available)), gr.update(interactive=bool(available and musical)),
            gr.update(interactive=bool(available and mode != 'none' and not full)),
            gr.update(interactive=bool(available and audible)), gr.update(interactive=bool(available and audible)),
            gr.update(interactive=bool(available and audible)), note]


def epub_music_source_updates(titles, title_kind, title_duration, title_seconds,
                              chapter_kind, chapter_duration, chapter_seconds, selection):
    active = ((titles and title_kind == 'music' and (title_duration == 'full_track' or title_seconds > 0))
              or (chapter_kind == 'music' and (chapter_duration == 'full_track' or chapter_seconds > 0)))
    return [gr.update(interactive=bool(active)), gr.update(interactive=bool(active and selection == 'fixed')),
            gr.update(interactive=bool(active and selection == 'random_theme')),
            gr.update(interactive=bool(active and selection == 'random_theme')),
            gr.update(interactive=bool(active)), gr.update(interactive=bool(active)),
            gr.update(interactive=bool(active and selection=='preset')),
            gr.update(interactive=bool(active and selection=='random_selection')),
            gr.update(interactive=bool(active and selection=='random_selection')),
            gr.update(interactive=bool(active and selection=='random_selection'))]


def import_epub_music(uploaded):
    path = _first_uploaded_path(uploaded)
    if path is None:
        return gr.update()
    item = ChapterMusicLibrary().import_track(path.resolve(), path.stem, provenance={"provider": "user_import"})
    return gr.update(choices=chapter_music_choices(), value=item.track_id)


def preview_epub(source_files):
    try:
        source = next((p for p in _source_paths(source_files) if p.suffix.lower() == ".epub"), None)
        if source is None:
            return "Hãy tải lên một EPUB trước."
        book = read_epub(source)
        info = book.preview(limit=100)
        return (f"{book.title} — {len(book.chapters)} chương\nBỏ qua: {len(book.skipped_documents)} phần. Chưa tạo giọng.\n\n"
            + "\n".join(f"{c['index']}. {c['title']}\n   {c['preview']}" for c in info["chapters"])
            + ("\n\nLưu ý: " + "\n".join(book.warnings) if book.warnings else ""))
    except Exception as exc:
        return f"Không đọc được EPUB: {exc}"


def epub_content_options(skip_references=True,url_mode="skip",read_notes=True,han_mode="prefer_vietnamese",
                         frontmatter=True,appendices=True,technical=False,export=True,readings=""):
    from omni_tts_shared.epub import EpubContentOptions
    from omni_tts_core.text.epub_content import parse_han_readings

    return EpubContentOptions(skip_references=bool(skip_references),url_mode=url_mode,read_notes=bool(read_notes),han_mode=han_mode,
        include_frontmatter=bool(frontmatter),include_appendices=bool(appendices),include_technical_notes=bool(technical),
        export_references=bool(export),han_readings=parse_han_readings(readings or ""))


def preview_epub_content(source_files,chapter_start,chapter_end,chapter_index,*content_values):
    from omni_tts_core.text.epub_content import prepare_epub, reading_summary, format_reading_changes, format_han_issues

    try:
        source = next((p for p in _source_paths(source_files) if p.suffix.lower() == ".epub"), None)
        if source is None:
            return "Hãy tải lên một EPUB trước.", "", "", ""
        options = EpubOptions(chapter_start=int(chapter_start),chapter_end=int(chapter_end),content=epub_content_options(*content_values))
        plan = prepare_epub(read_epub(source),options)
        data = plan.chapter_preview(int(chapter_index),max_chars=30000)
        if "error" in data:
            return data["error"], "", "", ""
        status = reading_summary(plan.summary) + "\n" + "\n".join(plan.warnings)
        if plan.han_issues:
            status += "\n" + format_han_issues(plan)
        if data["truncated"]:
            status += "\nBản xem trước giới hạn 30.000 ký tự mỗi cột; khi tạo sách dùng đầy đủ nội dung."
        changes = format_reading_changes(data)
        return status, data["reading_text"] or "Phần này không nằm trong bản đọc theo phạm vi / bộ lọc.", data["original_text"], changes or "Không có thay đổi."
    except (ValueError,OmniTtsError,OSError) as exc:
        return str(exc), "", "", ""


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
    paths.extend(path for field in ("reading_text_path", "reading_report_path", "references_path") if (path := getattr(result,field,None)))
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
        status = "Model đã tải" if item.worker_installed is not True else "Worker + model OK"
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


def _setup_row(item) -> list[Any]:
    action = item.action_label if item.can_run else ""
    if action and item.script_name:
        action = f"{action} ({item.script_name})"
    return [
        _setup_scope_label(item.scope),
        item.label,
        _setup_status_label(item.status),
        action,
        item.detail,
    ]


def _setup_scope_label(value: str) -> str:
    return {
        "environment": "Máy",
        "storage": "Storage",
        "model": "Model",
        "runtime": "Runtime",
        "worker": "Worker",
        "gpu": "GPU",
    }.get(value, value)


def _setup_status_label(value: str) -> str:
    return {
        "ok": "OK",
        "missing": "Thiếu",
        "warning": "Cảnh báo",
        "optional": "Tùy chọn",
        "error": "Lỗi",
    }.get(value, value)


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
