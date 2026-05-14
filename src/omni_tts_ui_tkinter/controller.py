from __future__ import annotations

from pathlib import Path
from threading import Event

from omni_tts_license.local_signed import LocalSignedLicenseProvider
from omni_tts_license.models import LicenseStatus
from omni_tts_core.progress import ProgressCallback, ProgressEvent, check_cancel
from omni_tts_core.service import TtsService
from omni_tts_shared.errors import OmniTtsError
from omni_tts_shared.schemas import (
    GenerateSpeechResult,
    ModelCapabilities,
    ModelStatus,
    RuntimeStatus,
    VoiceProfile,
)
from omni_tts_ui_tkinter.state import UiSettings


class TkinterController:
    def __init__(
        self,
        service: TtsService | None = None,
        license_provider: LocalSignedLicenseProvider | None = None,
    ) -> None:
        self.service = service or TtsService()
        self.license_provider = license_provider or LocalSignedLicenseProvider()

    def model_choices(self) -> list[tuple[str, str]]:
        return [(item.display_name, item.model_id) for item in self.service.list_tts_models()]

    def voice_profile_choices(self) -> list[tuple[str, str]]:
        return [(item.name, item.profile_id) for item in self.service.list_voice_profiles()]

    def all_voice_profiles(self) -> list[VoiceProfile]:
        return self.service.list_voice_profiles()

    def save_voice_profile(
        self,
        name: str,
        audio_path: Path,
        transcript: str,
        language: str,
        project: str,
        notes: str,
        profile_id: str | None = None,
    ) -> VoiceProfile:
        return self.service.save_voice_profile(
            name=name,
            audio_path=audio_path,
            transcript=transcript,
            language=language,
            project=project,
            notes=notes,
            profile_id=profile_id,
        )

    def delete_voice_profile(self, profile_id: str) -> str:
        self.service.delete_voice_profile(profile_id)
        return "Đã xóa profile giọng."

    def all_models(self) -> list[ModelStatus]:
        return self.service.list_models()

    def runtime_statuses(self) -> list[RuntimeStatus]:
        return self.service.list_runtime_statuses()

    def model_capabilities(self, model_id: str) -> ModelCapabilities:
        return self.service.model_capabilities(model_id)

    def model_supports_codec(self, model_id: str) -> bool:
        return self.service.supports_vieneu_codec(model_id)

    def model_supports_sampling(self, model_id: str) -> bool:
        return self.service.supports_vieneu_sampling(model_id)

    def default_vieneu_temperature(self, model_id: str) -> float:
        return self.service.default_vieneu_temperature(model_id)

    def default_vieneu_top_k(self, model_id: str) -> int:
        return self.service.default_vieneu_top_k(model_id)

    def vieneu_codec_choices(self, model_id: str) -> list[tuple[str, str]]:
        return self.service.list_vieneu_codecs(model_id)

    def default_vieneu_codec_repo(self, model_id: str) -> str | None:
        return self.service.default_vieneu_codec_repo(model_id)

    def valid_vieneu_codec_repo(self, model_id: str, codec_repo: str | None) -> str | None:
        return self.service.valid_vieneu_codec_repo(model_id, codec_repo)

    def voice_preset_choices(self, model_id: str, include_none: bool = True) -> list[tuple[str, str]]:
        return self.service.list_voice_presets(model_id, include_none=include_none)

    def default_voice_preset_id(self, model_id: str) -> str | None:
        return self.service.default_voice_preset_id(model_id)

    def has_voice_presets(self, model_id: str) -> bool:
        return self.service.has_voice_presets(model_id)

    def valid_voice_preset_id(self, model_id: str, preset_id: str | None) -> str | None:
        return self.service.valid_voice_preset_id(model_id, preset_id)

    def runtime_status_text(self, model_id: str) -> str:
        status = self.service.runtime_status_for(model_id)
        installed = "đã cài" if status.installed else "chưa cài"
        gpu = "có GPU" if status.gpu_available else "không dùng GPU"
        device = status.actual_device
        detail = f" - {status.device_name}" if status.device_name else ""
        return f"{status.display_name}: {installed}, {gpu}, chạy bằng {device}{detail}. {status.message}"

    def startup_notice(self) -> str:
        license_status = self.license_status()
        if not license_status.valid:
            return license_status.message
        missing = self.service.missing_required_models()
        if not missing:
            return "Sẵn sàng. Các model bắt buộc đã có trong dự án."
        names = ", ".join(item.display_name for item in missing)
        return f"Cần tải model bắt buộc còn thiếu: {names}."

    def download_model(self, model_id: str) -> str:
        status = self.service.download_model(model_id)
        return f"Đã tải xong: {status.display_name}"

    def download_required_models(self) -> str:
        downloaded = self.service.download_missing_required_models()
        if not downloaded:
            return "Các model bắt buộc đã có sẵn."
        names = ", ".join(item.display_name for item in downloaded)
        return f"Đã tải xong model bắt buộc: {names}."

    def generate_text(
        self,
        text: str,
        settings: UiSettings,
        progress_callback: ProgressCallback | None = None,
        cancel_event: Event | None = None,
    ) -> GenerateSpeechResult:
        if not text.strip():
            raise OmniTtsError("Bạn chưa nhập nội dung cần đọc.")
        self.validate_license_for_model(settings.model_id)
        return self.service.generate_audio(settings.to_request(text), progress_callback, cancel_event)

    def generate_files(
        self,
        source_paths: list[Path],
        settings: UiSettings,
        progress_callback: ProgressCallback | None = None,
        cancel_event: Event | None = None,
    ) -> list[GenerateSpeechResult]:
        if not source_paths:
            raise OmniTtsError("Bạn chưa chọn file nguồn.")
        self.validate_license_for_model(settings.model_id)
        results = []
        template = settings.to_request("Nội dung sẽ được đọc từ file nguồn.")
        total_files = len(source_paths)
        for file_index, source_path in enumerate(source_paths, start=1):
            check_cancel(cancel_event)
            results.append(
                self.service.generate_from_source_file(
                    source_path=source_path,
                    request_template=template,
                    output_dir=settings.output_dir,
                    progress_callback=_file_progress(
                        progress_callback,
                        file_index,
                        total_files,
                        source_path.name,
                    ),
                    cancel_event=cancel_event,
                )
            )
        return results

    def license_status(self) -> LicenseStatus:
        return self.license_provider.get_status()

    def current_device_id(self) -> str:
        return self.license_provider.current_device_id()

    def install_license(self, source_path: Path) -> LicenseStatus:
        return self.license_provider.install_license(source_path)

    def validate_license_for_model(self, model_id: str) -> None:
        status = self.license_status()
        if not status.valid:
            raise OmniTtsError(status.message)
        for feature in _required_features_for_model(model_id):
            if not status.feature_enabled(feature):
                raise OmniTtsError(f"License hiện tại chưa bật tính năng: {feature}.")


