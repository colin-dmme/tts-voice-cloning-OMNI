"""
App Controller - Main application controller.
Bridges the Qwen3-TTS style UI with omni_tts_core engines.
"""
from __future__ import annotations

import os
import io
import threading
import time
import logging
from pathlib import Path
from typing import Optional

import numpy as np
import soundfile as sf

from omni_tts_core.engines.base import TtsEngineRequest, TtsEngineResult
from omni_tts_core.model_registry import ModelRegistry, ModelSpec
from omni_tts_core.model_storage import ModelStorage
from omni_tts_core.service import TtsService
from omni_tts_core.voice_profiles import VoiceProfileManager
from omni_tts_shared.schemas import ModelCapabilities, VoiceProfile

from omni_tts_ui_tkinter.config_manager import ConfigManager
from omni_tts_ui_tkinter.srt_parser import parse_subtitle_file, calculate_total_characters
from omni_tts_ui_tkinter.audio_processor import trim_silence, adjust_speed

logger = logging.getLogger(__name__)

# Minimum text length for TTS generation - shorter text may cause
# model failures (empty audio or reproducing reference audio)
MIN_TEXT_LENGTH = 3


def _save_audio_mp3(audio: np.ndarray, sample_rate: int, output_path: str) -> None:
    """Save audio data as MP3 file via pydub (requires ffmpeg)."""
    from pydub import AudioSegment

    # Write WAV to memory buffer first
    wav_buffer = io.BytesIO()
    sf.write(wav_buffer, audio, sample_rate, format='WAV')
    wav_buffer.seek(0)

    # Convert to MP3
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    audio_seg = AudioSegment.from_wav(wav_buffer)
    audio_seg.export(output_path, format="mp3", bitrate="192k")

