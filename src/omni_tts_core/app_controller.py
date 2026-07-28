"""AppController: the single UI-facing facade over TtsService + licensing.

Ported from the tkinter controller but decoupled from any GUI toolkit and from
GenerationSettings (the UI-agnostic form snapshot). A GUI holds one
AppController and never talks to TtsService directly.

The optional ``safety_gate`` is consulted before text generation and before
each queued file so GPU preflight protection applies globally, for every CUDA
provider — not only Chatterbox.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from threading import Event, Lock
from typing import Callable, Protocol

from omni_tts_core.file_queue import FileQueueOutputManifest, FileQueueStatus
from omni_tts_core.higgs.endpoint_capabilities import (
    endpoint_capabilities,
    endpoint_preset_voices,
)
from omni_tts_core.higgs.script import (
    HiggsScriptAnalysis,
    compile_higgs_chunks,
    validate_higgs_script,
)
from omni_tts_core.gpu_safety import gpu_temperature_guidance
from omni_tts_core.generation_concurrency import GenerationCoordinator
from omni_tts_core.media_player import MediaPlayerService
from omni_tts_core.progress import ProgressCallback, ProgressEvent, check_cancel
from omni_tts_core.remote.higgs_sglang import EndpointCheckResult, HiggsSglangClient
from omni_tts_core.runtime_devices import RUNTIME_TARGET_CHOICES, runtime_target_label
from omni_tts_core.service import TtsService
from omni_tts_core.text.source_reader import text_units_from_blank_lines
from omni_tts_core.ui_presenters import labels, model_groups
from omni_tts_core.ui_presenters.control_policy import (
    GenerationControlPolicy,
    build_policy,
)
from omni_tts_core.ui_presenters.licensing import required_features_for_model
from omni_tts_core.ui_presenters.model_actions import ModelActionPolicy, build_action_policy
from omni_tts_core.ui_presenters.settings_state import GenerationSettings
from omni_tts_core.voice_profile_policy import ProfileCompatibility
from omni_tts_shared.errors import GenerationCancelled, GpuSafetyError, OmniTtsError
from omni_tts_shared.schemas import (
    GenerateSpeechResult,
    GenerationFormDescriptor,
    ModelCapabilities,
    ModelStatus,
    ProfileSaveWarning,
    RuntimeStatus,
    SetupTaskStatus,
    VoiceProfile,
)


@dataclass(frozen=True)
class FileGenerationEvent:
    item_id: str
    source_path: Path
    status: FileQueueStatus
    progress_percent: float = 0.0
    message: str = ""
    result: GenerateSpeechResult | None = None
    error: str = ""


@dataclass(frozen=True)
class FileGenerationOutcome:
    item_id: str
    source_path: Path
    status: FileQueueStatus
    result: GenerateSpeechResult | None = None
    error: str = ""


FileEventCallback = Callable[[FileGenerationEvent], None]
StatusCallback = Callable[[str], None]


class SafetyGateProtocol(Protocol):
    def wait_before_generation(
        self,
        settings: GenerationSettings,
        cancel_event: Event | None,
        status_callback: StatusCallback | None,
    ) -> None: ...


class LicenseProviderProtocol(Protocol):
    def get_status(self): ...

    def current_device_id(self) -> str: ...

    def install_license(self, source_path: Path): ...


class AppController:
    def __init__(
        self,
        service: TtsService | None = None,
        license_provider: LicenseProviderProtocol | None = None,
        safety_gate: SafetyGateProtocol | None = None,
        media_player: MediaPlayerService | None = None,
        generation_coordinator: GenerationCoordinator | None = None,
    ) -> None:
        self.service = service or TtsService()
        self.license_provider = license_provider or _default_license_provider()
        self.safety_gate = safety_gate
        self.media_player = media_player or MediaPlayerService()
        self.generation_coordinator = generation_coordinator or GenerationCoordinator(
            self.service
        )

    # --- Model catalog / choices -------------------------------------------

    def model_choices(self, provider_id: str | None = None) -> list[tuple[str, str]]:
        """Model choices, optionally limited to one provider."""
        return model_groups.models_for_provider(self.service.registry.tts_models(), provider_id)

    def provider_choices(self) -> list[tuple[str, str]]:
        return model_groups.provider_choices(self.service.registry.tts_models())

    def provider_of_model(self, model_id: str | None) -> str:
        return model_groups.provider_of_model(self.service.registry.tts_models(), model_id)

    def model_choice_info(self, model_id: str) -> str:
        return labels.model_choice_info(self.service.registry.get(model_id))

    def all_models(self, provider_id: str | None = None) -> list[ModelStatus]:
        """Model statuses grouped by provider, optionally limited to one."""
        items = model_groups.filter_by_provider(self.service.list_models(), provider_id)
        return model_groups.sort_by_provider(items)

    def model_provider_choices(self) -> list[tuple[str, str]]:
        """Provider filter choices counted over the full model catalog."""
        return model_groups.provider_choices(self.service.list_models())

    def provider_display_label(self, provider_id: str) -> str:
        return model_groups.provider_label(provider_id)

    def model_action_policy(self, selected: list[ModelStatus]) -> ModelActionPolicy:
        """Which management buttons apply to the current table selection."""
        return build_action_policy(selected)

    def runtime_statuses(self) -> list[RuntimeStatus]:
        return self.service.list_runtime_statuses()

    def setup_statuses(self, model_id: str | None = None) -> list[SetupTaskStatus]:
        return self.service.setup_statuses(model_id)

    def model_capabilities(self, model_id: str) -> ModelCapabilities:
        return self.service.model_capabilities(model_id)

    def generation_form_descriptor(
        self,
        model_id: str,
        preferred_mode: str | None = None,
    ) -> GenerationFormDescriptor:
        return self.service.generation_form_descriptor(model_id, preferred_mode)

    def provider_of(self, model_id: str) -> str:
        return self.service.registry.get(model_id).provider

    def control_policy(self, model_id: str) -> GenerationControlPolicy:
        """Which generation controls this model actually honours."""
        return build_policy(
            spec=self.service.registry.get(model_id),
            capabilities=self.service.model_capabilities(model_id),
            runtime_status=self.service.runtime_status_for(model_id),
            supports_codec=self.service.supports_vieneu_codec(model_id),
            supports_sampling=self.service.supports_vieneu_sampling(model_id),
            supports_f5=self.service.supports_f5_settings(model_id),
            supports_chatterbox=self.service.supports_chatterbox_settings(model_id),
        )

    # --- Runtime devices ----------------------------------------------------

    def runtime_target_choices(self) -> list[tuple[str, str]]:
        return [(label, value) for label, value in RUNTIME_TARGET_CHOICES]

    def runtime_target_label(self, value: str | None) -> str:
        return runtime_target_label(value)

    def runtime_status_text(self, model_id: str) -> str:
        return labels.runtime_status_text(self.service.runtime_status_for(model_id))

    def runtime_status_for(self, model_id: str) -> RuntimeStatus:
        return self.service.runtime_status_for(model_id)

    # --- Provider-specific capabilities ------------------------------------

    def model_supports_codec(self, model_id: str) -> bool:
        return self.service.supports_vieneu_codec(model_id)

    def model_supports_sampling(self, model_id: str) -> bool:
        return self.service.supports_vieneu_sampling(model_id)

    def default_vieneu_temperature(self, model_id: str) -> float:
        return self.service.default_vieneu_temperature(model_id)

    def default_vieneu_top_k(self, model_id: str) -> int:
        return self.service.default_vieneu_top_k(model_id)

    def model_supports_f5_settings(self, model_id: str) -> bool:
        return self.service.supports_f5_settings(model_id)

    def default_f5_settings(self, model_id: str) -> dict[str, object]:
        return self.service.default_f5_settings(model_id)

    def model_supports_chatterbox_settings(self, model_id: str) -> bool:
        return self.service.supports_chatterbox_settings(model_id)

    def default_chatterbox_settings(self, model_id: str) -> dict[str, object]:
        return self.service.default_chatterbox_settings(model_id)

    def gpu_temperature_guidance(self) -> str:
        return gpu_temperature_guidance()

    def check_higgs_endpoint(self, settings: GenerationSettings) -> EndpointCheckResult:
        """Check health/model discovery using the same core settings as generation."""
        request = settings.to_request("Kiểm tra kết nối")
        if request.remote_endpoint is None or request.higgs is None:
            raise OmniTtsError("Thiếu cấu hình Higgs Remote.")
        return HiggsSglangClient(request.remote_endpoint, request.higgs).check()

    def higgs_endpoint_capabilities(self, settings: GenerationSettings):
        return endpoint_capabilities(settings.remote_api_flavor)

    def analyze_higgs_script(self, text: str) -> HiggsScriptAnalysis:
        return validate_higgs_script(text)

    def preview_higgs_script(
        self, text: str, settings: GenerationSettings
    ) -> list[str]:
        if self.provider_of(settings.model_id) != "higgs_remote":
            raise OmniTtsError("Chỉ model Higgs mới biên dịch Higgs Script.")
        request = settings.to_request(text)
        chunks: list[str] = []
        for unit in text_units_from_blank_lines(text):
            chunks.extend(
                compile_higgs_chunks(
                    unit.text,
                    request.language,
                    request.max_chunk_chars,
                    request.higgs,
                )
            )
        return chunks

    def higgs_custom_voice_choices(
        self, settings: GenerationSettings
    ) -> list[tuple[str, str]]:
        if self.provider_of(settings.model_id) != "higgs_remote":
            return []
        choices = list(endpoint_preset_voices(settings.remote_api_flavor))
        if not endpoint_capabilities(
            settings.remote_api_flavor
        ).supports_custom_voice_create:
            return choices
        choices.extend(
            (f"{voice.title} · Custom Higgs", voice.voice_id)
            for voice in self.service.list_higgs_custom_voices(
                settings.remote_endpoint_id
            )
        )
        return choices

    def create_higgs_custom_voice(
        self,
        settings: GenerationSettings,
        profile_id: str,
        title: str,
    ):
        if not endpoint_capabilities(
            settings.remote_api_flavor
        ).supports_custom_voice_create:
            raise OmniTtsError(
                "Endpoint hiện tại không khai báo API tạo Custom Voice."
            )
        request = settings.to_request("Tạo Custom Voice")
        if request.remote_endpoint is None:
            raise OmniTtsError("Thiếu cấu hình endpoint Higgs.")
        return self.service.create_higgs_custom_voice(
            endpoint=request.remote_endpoint,
            profile_id=profile_id,
            title=title,
        )

    def vieneu_codec_choices(self, model_id: str) -> list[tuple[str, str]]:
        return self.service.list_vieneu_codecs(model_id)

    def default_vieneu_codec_repo(self, model_id: str) -> str | None:
        return self.service.default_vieneu_codec_repo(model_id)

    def valid_vieneu_codec_repo(self, model_id: str, codec_repo: str | None) -> str | None:
        return self.service.valid_vieneu_codec_repo(model_id, codec_repo)

    def voice_preset_choices(
        self, model_id: str, include_none: bool = True
    ) -> list[tuple[str, str]]:
        return self.service.list_voice_presets(model_id, include_none=include_none)

    def default_voice_preset_id(self, model_id: str) -> str | None:
        return self.service.default_voice_preset_id(model_id)

    def has_voice_presets(self, model_id: str) -> bool:
        return self.service.has_voice_presets(model_id)

    def valid_voice_preset_id(self, model_id: str, preset_id: str | None) -> str | None:
        return self.service.valid_voice_preset_id(model_id, preset_id)

    # --- Voice profiles -----------------------------------------------------

    def voice_profile_choices(self) -> list[tuple[str, str]]:
        return [(item.name, item.profile_id) for item in self.service.list_voice_profiles()]

    def all_voice_profiles(self) -> list[VoiceProfile]:
        return self.service.list_voice_profiles()

    def voice_profile(self, profile_id: str) -> VoiceProfile:
        return self.service.get_voice_profile(profile_id)

    def play_audio_file(self, path: Path | str | None) -> Path:
        """Open any audio file in the OS player — used for not-yet-saved samples."""
        return self.media_player.play_first_available(
            [path],
            missing_message="Không tìm thấy file audio này trên đĩa.",
            empty_message="Chưa chọn file audio để nghe.",
        )

    def play_voice_profile_sample(
        self, profile_id: str, sample_id: str | None = None
    ) -> Path:
        """Open a profile's reference audio in the OS player (no TTS run)."""
        return self.media_player.play_profile(
            self.service.get_voice_profile(profile_id), sample_id
        )

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

    # --- Setup / installation ----------------------------------------------

    def startup_notice(self) -> str:
        status = self.license_status()
        if not status.valid:
            return status.message
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

    def model_removal_preview(self, model_id: str) -> str:
        return self.service.model_removal_preview(model_id)

    def remove_model(self, model_id: str) -> str:
        status = self.service.remove_model(model_id)
        return (
            f"Đã gỡ phần lưu trữ riêng của {status.display_name}. "
            "Worker dùng chung vẫn được giữ; model có thể tải lại khi cần."
        )

    def open_model_storage(self, model_id: str) -> None:
        spec = self.service.registry.get(model_id)
        status = self.service.storage.status_for(spec)
        path = status.storage_path or spec.local_path
        path.mkdir(parents=True, exist_ok=True)
        if os.name == "nt":
            os.startfile(str(path))  # type: ignore[attr-defined]
            return
        import subprocess

        subprocess.Popen(["xdg-open", str(path)])

    def play_result_audio(self, result: GenerateSpeechResult) -> Path:
        """Open direct-generation audio through the OS default player."""
        return self.media_player.play_result(result)

    def play_queue_audio(self, manifest: FileQueueOutputManifest) -> Path:
        """Open queue audio through the OS default player."""
        return self.media_player.play_manifest(manifest)

    def install_gpu_for_model(self, model_id: str) -> str:
        return self.service.install_gpu_acceleration(model_id)

    def install_base_for_model(self, model_id: str) -> str:
        return self.service.install_base_runtime_for_model(model_id)

    def open_model_catalog(self) -> None:
        self.service.open_model_catalog()

    # --- Generation ---------------------------------------------------------

    def generate_text(
        self,
        text: str,
        settings: GenerationSettings,
        progress_callback: ProgressCallback | None = None,
        cancel_event: Event | None = None,
    ) -> GenerateSpeechResult:
        if not text.strip():
            raise OmniTtsError("Bạn chưa nhập nội dung cần đọc.")
        self.validate_license_for_model(settings.model_id)
        status_callback = _status_from(progress_callback)
        with self.generation_coordinator.acquire(
            settings, cancel_event, status_callback
        ):
            self._wait_for_gpu(settings, cancel_event, status_callback)
            return self.service.generate_audio(
                settings.to_request(text), progress_callback, cancel_event
            )

    def generate_files(
        self,
        tasks: list[tuple[str, Path]],
        settings: GenerationSettings,
        progress_callback: ProgressCallback | None = None,
        file_event_callback: FileEventCallback | None = None,
        cancel_event: Event | None = None,
    ) -> list[FileGenerationOutcome]:
        if not tasks:
            raise OmniTtsError("Bạn chưa chọn file nguồn.")
        self.validate_license_for_model(settings.model_id)
        outcomes: list[FileGenerationOutcome] = []
        template = settings.to_request("Nội dung sẽ được đọc từ file nguồn.")
        total_files = len(tasks)
        status_callback = _status_from(progress_callback)
        for file_index, (item_id, source_path) in enumerate(tasks, start=1):
            check_cancel(cancel_event)
            _emit_file_event(
                file_event_callback,
                FileGenerationEvent(
                    item_id=item_id,
                    source_path=source_path,
                    status=FileQueueStatus.RUNNING,
                    message="Đang khởi tạo...",
                ),
            )
            try:
                with self.generation_coordinator.acquire(
                    settings,
                    cancel_event,
                    status_callback,
                    source_path=source_path,
                ):
                    self._wait_for_gpu(settings, cancel_event, status_callback)
                    result = self.service.generate_from_source_file(
                        source_path=source_path,
                        request_template=template,
                        output_dir=settings.output_dir,
                        progress_callback=_file_progress(
                            progress_callback,
                            file_event_callback,
                            item_id,
                            source_path,
                            file_index,
                            total_files,
                            source_path.name,
                        ),
                        cancel_event=cancel_event,
                    )
            except GenerationCancelled:
                _emit_file_event(
                    file_event_callback,
                    FileGenerationEvent(
                        item_id=item_id,
                        source_path=source_path,
                        status=FileQueueStatus.CANCELLED,
                        message="Đã hủy khi đang xử lý",
                    ),
                )
                raise
            except GpuSafetyError as exc:
                error = str(exc)
                outcomes.append(
                    FileGenerationOutcome(
                        item_id=item_id,
                        source_path=source_path,
                        status=FileQueueStatus.FAILED,
                        error=error,
                    )
                )
                _emit_file_event(
                    file_event_callback,
                    FileGenerationEvent(
                        item_id=item_id,
                        source_path=source_path,
                        status=FileQueueStatus.FAILED,
                        message=error,
                        error=error,
                    ),
                )
                if progress_callback is not None:
                    progress_callback(
                        ProgressEvent(
                            message=(
                                f"File {file_index}/{total_files} ({source_path.name}): "
                                "Đã dừng toàn bộ hàng đợi để bảo vệ GPU"
                            ),
                            current=file_index,
                            total=total_files,
                        )
                    )
                break
            except Exception as exc:  # continue remaining files after one failure
                error = str(exc)
                outcomes.append(
                    FileGenerationOutcome(
                        item_id=item_id,
                        source_path=source_path,
                        status=FileQueueStatus.FAILED,
                        error=error,
                    )
                )
                _emit_file_event(
                    file_event_callback,
                    FileGenerationEvent(
                        item_id=item_id,
                        source_path=source_path,
                        status=FileQueueStatus.FAILED,
                        message=error,
                        error=error,
                    ),
                )
                if progress_callback is not None:
                    progress_callback(
                        ProgressEvent(
                            message=f"File {file_index}/{total_files} ({source_path.name}): Lỗi, chuyển file tiếp theo",
                            current=file_index,
                            total=total_files,
                        )
                    )
                continue

            try:
                self.service.job_store.save_json(result.job_dir / "result.json", result)
            except OSError:
                pass
            outcomes.append(
                FileGenerationOutcome(
                    item_id=item_id,
                    source_path=source_path,
                    status=FileQueueStatus.DONE,
                    result=result,
                )
            )
            _emit_file_event(
                file_event_callback,
                FileGenerationEvent(
                    item_id=item_id,
                    source_path=source_path,
                    status=FileQueueStatus.DONE,
                    progress_percent=100.0,
                    message=result.message,
                    result=result,
                ),
            )
        return outcomes

    def _wait_for_gpu(
        self,
        settings: GenerationSettings,
        cancel_event: Event | None,
        status_callback: StatusCallback | None,
    ) -> None:
        if self.safety_gate is not None:
            self.safety_gate.wait_before_generation(settings, cancel_event, status_callback)

    # --- License ------------------------------------------------------------

    def license_status(self):
        return self.license_provider.get_status()

    def current_device_id(self) -> str:
        return self.license_provider.current_device_id()

    def install_license(self, source_path: Path):
        return self.license_provider.install_license(source_path)

    def validate_license_for_model(self, model_id: str) -> None:
        status = self.license_status()
        if not status.valid:
            raise OmniTtsError(status.message)
        for feature in required_features_for_model(model_id):
            if not status.feature_enabled(feature):
                raise OmniTtsError(f"License hiện tại chưa bật tính năng: {feature}.")