def format_result(result: GenerateSpeechResult) -> str:
    if result.item_audio_paths:
        joined = "\n".join(str(path) for path in result.item_audio_paths)
        srt_line = ""
        if result.item_srt_paths:
            srt_joined = "\n".join(str(path) for path in result.item_srt_paths)
            srt_line = f"\nSRT:\n{srt_joined}"
        return (
            f"{result.message}\n"
            f"Số đoạn nhỏ: {result.segment_count}, tổng {result.duration_seconds:.1f} giây\n"
            f"Audio:\n{joined}{srt_line}"
        )
    srt_line = f"\nSRT: {result.srt_path}" if result.srt_path else ""
    return (
        f"Hoàn tất {result.segment_count} đoạn, {result.duration_seconds:.1f} giây\n"
        f"WAV: {result.audio_path}{srt_line}"
    )


def _file_progress(
    callback: ProgressCallback | None,
    file_index: int,
    total_files: int,
    file_name: str,
) -> ProgressCallback | None:
    if callback is None:
        return None

    def scaled(event: ProgressEvent) -> None:
        file_progress = event.current / event.total if event.total > 0 else 0.0
        callback(
            ProgressEvent(
                message=f"File {file_index}/{total_files} ({file_name}): {event.message}",
                current=(file_index - 1) + file_progress,
                total=total_files,
            )
        )

    return scaled


def _required_features_for_model(model_id: str) -> list[str]:
    features = ["tts"]
    if model_id.startswith("vieneu"):
        features.append("vieneu")
    elif model_id.startswith("qwen"):
        features.append("qwen")
    return features
