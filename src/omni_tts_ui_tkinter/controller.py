from __future__ import annotations

from pathlib import Path
from threading import Event

from omni_tts_license.local_signed import LocalSignedLicenseProvider
from omni_tts_license.models import LicenseStatus
from omni_tts_core.progress import ProgressCallback, ProgressEvent, check_cancel
from omni_tts_core.model_registry import ModelSpec
from omni_tts_core.runtime_devices import RUNTIME_TARGET_CHOICES, runtime_target_label
from omni_tts_core.service import TtsService
from omni_tts_core.voice_profile_policy import ProfileCompatibility
from omni_tts_shared.errors import OmniTtsError
from omni_tts_shared.schemas import (
    GenerateSpeechResult,
    ModelCapabilities,
    ModelStatus,
    ProfileSaveWarning,
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
        return [
            (_model_choice_label(item), item.model_id)
            for item in self.service.registry.tts_models()
        ]

    def model_choice_info(self, model_id: str) -> str:
        spec = self.service.registry.get(model_id)
        info = spec.catalog_info
        category = _category_label(str(info.get("category") or ""))
        origin = _origin_label(str(info.get("origin") or ""))
        variant = str(info.get("variant") or "").strip()
        base_model = str(info.get("base_model") or "").strip()
        risk = _risk_label(str(info.get("risk") or ""))
        highlight = str(info.get("highlight") or "").strip()
        recommend = str(info.get("recommend_for") or "").strip()
        parts = [f"Nguồn: {origin}" if origin else f"Nhóm: {category}"]
        if origin and category and category != origin:
            parts.append(f"Nhóm: {category}")
        if variant:
            parts.append(variant)
        if base_model:
            parts.append(f"Base: {base_model}")
        if risk:
            parts.append(f"Mức: {risk}")
        if highlight:
            parts.append(highlight)
        if recommend:
            parts.append(recommend)
        elif spec.notes:
            parts.append(spec.notes)
        return " · ".join(parts)

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
    ) -> tuple[VoiceProfile, list[ProfileSaveWarning]]:
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

    def profile_quality_for_model(self, profile_id: str, model_id: str) -> ProfileCompatibility:
        return self.service.profile_quality_for_model(profile_id, model_id)

    def add_voice_profile_sample(
        self,
        profile_id: str,
        audio_path: Path,
        transcript: str = "",
        role: str = "neutral",
        sample_id: str | None = None,
    ) -> tuple:
        return self.service.add_voice_profile_sample(
            profile_id=profile_id,
            audio_path=audio_path,
            transcript=transcript,
            role=role,
            sample_id=sample_id,
        )

    def remove_voice_profile_sample(self, profile_id: str, sample_index: int):
        return self.service.remove_voice_profile_sample(profile_id, sample_index)

    def set_voice_profile_default_sample(self, profile_id: str, sample_id: str):
        return self.service.set_voice_profile_default_sample(profile_id, sample_id)

    def all_models(self) -> list[ModelStatus]:
        return self.service.list_models()

    def runtime_statuses(self) -> list[RuntimeStatus]:
        return self.service.list_runtime_statuses()

    def runtime_target_choices(self) -> list[tuple[str, str]]:
        return [(label, value) for label, value in RUNTIME_TARGET_CHOICES]

    def runtime_target_label(self, value: str | None) -> str:
        return runtime_target_label(value)

    def runtime_device_label(self, value: str | None) -> str:
        return _runtime_device_label(value)

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
        gpu = "có CUDA" if status.gpu_available else "chưa có CUDA"
        device = _runtime_device_label(status.actual_device)
        detail = _runtime_device_detail(status.actual_device, status.device_name)
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

    def install_gpu_for_model(self, model_id: str) -> str:
        return self.service.install_gpu_acceleration(model_id)

    def open_model_catalog(self) -> None:
        self.service.open_model_catalog()

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


def _model_choice_label(spec: ModelSpec) -> str:
    badges = _model_badges(spec.catalog_info)
    if not badges:
        return spec.display_name
    suffix = " ".join(f"[{item}]" for item in badges)
    return f"{spec.display_name} {suffix}"


def _model_badges(info: dict) -> list[str]:
    badges: list[str] = []
    origin = _origin_badge(str(info.get("origin") or ""))
    category = _category_badge(str(info.get("category") or ""))
    variant = str(info.get("variant_badge") or "").strip()
    risk = _risk_badge(str(info.get("risk") or ""))
    if origin:
        badges.append(origin)
    elif category:
        badges.append(category)
    if variant:
        badges.append(variant)
    if risk and risk not in badges:
        badges.append(risk)
    return badges


def _category_badge(category: str) -> str:
    return {
        "official-cpu": "Official",
        "official-gpu": "Official",
        "community": "Community",
        "experimental": "Debug/Legacy",
        "multilingual": "Multilingual",
        "support": "Support",
    }.get(category, "Custom" if category else "")


def _origin_badge(origin: str) -> str:
    return {
        "official": "Official",
        "community": "Community",
        "custom": "Custom",
    }.get(origin, "")


def _risk_badge(risk: str) -> str:
    return {
        "test": "Test",
        "checkpoint": "Checkpoint",
        "debug": "Debug",
    }.get(risk, "")


def _category_label(category: str) -> str:
    return {
        "official-cpu": "Official",
        "official-gpu": "Official",
        "community": "Community",
        "experimental": "Debug/Legacy",
        "multilingual": "Multilingual",
        "support": "Support",
    }.get(category, "Custom/Unknown" if category else "")


def _origin_label(origin: str) -> str:
    return {
        "official": "Official",
        "community": "Community",
        "custom": "Custom",
    }.get(origin, "")


def _risk_label(risk: str) -> str:
    return {
        "stable": "Ổn định",
        "test": "Test A/B",
        "checkpoint": "Checkpoint thô",
        "debug": "Debug",
    }.get(risk, "")


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


def _runtime_device_detail(actual_device: str | None, device_name: str) -> str:
    if not device_name:
        return ""
    label = _runtime_device_label(actual_device)
    if actual_device in {"cpu", "auto-cpu", "cuda-unavailable", "cuda-partial"}:
        return ""
    if actual_device in {"cuda", "auto-cuda"} and device_name.startswith("CUDA - "):
        return f" - {device_name.removeprefix('CUDA - ')}"
    return f" - {device_name}"


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