def _default_license_provider() -> LicenseProviderProtocol:
    from omni_tts_license.local_signed import LocalSignedLicenseProvider

    return LocalSignedLicenseProvider()


def _status_from(progress_callback: ProgressCallback | None) -> StatusCallback | None:
    if progress_callback is None:
        return None

    def emit(message: str) -> None:
        progress_callback(ProgressEvent(message=message, current=0, total=1))

    return emit


def _file_progress(
    callback: ProgressCallback | None,
    file_event_callback: FileEventCallback | None,
    item_id: str,
    source_path: Path,
    file_index: int,
    total_files: int,
    file_name: str,
) -> ProgressCallback | None:
    if callback is None and file_event_callback is None:
        return None

    last_file_progress = 0.0
    progress_lock = Lock()

    def scaled(event: ProgressEvent) -> None:
        nonlocal last_file_progress
        candidate = event.current / event.total if event.total > 0 else 0.0
        candidate = max(0.0, min(1.0, candidate))
        # Provider status messages may carry 0/current while a request starts.
        # Multiple remote requests can emit those messages concurrently and out
        # of order, so progress for one file must never move backwards.
        with progress_lock:
            file_progress = max(last_file_progress, candidate)
            last_file_progress = file_progress
            # Keep calculation and emission under the same lock. Otherwise a
            # thread holding an older value could emit after a newer thread.
            if callback is not None:
                callback(
                    ProgressEvent(
                        message=f"File {file_index}/{total_files} ({file_name}): {event.message}",
                        current=(file_index - 1) + file_progress,
                        total=total_files,
                    )
                )
            _emit_file_event(
                file_event_callback,
                FileGenerationEvent(
                    item_id=item_id,
                    source_path=source_path,
                    status=FileQueueStatus.RUNNING,
                    progress_percent=max(0.0, min(100.0, file_progress * 100.0)),
                    message=event.message,
                ),
            )

    return scaled


def _emit_file_event(callback: FileEventCallback | None, event: FileGenerationEvent) -> None:
    if callback is not None:
        callback(event)