class AppController:
    """Main application controller following MVC pattern."""

    def __init__(self, config_manager: ConfigManager):
        self.config = config_manager
        self.service = TtsService()
        self.view = None

        self._is_generating = False
        self._batch_stop_requested = False
        self._batch_thread: Optional[threading.Thread] = None

        logger.info("AppController initialized")

    def set_view(self, view):
        """Set the main window view and connect event handlers."""
        self.view = view
        self._connect_handlers()
        self._load_saved_config()
        logger.debug("View connected and handlers registered")

    def _connect_handlers(self):
        """Connect view event handlers to controller methods."""
        # Voice frame
        self.view.voice_frame.on_model_change = self._on_model_changed
        self.view.voice_frame.on_language_change = self._on_language_changed
        self.view.voice_frame.on_speed_change = self._on_speed_changed
        self.view.voice_frame.on_profile_change = self._on_profile_changed

        # Batch frame
        self.view.batch_frame.on_start = self.start_batch_processing
        self.view.batch_frame.on_stop = self.stop_batch_processing
        self.view.batch_frame.on_input_files_change = self._on_input_files_changed
        self.view.batch_frame.on_column_resize = self._on_column_resize

        # Trim settings
        self.view.trim_frame.on_setting_change = self._on_trim_settings_changed

        # Load voice profiles into both dropdowns
        self._refresh_voice_profiles()

    def _load_saved_config(self):
        """Load saved configuration into view."""
        config = self.config.config

        # Load model selection
        self.view.voice_frame.set_model_by_id(config.model_id)

        # Load voice settings
        self.view.voice_frame.set_language(config.default_language)
        self.view.voice_frame.set_speed(config.default_speed)

        # Restore voice profile selection
        if config.voice_profile_id:
            self.view.voice_frame.set_profile_by_id(config.voice_profile_id)
            self.view.batch_frame.set_default_voice_profile(config.voice_profile_id)

        # Load batch settings
        self.view.batch_frame.set_auto_close(config.auto_close)
        self.view.batch_frame.set_default_speed(config.default_speed)

        # Restore column widths
        if config.column_widths:
            self.view.batch_frame.set_column_widths(config.column_widths)

        # Load trim settings
        self.view.trim_frame.set_settings({
            "enabled": config.trim_enabled,
            "threshold": config.trim_threshold,
            "min_silence": config.trim_min_silence,
            "padding1": config.trim_padding1,
            "padding2": config.trim_padding2
        })

    # ========== MODEL / VOICE SETTINGS ==========

    def _on_model_changed(self, model_id: str):
        self.config.update_model_settings(model_id=model_id)
        self.view.log(f"Model: {model_id}", "INFO")

    def _on_language_changed(self, language_code: str):
        self.config.update_voice_settings(language=language_code)
        self.view.log(f"Ngôn ngữ: {language_code}", "INFO")

    def _on_speed_changed(self, speed: float):
        self.config.config.default_speed = speed
        self.config.save()
        self.view.batch_frame.update_all_speeds(speed)

    def _on_profile_changed(self, profile_id: str):
        """Handle voice profile selection change."""
        self.config.update_voice_settings(voice_profile_id=profile_id or "")
        # Sync default profile to batch frame for new file imports
        self.view.batch_frame.set_default_voice_profile(profile_id or "")
        if profile_id:
            profiles = {p.profile_id: p for p in self.service.voice_profiles.list_profiles()}
            profile = profiles.get(profile_id)
            if profile:
                # Auto-switch language to match profile
                self.view.voice_frame.set_language(profile.language)
                self.config.update_voice_settings(language=profile.language)
                self.view.log(f"Profile: {profile.name} (ngôn ngữ: {profile.language})", "INFO")
        else:
            self.view.log("Profile: Không dùng profile", "INFO")

    def _refresh_voice_profiles(self):
        """Refresh voice profiles in both the voice frame and batch frame."""
        if self.view is None:
            return
        profiles = self.service.voice_profiles.list_profiles()
        self.view.voice_frame.update_profiles(profiles)
        self.view.batch_frame.update_profile_choices(profiles)

    def _on_column_resize(self, col_widths: dict):
        """Save column widths when user resizes columns."""
        self.config.config.column_widths = col_widths
        self.config.save()

    def _on_input_files_changed(self, file_paths: list):
        self.config.update_input_files(file_paths)

    def _on_trim_settings_changed(self, settings: dict):
        self.config.update_trim_settings(**settings)

    # ========== BATCH PROCESSING ==========

    def start_batch_processing(self):
        """Start batch TTS processing for multiple files."""
        model_id = self.view.voice_frame.get_selected_model_id()
        if not model_id:
            self._batch_log("Chưa chọn model!", "ERROR")
            return

        # Validate model is installed
        try:
            spec = self.service.registry.get(model_id)
            if not self.service.storage.is_installed(spec):
                self._batch_log(f"Model chưa được tải: {spec.display_name}. Hãy tải model trước.", "ERROR")
                return
        except Exception as e:
            self._batch_log(f"Lỗi model: {e}", "ERROR")
            return

        # Get per-file settings
        file_settings = self.view.batch_frame.get_file_settings()
        if not file_settings:
            self._batch_log("Chưa thêm file nào! Nhấn 'Thêm file' để thêm.", "ERROR")
            return

        # Validate files exist
        valid_settings = [fs for fs in file_settings if os.path.exists(fs["path"])]
        if not valid_settings:
            self._batch_log("Không có file hợp lệ!", "ERROR")
            return

        # Get global settings
        language = self.view.voice_frame.get_language_code()
        ref_audio = self.view.voice_frame.get_ref_audio()
        ref_text = self.view.voice_frame.get_ref_text()
        auto_retry = self.view.batch_frame.get_auto_retry()
        auto_close = self.view.batch_frame.get_auto_close()
        trim_settings = self.view.trim_frame.get_settings()
        start_index = self.view.batch_frame.get_start_index()

        # Save settings
        self.config.update_auto_close(auto_close)
        self.config.update_voice_settings(language=language)

        # Reset all statuses
        self.view.root.after(0, lambda: self.view.batch_frame.reset_all_status())

        # Start processing
        self._batch_stop_requested = False
        self.view.batch_frame.set_processing(True)

        self._batch_log(f"Bắt đầu batch: {len(valid_settings)} files, model: {spec.display_name}", "INFO")

        self._batch_thread = threading.Thread(
            target=self._multi_file_batch_worker,
            args=(valid_settings, model_id, spec, language,
                  ref_audio, ref_text, trim_settings,
                  auto_retry, auto_close, start_index),
            daemon=True
        )
        self._batch_thread.start()

    def stop_batch_processing(self):
        """Stop batch processing."""
        self._batch_stop_requested = True
        self._batch_log("Đang dừng batch...", "WARNING")

    def _multi_file_batch_worker(
        self, file_settings_list, model_id, spec, language,
        ref_audio, ref_text, trim_settings,
        auto_retry, auto_close, start_index
    ):
        """Worker thread for multi-file batch processing."""
        total_files = len(file_settings_list)
        files_done = 0
        files_failed = 0

        # Get engine
        try:
            engine = self.service._engine_for(spec)
        except Exception as e:
            self._batch_log(f"Không thể khởi tạo engine: {e}", "ERROR")
            self.view.root.after(0, lambda: self.view.batch_frame.set_processing(False))
            return

        for file_idx, file_settings in enumerate(file_settings_list):
            if self._batch_stop_requested:
                for remaining in file_settings_list[file_idx:]:
                    self._update_file_status(remaining["path"], "⏹️")
                break

            input_file = file_settings["path"]
            file_speed = file_settings.get("speed", 1.0)
            file_profile_id = file_settings.get("voice_profile_id", "")

            file_basename = os.path.splitext(os.path.basename(input_file))[0]
            self._batch_log(
                f"━━━ File {file_idx+1}/{total_files}: {os.path.basename(input_file)} "
                f"(speed={file_speed:.2f}x) ━━━", "INFO"
            )
            self._update_file_status(input_file, "🔄")

            # Resolve per-file voice profile for ref audio/text
            file_ref_audio = ref_audio
            file_ref_text = ref_text
            if file_profile_id:
                try:
                    profile = self.service.voice_profiles.get_profile(file_profile_id)
                    if profile and profile.audio_path:
                        file_ref_audio = str(profile.audio_path)
                        file_ref_text = profile.transcript or ""
                        self._batch_log(f"  Profile: {profile.name}", "INFO")
                except Exception:
                    pass  # Fall back to global

            # Parse subtitles from this file
            subtitles = parse_subtitle_file(input_file)
            if not subtitles:
                self._batch_log(f"⚠️ Không tìm thấy nội dung: {os.path.basename(input_file)}", "WARNING")
                self._update_file_status(input_file, "❌ Trống")
                files_failed += 1
                continue

            # Apply start index filter
            subtitles = [s for s in subtitles if s.index >= start_index]
            if not subtitles:
                self._batch_log(f"⚠️ Không có nội dung từ câu {start_index}", "WARNING")
                self._update_file_status(input_file, "❌ Trống")
                files_failed += 1
                continue

            # Output goes to same folder as input file
            input_dir = os.path.dirname(input_file)
            voice_folder = os.path.join(input_dir, f"{file_basename}_Voice")
            trim_folder1 = os.path.join(input_dir, f"{file_basename}_Voice_Trim_{trim_settings['padding1']}")
            trim_folder2 = os.path.join(input_dir, f"{file_basename}_Voice_Trim_{trim_settings['padding2']}")

            os.makedirs(voice_folder, exist_ok=True)
            if trim_settings["enabled"]:
                os.makedirs(trim_folder1, exist_ok=True)
                os.makedirs(trim_folder2, exist_ok=True)

            # Process this file's subtitles
            file_success = self._process_single_file(
                engine, subtitles, voice_folder, trim_folder1, trim_folder2,
                model_id, language, file_ref_audio, file_ref_text,
                trim_settings, auto_retry, file_speed,
                file_idx, total_files
            )

            if file_success:
                self._update_file_status(input_file, "✅ Xong")
                files_done += 1
            else:
                self._update_file_status(input_file, "❌ Lỗi")
                files_failed += 1

        # Done
        final_msg = f"Batch hoàn tất: {files_done}/{total_files} files xong"
        if files_failed > 0:
            final_msg += f", {files_failed} lỗi"
        self._update_batch_ui(total_files, total_files, final_msg)
        self._batch_log(final_msg, "SUCCESS" if files_failed == 0 else "WARNING")

        self.view.root.after(0, lambda: self.view.batch_frame.set_processing(False))

        if auto_close and files_failed == 0 and not self._batch_stop_requested:
            self._batch_log("Tự tắt sau 3 giây...", "INFO")
            self.view.root.after(3000, self.view.root.destroy)

    def _process_single_file(
        self, engine, subtitles, voice_folder, trim_folder1, trim_folder2,
        model_id, language, ref_audio, ref_text,
        trim_settings, auto_retry, speed,
        file_idx, total_files
    ) -> bool:
        """Process subtitles from a single file. Returns True if all succeeded."""
        total = len(subtitles)
        success_count = 0
        failed = []

        total_chars = calculate_total_characters(subtitles)
        self._batch_log(f"  {total} items, {total_chars} chars", "INFO")

        # Prepare reference audio path
        ref_path = Path(ref_audio) if ref_audio else None

        for i, sub in enumerate(subtitles):
            if self._batch_stop_requested:
                return False

            # Update progress
            overall_msg = f"File {file_idx+1}/{total_files} | Item {i+1}/{total}: #{sub.index}"
            self._update_batch_ui(
                file_idx * 100 + int((i / total) * 100),
                total_files * 100,
                overall_msg
            )

            # Output path (MP3)
            output_path = os.path.join(voice_folder, f"{sub.index:04d}.mp3")

            # Skip if exists
            if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                if trim_settings["enabled"]:
                    self._do_trim(output_path, trim_folder1, trim_folder2, sub.index, trim_settings)
                self._batch_log(f"  Skip #{sub.index} (đã có)", "INFO")
                success_count += 1
                continue

            # Generate TTS
            max_retries = 3
            generated = False

            for retry in range(max_retries):
                try:
                    gen_start = time.time()
                    self._batch_log(f"  🔊 #{sub.index} ({len(sub.content)} chars)...", "INFO")

                    # Pad short text to avoid model generation failures
                    gen_text = _pad_short_text(sub.content)

                    request = TtsEngineRequest(
                        text=gen_text,
                        language=language,
                        reference_audio_path=ref_path,
                        reference_text=ref_text or None,
                        speed=1.0,  # Speed applied via FFmpeg after
                        pitch_shift=0.0,
                    )

                    result = engine.generate(request)
                    gen_elapsed = time.time() - gen_start

                    # Save audio as MP3
                    os.makedirs(os.path.dirname(output_path), exist_ok=True)
                    _save_audio_mp3(result.audio, result.sample_rate, output_path)

                    # Apply speed adjustment
                    if speed != 1.0:
                        adjust_speed(output_path, speed)

                    # Trim
                    if trim_settings["enabled"]:
                        self._do_trim(output_path, trim_folder1, trim_folder2, sub.index, trim_settings)

                    success_count += 1
                    generated = True
                    self._batch_log(f"  ✅ #{sub.index} ({gen_elapsed:.1f}s)", "SUCCESS")
                    break

                except Exception as e:
                    if retry < max_retries - 1:
                        self._batch_log(f"  ⚠️ #{sub.index}: Retry {retry+1}/{max_retries} ({e})", "WARNING")
                    else:
                        self._batch_log(f"  ❌ Lỗi #{sub.index}: {e}", "ERROR")
                        failed.append(sub)

        # Retry failed items
        if auto_retry and failed and not self._batch_stop_requested:
            self._batch_log(f"  Retry {len(failed)} items lỗi...", "WARNING")
            for sub in failed[:]:
                if self._batch_stop_requested:
                    break
                try:
                    output_path = os.path.join(voice_folder, f"{sub.index:04d}.mp3")
                    ref_path_retry = Path(ref_audio) if ref_audio else None
                    gen_text = _pad_short_text(sub.content)
                    request = TtsEngineRequest(
                        text=gen_text,
                        language=language,
                        reference_audio_path=ref_path_retry,
                        reference_text=ref_text or None,
                        speed=1.0,
                        pitch_shift=0.0,
                    )
                    result = engine.generate(request)
                    _save_audio_mp3(result.audio, result.sample_rate, output_path)
                    if trim_settings["enabled"]:
                        self._do_trim(output_path, trim_folder1, trim_folder2, sub.index, trim_settings)
                    success_count += 1
                    failed.remove(sub)
                    self._batch_log(f"  ✅ Retry #{sub.index} thành công", "SUCCESS")
                except Exception as e:
                    self._batch_log(f"  ❌ Retry #{sub.index} lỗi: {e}", "ERROR")

        self._batch_log(f"  File xong: {success_count}/{total} thành công", "INFO")
        return len(failed) == 0

    def _do_trim(self, source_path, trim_folder1, trim_folder2, index, trim_settings):
        """Apply dual trim to an audio file."""
        ext = os.path.splitext(source_path)[1] or ".mp3"
        filename = f"{index:04d}{ext}"
        trim_path1 = os.path.join(trim_folder1, filename)
        trim_path2 = os.path.join(trim_folder2, filename)

        needs1 = not os.path.exists(trim_path1) or os.path.getsize(trim_path1) == 0
        needs2 = not os.path.exists(trim_path2) or os.path.getsize(trim_path2) == 0

        if needs1:
            trim_silence(source_path, trim_path1,
                silence_thresh=trim_settings["threshold"],
                min_silence_len=trim_settings["min_silence"],
                padding_ms=trim_settings["padding1"])
        if needs2:
            trim_silence(source_path, trim_path2,
                silence_thresh=trim_settings["threshold"],
                min_silence_len=trim_settings["min_silence"],
                padding_ms=trim_settings["padding2"])

    def _update_file_status(self, file_path: str, status: str):
        self.view.root.after(0, lambda: self.view.batch_frame.update_file_status(file_path, status))

    def _batch_log(self, message: str, level: str = "INFO"):
        def _log():
            self.view.log(message, level)
        self.view.root.after(0, _log)

    def _update_batch_ui(self, current, total, message):
        self.view.root.after(0, lambda: self.view.batch_frame.set_progress(current, total, message))

    def on_window_close(self):
        """Handle window close - save geometry."""
        if self.view:
            x, y, width, height = self.view.get_geometry()
            self.config.update_window_geometry(x, y, width, height)
            logger.info("Window geometry saved")

    # ========== MODEL & VOICE PROFILE MANAGEMENT ==========

    def model_choices(self) -> list:
        """Return list of (display_name, model_id) for TTS models."""
        return [
            (item.display_name, item.model_id)
            for item in self.service.list_tts_models()
            if item.installed
        ]

    def all_models(self):
        return self.service.list_models()

    def all_voice_profiles(self):
        return self.service.list_voice_profiles()

    def save_voice_profile(self, **kwargs):
        return self.service.save_voice_profile(**kwargs)

    def delete_voice_profile(self, profile_id: str):
        self.service.delete_voice_profile(profile_id)
        return "Đã xóa profile giọng."

    def download_model(self, model_id: str):
        def _log(msg):
            if self.view:
                self.view.root.after(0, lambda m=msg: self.view.log(m, "INFO"))
        status = self.service.download_model(model_id, log_callback=_log)
        # Refresh model choices in voice frame after download
        if self.view:
            choices = self.model_choices()
            self.view.root.after(0, lambda: self.view.voice_frame.update_model_choices(choices))
        return f"Đã tải xong: {status.display_name}"

    def download_required_models(self):
        def _log(msg):
            if self.view:
                self.view.root.after(0, lambda m=msg: self.view.log(m, "INFO"))
        downloaded = self.service.download_missing_required_models(log_callback=_log)
        if not downloaded:
            return "Các model bắt buộc đã có sẵn."
        # Refresh model choices in voice frame after download
        if self.view:
            choices = self.model_choices()
            self.view.root.after(0, lambda: self.view.voice_frame.update_model_choices(choices))
        names = ", ".join(item.display_name for item in downloaded)
        return f"Đã tải xong: {names}."

    def runtime_status_text(self, model_id: str) -> str:
        status = self.service.runtime_status_for(model_id)
        installed = "đã cài" if status.installed else "chưa cài"
        gpu = "có GPU" if status.gpu_available else "không GPU"
        device = status.actual_device
        detail = f" - {status.device_name}" if status.device_name else ""
        return f"{status.display_name}: {installed}, {gpu}, {device}{detail}. {status.message}"

    def startup_notice(self) -> str:
        missing = self.service.missing_required_models()
        if not missing:
            return "Sẵn sàng."
        names = ", ".join(item.display_name for item in missing)
        return f"Cần tải model: {names}."


def _pad_short_text(text: str) -> str:
    """
    Pad text shorter than MIN_TEXT_LENGTH with spaces.
    Some TTS models fail or produce garbage output when text is too short.
    """
    text = text.strip()
    if len(text) < MIN_TEXT_LENGTH:
        text = text + " " * (MIN_TEXT_LENGTH - len(text))
        logger.info(f"Padded short text to {len(text)} chars: '{text}'")
    return text

