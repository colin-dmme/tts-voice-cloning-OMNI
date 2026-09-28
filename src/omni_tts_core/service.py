from __future__ import annotations

from pathlib import Path
from threading import Event, Lock
from typing import Callable

from omni_tts_core.audio.wav_tools import (
    concatenate_segments_with_pauses,
    duration_seconds,
    read_audio_mono,
    save_audio_atomic,
)
from omni_tts_core.chunk_join import resolve_chunk_join_policy
from omni_tts_core.config import AppSettings
from omni_tts_core.engine_profile_cache import EngineProfileCache
from omni_tts_core.generation_form import GenerationFormPresenter
from omni_tts_core.generation_process_lock import GenerationProcessLock
from omni_tts_core.higgs.custom_voices import (
    HiggsCustomVoiceClient,
    HiggsCustomVoiceStore,
)
from omni_tts_core.higgs.script import compile_higgs_chunks, validate_higgs_script
from omni_tts_core.model_catalog import open_catalog
from omni_tts_core.engines.base import BaseTtsEngine, TtsEngineRequest, TtsEngineResult
from omni_tts_core.jobs.store import JobStore
from omni_tts_core.model_registry import ModelRegistry, ModelSpec, effective_voice_input
from omni_tts_core.model_storage import ModelStorage
from omni_tts_core.progress import ProgressCallback, check_cancel, emit_progress
from omni_tts_core.pronunciation import (
    PronunciationPresetStore,
    analyze_pronunciation,
    build_pronunciation_report,
    freeze_pronunciation_selection,
)
from omni_tts_core.provider_registry import provider_descriptor
from omni_tts_core.provider_options import (
    normalize_provider_options,
    provider_settings_for_model,
)
from omni_tts_core.runtime_status import RuntimeStatusService
from omni_tts_core.setup_tasks import SetupService
from omni_tts_core.subtitles.srt_builder import write_srt
from omni_tts_core.text.splitter import split_text
from omni_tts_core.text.punctuation_pauses import (
    PauseRange,
    PunctuationPauseConfig,
    RandomSource,
    pause_after_text,
)
from omni_tts_core.text.source_reader import read_source_text, read_source_units, text_units_from_blank_lines
from omni_tts_core.text.vi_normalizer import normalize_vietnamese_text
from omni_tts_core.designed_voices import DesignedVoiceStore
from omni_tts_core.voice_library import VoiceItem, build_voice_items, filter_voice_items
from omni_tts_core.voice_profile_policy import ProfileCompatibility, VoiceProfilePolicy
from omni_tts_core.voice_profiles import VoiceProfileManager
from omni_tts_shared.errors import ConfigError, ModelMissingError
from omni_tts_core.text.output_naming import (
    compose_stem,
    default_stem_from_text,
    format_duration_stem,
    slug_component,
)
from omni_tts_shared.languages import language_label
from omni_tts_shared.pronunciation import (
    PronunciationAnalysis,
    PronunciationPreset,
    PronunciationRule,
    PronunciationSelection,
    PronunciationSnapshot,
)
from omni_tts_shared.schemas import (
    DesignedVoice,
    GenerateSpeechRequest,
    GenerateSpeechResult,
    GenerationFormDescriptor,
    HiggsCustomVoice,
    ModelCapabilities,
    ModelStatus,
    ProfileSaveWarning,
    RuntimeStatus,
    SetupTaskStatus,
    SegmentTiming,
    VoiceProfile,
)
from omni_tts_shared.voice_presets import NO_VOICE_PRESET_ID, NO_VOICE_PRESET_LABEL
from omni_tts_shared.vieneu_codecs import ONNX_CODEC_REPO, codec_choices, valid_codec_repo


class TtsService:
    def __init__(
        self,
        settings: AppSettings | None = None,
        registry: ModelRegistry | None = None,
        storage: ModelStorage | None = None,
        voice_profiles: VoiceProfileManager | None = None,
        higgs_custom_voices: HiggsCustomVoiceStore | None = None,
        pronunciation_presets: PronunciationPresetStore | None = None,
    ) -> None:
        self.settings = settings or AppSettings()
        self.registry = registry or ModelRegistry()
        self.storage = storage or ModelStorage(self.registry)
        self.runtime_status = RuntimeStatusService(self.registry, self.storage)
        self.setup = SetupService(self.registry, self.storage, self.runtime_status)
        self.voice_profiles = voice_profiles or VoiceProfileManager()
        self.designed_voices = DesignedVoiceStore()
        self.higgs_custom_voices = higgs_custom_voices or HiggsCustomVoiceStore()
        self.engine_cache = EngineProfileCache()
        self.voice_policy = VoiceProfilePolicy(self.registry, self.engine_cache)
        self.generation_form = GenerationFormPresenter(self.registry)
        self.job_store = JobStore(self.settings.outputs_root)
        project_root = getattr(
            self.settings,
            "project_root",
            Path(self.settings.outputs_root).parent,
        )
        self.pronunciation_presets = pronunciation_presets or PronunciationPresetStore(
            Path(project_root) / "pronunciation" / "presets"
        )
        self.process_lock = GenerationProcessLock(
            Path(project_root) / "config" / "tts_generation.lock"
        )
        self._engines: dict[str, BaseTtsEngine] = {}
        self._engine_lock = Lock()
        self._remote_switch_confirm: Callable[..., bool] | None = None

    # --- Pronunciation presets ---------------------------------------------

    def list_pronunciation_presets(self) -> list[PronunciationPreset]:
        return self.pronunciation_presets.list_presets()

    def get_pronunciation_preset(self, preset_id: str) -> PronunciationPreset:
        return self.pronunciation_presets.get(preset_id)

    def save_pronunciation_preset(
        self,
        *,
        name: str,
        rules: list[PronunciationRule | dict],
        project: str = "",
        tags: list[str] | None = None,
        notes: str = "",
        preset_id: str | None = None,
    ) -> PronunciationPreset:
        return self.pronunciation_presets.save(
            name=name,
            rules=rules,
            project=project,
            tags=tags,
            notes=notes,
            preset_id=preset_id,
        )

    def delete_pronunciation_preset(self, preset_id: str) -> bool:
        return self.pronunciation_presets.delete(preset_id)

    def duplicate_pronunciation_preset(
        self, preset_id: str, name: str | None = None
    ) -> PronunciationPreset:
        return self.pronunciation_presets.duplicate(preset_id, name)

    def import_pronunciation_preset(self, path: Path) -> PronunciationPreset:
        return self.pronunciation_presets.import_file(path)

    def export_pronunciation_preset(self, preset_id: str, path: Path) -> Path:
        return self.pronunciation_presets.export_file(preset_id, path)

    def preview_pronunciation(
        self,
        text: str,
        selection: PronunciationSelection | None = None,
    ) -> PronunciationAnalysis:
        snapshot = freeze_pronunciation_selection(
            self.pronunciation_presets,
            selection,
        )
        return analyze_pronunciation(text, snapshot)

    def freeze_pronunciation(
        self, request: GenerateSpeechRequest
    ) -> GenerateSpeechRequest:
        if request.pronunciation_snapshot is not None:
            return request
        snapshot = freeze_pronunciation_selection(
            self.pronunciation_presets,
            request.pronunciation,
        )
        return request.model_copy(update={"pronunciation_snapshot": snapshot})

    def _save_pronunciation_report(
        self,
        job_dir: Path,
        request: GenerateSpeechRequest,
        source_text: str,
    ) -> tuple[Path | None, PronunciationAnalysis]:
        analysis = analyze_pronunciation(
            source_text,
            request.pronunciation_snapshot,
        )
        snapshot = request.pronunciation_snapshot
        if snapshot is None or not snapshot.enabled:
            return None, analysis
        report_path = job_dir / "pronunciation_report.json"
        self.job_store.save_json(report_path, build_pronunciation_report(analysis))
        return report_path, analysis

    def list_voice_profiles(self) -> list[VoiceProfile]:
        return self.voice_profiles.list_profiles()

    def get_voice_profile(self, profile_id: str) -> VoiceProfile:
        return self.voice_profiles.get_profile(profile_id)

    # --- Designed voices (Voice Design) ------------------------------------

    def list_designed_voices(self) -> list[DesignedVoice]:
        return self.designed_voices.list_voices()

    def get_designed_voice(self, voice_id: str) -> DesignedVoice:
        return self.designed_voices.get_voice(voice_id)

    def save_designed_voice(
        self,
        name: str,
        instruct: str,
        language: str = "vi",
        project: str = "",
        tags: list[str] | None = None,
        notes: str = "",
        voice_id: str | None = None,
    ) -> DesignedVoice:
        return self.designed_voices.save_voice(
            name=name,
            instruct=instruct,
            language=language,
            project=project,
            tags=tags,
            notes=notes,
            voice_id=voice_id,
        )

    def delete_designed_voice(self, voice_id: str) -> None:
        self.designed_voices.delete_voice(voice_id)

    # --- Voice library (unified selectable voices) -------------------------

    def voice_kinds_for_model(self, model_id: str) -> tuple[str, ...]:
        """Which library voice kinds a model can use: clone and/or design."""
        caps = self.registry.get(model_id).capabilities
        kinds: list[str] = []
        if caps.supports_voice_profile:
            kinds.append("clone")
        if caps.supports_voice_design:
            kinds.append("design")
        return tuple(kinds)

    def selectable_voice_items(
        self,
        model_id: str,
        *,
        query: str = "",
        project: str | None = None,
        tag: str | None = None,
    ) -> list[VoiceItem]:
        """Library voices this model supports, after search/project/tag filters.

        The GUI passes only its widget state (query/project/tag); which *kinds*
        are offered comes from the model's capabilities, never from the GUI.
        """
        items = build_voice_items(
            self.voice_profiles.list_profiles(), self.designed_voices.list_voices()
        )
        return filter_voice_items(
            items,
            query=query,
            project=project,
            tag=tag,
            kinds=self.voice_kinds_for_model(model_id),
        )

    def _resolve_instruct(self, request: GenerateSpeechRequest, spec: ModelSpec) -> str | None:
        """Resolve the Voice Design description for this request, or None.

        Only honoured when the model supports voice design; a saved
        designed_voice_id wins, otherwise a directly-supplied voice_instruct.
        """
        if not spec.capabilities.supports_voice_design:
            return None
        if request.designed_voice_id:
            try:
                return self.designed_voices.get_voice(request.designed_voice_id).instruct
            except Exception:
                return request.voice_instruct or None
        return request.voice_instruct or None

    def list_higgs_custom_voices(self, endpoint_id: str) -> list[HiggsCustomVoice]:
        return self.higgs_custom_voices.list(endpoint_id)

    def create_higgs_custom_voice(
        self,
        *,
        endpoint,
        profile_id: str,
        title: str,
    ) -> HiggsCustomVoice:
        profile = self.voice_profiles.get_profile(profile_id)
        voice = HiggsCustomVoiceClient(endpoint).create(
            title=title,
            reference_audio_path=profile.audio_path,
            reference_text=profile.transcript,
        )
        voice = voice.model_copy(update={"source_profile_id": profile.profile_id})
        return self.higgs_custom_voices.save(voice)

    def save_voice_profile(
        self,
        name: str,
        audio_path: Path,
        transcript: str,
        language: str = "vi",
        project: str = "",
        notes: str = "",
        profile_id: str | None = None,
        tags: list[str] | None = None,
    ) -> tuple[VoiceProfile, list[ProfileSaveWarning]]:
        return self.voice_profiles.save_profile(
            name=name,
            audio_path=audio_path,
            transcript=transcript,
            language=language,
            project=project,
            notes=notes,
            profile_id=profile_id,
            tags=tags,
        )

    def delete_voice_profile(self, profile_id: str, remove_sample: bool = False) -> None:
        self.voice_profiles.delete_profile(profile_id, remove_sample=remove_sample)
        self.engine_cache.invalidate_profile(profile_id)

    def add_voice_profile_sample(
        self,
        profile_id: str,
        audio_path: Path,
        transcript: str = "",
        role: str = "neutral",
        sample_id: str | None = None,
    ) -> tuple:
        return self.voice_profiles.add_sample(
            profile_id=profile_id,
            audio_path=audio_path,
            transcript=transcript,
            role=role,
            sample_id=sample_id,
        )

    def remove_voice_profile_sample(self, profile_id: str, sample_index: int):
        return self.voice_profiles.remove_sample(profile_id, sample_index)

    def set_voice_profile_default_sample(self, profile_id: str, sample_id: str):
        return self.voice_profiles.set_default_sample(profile_id, sample_id)

    def open_model_catalog(self) -> None:
        open_catalog(self.settings.app_name)

    def list_models(self) -> list[ModelStatus]:
        return self.storage.statuses()

    def list_tts_models(self) -> list[ModelStatus]:
        specs = self.registry.tts_models()
        return [self.storage.status_for(spec) for spec in specs]

    def list_runtime_statuses(self) -> list[RuntimeStatus]:
        return self.runtime_status.all_statuses()

    def model_capabilities(self, model_id: str):
        return _effective_capabilities(self.registry.get(model_id))

    def model_provider(self, model_id: str) -> str:
        return self.registry.get(model_id).provider

    def generation_form_descriptor(
        self,
        model_id: str,
        preferred_mode: str | None = None,
    ) -> GenerationFormDescriptor:
        mode = preferred_mode if preferred_mode in ("fixed", "profile") else None
        return self.generation_form.describe(model_id, mode)

    def supports_vieneu_codec(self, model_id: str) -> bool:
        spec = self.registry.get(model_id)
        descriptor = provider_descriptor(spec.provider)
        return bool(
            descriptor
            and "codec" in descriptor.controls
            and spec.runtime.get("codec_repo")
        )

    def supports_vieneu_sampling(self, model_id: str) -> bool:
        spec = self.registry.get(model_id)
        descriptor = provider_descriptor(spec.provider)
        return bool(descriptor and "sampling" in descriptor.controls)

    def supports_f5_settings(self, model_id: str) -> bool:
        spec = self.registry.get(model_id)
        descriptor = provider_descriptor(spec.provider)
        return bool(descriptor and "f5" in descriptor.controls)

    def default_f5_settings(self, model_id: str) -> dict[str, object]:
        spec = self.registry.get(model_id)
        runtime = spec.runtime if spec.provider == "f5tts" else {}
        return {
            "f5_nfe_step": int(_runtime_default(runtime, "f5_nfe_step", 32)),
            "f5_cfg_strength": float(_runtime_default(runtime, "f5_cfg_strength", 2.0)),
            "f5_sway_sampling_coef": float(_runtime_default(runtime, "f5_sway_sampling_coef", -1.0)),
            "f5_cross_fade_duration": float(_runtime_default(runtime, "f5_cross_fade_duration", 0.15)),
            "f5_target_rms": float(_runtime_default(runtime, "f5_target_rms", 0.1)),
            "f5_remove_silence": bool(runtime.get("f5_remove_silence", False)),
            "f5_seed": None,
            "f5_fix_duration": None,
        }

    def supports_chatterbox_settings(self, model_id: str) -> bool:
        spec = self.registry.get(model_id)
        descriptor = provider_descriptor(spec.provider)
        return bool(descriptor and "chatterbox" in descriptor.controls)

    def default_chatterbox_settings(self, model_id: str) -> dict[str, object]:
        spec = self.registry.get(model_id)
        runtime = spec.runtime if spec.provider == "chatterbox" else {}
        return {
            "chatterbox_temperature": float(_runtime_default(runtime, "chatterbox_temperature", 0.8)),
            "chatterbox_top_p": float(_runtime_default(runtime, "chatterbox_top_p", 0.95)),
            "chatterbox_top_k": int(_runtime_default(runtime, "chatterbox_top_k", 1000)),
            "chatterbox_repetition_penalty": float(
                _runtime_default(runtime, "chatterbox_repetition_penalty", 1.2)
            ),
            "chatterbox_seed": None,
            "chatterbox_norm_loudness": bool(runtime.get("chatterbox_norm_loudness", True)),
            "gpu_safety_enabled": bool(runtime.get("gpu_safety_enabled", True)),
            "gpu_start_temperature_c": int(_runtime_default(runtime, "gpu_start_temperature_c", 75)),
            "gpu_abort_temperature_c": int(_runtime_default(runtime, "gpu_abort_temperature_c", 82)),
            "gpu_abort_temperature_sustain_seconds": float(
                _runtime_default(runtime, "gpu_abort_temperature_sustain_seconds", 10.0)
            ),
            "gpu_emergency_temperature_c": int(
                _runtime_default(runtime, "gpu_emergency_temperature_c", 90)
            ),
            "gpu_cooldown_max_wait_seconds": float(
                _runtime_default(runtime, "gpu_cooldown_max_wait_seconds", 300.0)
            ),
            "gpu_resume_temperature_c": int(_runtime_default(runtime, "gpu_resume_temperature_c", 72)),
            "gpu_minimum_free_vram_mb": int(_runtime_default(runtime, "gpu_minimum_free_vram_mb", 6000)),
            "gpu_runtime_minimum_free_vram_mb": int(
                _runtime_default(runtime, "gpu_runtime_minimum_free_vram_mb", 700)
            ),
            "gpu_maximum_utilization_percent": int(
                _runtime_default(runtime, "gpu_maximum_utilization_percent", 20)
            ),
            "gpu_maximum_encoder_utilization_percent": int(
                _runtime_default(runtime, "gpu_maximum_encoder_utilization_percent", 5)
            ),
        }

    def default_vieneu_temperature(self, model_id: str) -> float:
        spec = self.registry.get(model_id)
        return float(spec.runtime.get("temperature") or 1.0) if spec.provider == "vieneu" else 1.0

    def default_vieneu_top_k(self, model_id: str) -> int:
        spec = self.registry.get(model_id)
        return int(spec.runtime.get("top_k") or 50) if spec.provider == "vieneu" else 50

    def list_vieneu_codecs(self, model_id: str) -> list[tuple[str, str]]:
        if not self.supports_vieneu_codec(model_id):
            return []
        return codec_choices()

    def default_vieneu_codec_repo(self, model_id: str) -> str | None:
        spec = self.registry.get(model_id)
        if not self.supports_vieneu_codec(model_id):
            return None
        return valid_codec_repo(str(spec.runtime.get("codec_repo") or "")) or codec_choices()[0][1]

    def valid_vieneu_codec_repo(self, model_id: str, codec_repo: str | None) -> str | None:
        if not self.supports_vieneu_codec(model_id):
            return None
        return valid_codec_repo(codec_repo)

    def list_voice_presets(self, model_id: str, include_none: bool = True) -> list[tuple[str, str]]:
        spec = self.registry.get(model_id)
        choices = [(label, preset_id) for preset_id, label in spec.voice_presets.items()]
        if include_none:
            return [(NO_VOICE_PRESET_LABEL, NO_VOICE_PRESET_ID), *choices]
        return choices

    def default_voice_preset_id(self, model_id: str) -> str | None:
        spec = self.registry.get(model_id)
        if spec.default_voice_preset in spec.voice_presets:
            return spec.default_voice_preset
        return next(iter(spec.voice_presets), None)

    def has_voice_presets(self, model_id: str) -> bool:
        spec = self.registry.get(model_id)
        return spec.capabilities.supports_voice_presets and bool(spec.voice_presets)

    def valid_voice_preset_id(self, model_id: str, preset_id: str | None) -> str | None:
        if not preset_id:
            return None
        spec = self.registry.get(model_id)
        return preset_id if preset_id in spec.voice_presets else None

    def runtime_status_for(self, model_id: str) -> RuntimeStatus:
        return self.runtime_status.status_for(model_id)

    def setup_statuses(self, model_id: str | None = None) -> list[SetupTaskStatus]:
        return self.setup.setup_statuses(model_id)

    def environment_statuses(self) -> list[SetupTaskStatus]:
        return self.setup.environment_statuses()

    def model_setup_statuses(self, model_id: str) -> list[SetupTaskStatus]:
        return self.setup.model_setup_statuses(model_id)

    def download_model(self, model_id: str) -> ModelStatus:
        return self.storage.download(model_id)

    def import_local_model(self, model_id: str, source_root: str | Path) -> ModelStatus:
        return self.storage.import_local(model_id, source_root)

    def install_gpu_acceleration(self, model_id: str) -> str:
        return self.setup.install_gpu_for_model(model_id)

    def install_base_runtime_for_model(self, model_id: str) -> str:
        return self.setup.install_base_for_model(model_id)

    def download_missing_required_models(self) -> list[ModelStatus]:
        downloaded: list[ModelStatus] = []
        for spec in self.missing_required_models():
            downloaded.append(self.storage.download(spec.model_id))
        return downloaded

    def missing_required_models(self) -> list[ModelSpec]:
        return [
            spec
            for spec in self.registry.all()
            if spec.required and not self.storage.is_installed(spec)
        ]

    def remove_model(self, model_id: str) -> ModelStatus:
        return self.storage.remove(model_id)

    def model_removal_preview(self, model_id: str) -> str:
        return self.storage.removal_preview(model_id)

    def generate_audio(
        self,
        request: GenerateSpeechRequest,
        progress_callback: ProgressCallback | None = None,
        cancel_event: Event | None = None,
    ) -> GenerateSpeechResult:
        request = self.freeze_pronunciation(request)

        def report_wait(message: str) -> None:
            emit_progress(progress_callback, message, 0, 1)

        with self.process_lock.acquire(cancel_event, report_wait):
            check_cancel(cancel_event)
            if request.output_mode == "split":
                return self._generate_split_text(request, request.text, progress_callback, cancel_event)
            return self._generate_merged_text(request, progress_callback, cancel_event)

    def _generate_merged_text(
        self,
        request: GenerateSpeechRequest,
        progress_callback: ProgressCallback | None = None,
        cancel_event: Event | None = None,
    ) -> GenerateSpeechResult:
        check_cancel(cancel_event)
        request = self._apply_voice_profile(request)
        spec = self.registry.get(request.model_id)
        self._ensure_request_can_generate(request, spec)
        units = _prepared_text_units(
            request.text,
            request.language,
            request.max_chunk_chars,
            provider=spec.provider,
            chunk_join_mode=request.chunk_join_mode,
            higgs=request.higgs,
            pronunciation_snapshot=request.pronunciation_snapshot,
        )
        chunks = [chunk for unit in units for chunk in unit["chunks"]]
        if not chunks:
            raise ConfigError("Không có nội dung để đọc.")
        emit_progress(
            progress_callback,
            f"Đã tách thành {len(units)} đoạn gốc, {len(chunks)} đoạn đọc.",
            0,
            len(chunks),
        )

        job_id, job_dir = self.job_store.create_job_dir()
        output_dir = _resolve_output_dir(request, job_dir)
        base_stem = _resolve_output_stem(request)
        output_dir.mkdir(parents=True, exist_ok=True)
        self.job_store.save_json(job_dir / "request.json", request)
        self.job_store.save_json(
            job_dir / "chunks.json",
            {
                "max_chunk_chars": request.max_chunk_chars,
                "punctuation_pause_enabled": request.punctuation_pause_enabled,
                "sentence_pause_ms": request.sentence_pause_ms,
                "sentence_pause_random_enabled": request.sentence_pause_random_enabled,
                "sentence_pause_min_ms": request.sentence_pause_min_ms,
                "sentence_pause_max_ms": request.sentence_pause_max_ms,
                "comma_pause_ms": request.comma_pause_ms,
                "comma_pause_random_enabled": request.comma_pause_random_enabled,
                "comma_pause_min_ms": request.comma_pause_min_ms,
                "comma_pause_max_ms": request.comma_pause_max_ms,
                "clause_pause_ms": request.clause_pause_ms,
                "clause_pause_random_enabled": request.clause_pause_random_enabled,
                "clause_pause_min_ms": request.clause_pause_min_ms,
                "clause_pause_max_ms": request.clause_pause_max_ms,
                "ellipsis_pause_ms": request.ellipsis_pause_ms,
                "ellipsis_pause_random_enabled": request.ellipsis_pause_random_enabled,
                "ellipsis_pause_min_ms": request.ellipsis_pause_min_ms,
                "ellipsis_pause_max_ms": request.ellipsis_pause_max_ms,
                "chunk_join_mode": request.chunk_join_mode,
                "chunk_pause_ms": request.chunk_pause_ms,
                "chunk_crossfade_ms": request.chunk_crossfade_ms,
                "paragraph_pause_ms": _paragraph_pause_ms(request),
                "paragraph_pause_random_enabled": request.paragraph_pause_random_enabled,
                "paragraph_pause_min_ms": request.paragraph_pause_min_ms,
                "paragraph_pause_max_ms": request.paragraph_pause_max_ms,
                "unit_count": len(units),
                "chunk_count": len(chunks),
                "units": [
                    {
                        "index": unit["unit"].index,
                        "text": unit["unit"].text,
                        "chunks": unit["chunks"],
                        "segments": unit["segments"],
                    }
                    for unit in units
                ],
            },
        )
        pronunciation_report_path, pronunciation_analysis = (
            self._save_pronunciation_report(job_dir, request, request.text)
        )

        engine = self._engine_for(spec)
        cached_path = self._cached_prompt_path_for(request, spec)
        engine_requests = [
            TtsEngineRequest(
                text=chunk,
                language=request.language,
                reference_audio_path=_clean_path(request.reference_audio_path),
                reference_text=request.reference_text,
                speaker_id=request.speaker_id,
                instruct=self._resolve_instruct(request, spec),
                num_step=request.omnivoice_num_step if spec.provider == "omnivoice" else None,
                speed=request.speed,
                pitch_shift=request.pitch_shift,
                emotion=request.emotion,
                runtime_target=request.runtime_target,
                codec_repo=_codec_repo_for_request(request, spec),
                temperature=request.temperature if spec.provider == "vieneu" else None,
                top_k=request.top_k if spec.provider == "vieneu" else None,
                piper_noise_scale=request.piper_noise_scale if spec.provider == "piper" else 0.667,
                piper_noise_w=request.piper_noise_w if spec.provider == "piper" else 0.8,
                piper_seed=request.piper_seed if spec.provider == "piper" else None,
                f5_nfe_step=request.f5_nfe_step if spec.provider == "f5tts" else None,
                f5_cfg_strength=request.f5_cfg_strength if spec.provider == "f5tts" else None,
                f5_sway_sampling_coef=request.f5_sway_sampling_coef if spec.provider == "f5tts" else None,
                f5_cross_fade_duration=request.f5_cross_fade_duration if spec.provider == "f5tts" else None,
                f5_target_rms=request.f5_target_rms if spec.provider == "f5tts" else None,
                f5_remove_silence=request.f5_remove_silence if spec.provider == "f5tts" else False,
                f5_seed=request.f5_seed if spec.provider == "f5tts" else None,
                f5_fix_duration=request.f5_fix_duration if spec.provider == "f5tts" else None,
                chatterbox_temperature=(
                    request.chatterbox_temperature if spec.provider == "chatterbox" else None
                ),
                chatterbox_top_p=request.chatterbox_top_p if spec.provider == "chatterbox" else None,
                chatterbox_top_k=request.chatterbox_top_k if spec.provider == "chatterbox" else None,
                chatterbox_repetition_penalty=(
                    request.chatterbox_repetition_penalty if spec.provider == "chatterbox" else None
                ),
                chatterbox_seed=request.chatterbox_seed if spec.provider == "chatterbox" else None,
                chatterbox_norm_loudness=(
                    request.chatterbox_norm_loudness if spec.provider == "chatterbox" else True
                ),
                gpu_safety_enabled=request.gpu_safety_enabled,
                gpu_start_temperature_c=request.gpu_start_temperature_c,
                gpu_abort_temperature_c=request.gpu_abort_temperature_c,
                gpu_abort_temperature_sustain_seconds=request.gpu_abort_temperature_sustain_seconds,
                gpu_emergency_temperature_c=request.gpu_emergency_temperature_c,
                gpu_cooldown_max_wait_seconds=request.gpu_cooldown_max_wait_seconds,
                gpu_resume_temperature_c=request.gpu_resume_temperature_c,
                gpu_minimum_free_vram_mb=request.gpu_minimum_free_vram_mb,
                gpu_runtime_minimum_free_vram_mb=request.gpu_runtime_minimum_free_vram_mb,
                gpu_maximum_utilization_percent=request.gpu_maximum_utilization_percent,
                gpu_maximum_encoder_utilization_percent=request.gpu_maximum_encoder_utilization_percent,
                punctuation_pause_enabled=(
                    request.punctuation_pause_enabled
                    and _supports_punctuation_pauses(spec)
                ),
                sentence_pause_ms=request.sentence_pause_ms,
                sentence_pause_random_enabled=request.sentence_pause_random_enabled,
                sentence_pause_min_ms=request.sentence_pause_min_ms,
                sentence_pause_max_ms=request.sentence_pause_max_ms,
                comma_pause_ms=request.comma_pause_ms,
                comma_pause_random_enabled=request.comma_pause_random_enabled,
                comma_pause_min_ms=request.comma_pause_min_ms,
                comma_pause_max_ms=request.comma_pause_max_ms,
                clause_pause_ms=request.clause_pause_ms,
                clause_pause_random_enabled=request.clause_pause_random_enabled,
                clause_pause_min_ms=request.clause_pause_min_ms,
                clause_pause_max_ms=request.clause_pause_max_ms,
                ellipsis_pause_ms=request.ellipsis_pause_ms,
                ellipsis_pause_random_enabled=request.ellipsis_pause_random_enabled,
                ellipsis_pause_min_ms=request.ellipsis_pause_min_ms,
                ellipsis_pause_max_ms=request.ellipsis_pause_max_ms,
                cancel_event=cancel_event,
                cached_prompt_path=cached_path,
                status_callback=lambda message: emit_progress(
                    progress_callback,
                    message,
                    0,
                    max(1, len(chunks)),
                ),
                remote_endpoint=(
                    request.remote_endpoint if spec.provider == "higgs_remote" else None
                ),
                higgs=request.higgs if spec.provider == "higgs_remote" else None,
                provider_options=dict(request.provider_options),
            )
            for chunk in chunks
        ]
        check_cancel(cancel_event)
        emit_progress(progress_callback, f"Đang tạo {len(chunks)} đoạn...", 0, len(chunks))
        batch_results = engine.generate_batch(
            engine_requests,
            progress_callback=lambda done, total: emit_progress(
                progress_callback,
                f"Đã tạo {done}/{total} đoạn...",
                done,
                total,
            ),
        )
        check_cancel(cancel_event)
        if len(batch_results) != len(engine_requests):
            raise ConfigError("Engine trả về số đoạn audio không khớp với yêu cầu.")
        emit_progress(progress_callback, f"Hoàn tất {len(chunks)} đoạn.", len(chunks), len(chunks))

        paragraph_audio_segments = []
        timings: list[SegmentTiming] = []
        current_seconds = 0.0
        sample_rate = 24000
        chunk_cursor = 0
        paragraph_pauses_ms = _paragraph_pause_values(request, len(units))

        for unit_index, unit in enumerate(units):
            unit_chunks = unit["chunks"]
            unit_results = batch_results[chunk_cursor : chunk_cursor + len(unit_chunks)]
            chunk_cursor += len(unit_chunks)
            unit_audio_segments = []
            chunk_windows: list[tuple[float, float]] = []
            unit_sample_rate = sample_rate
            unit_pauses_ms = _chunk_pause_values(request, spec, unit_chunks)
            unit_crossfade_ms = _chunk_crossfade_ms(request, spec)

            for chunk_index, (chunk, result) in enumerate(zip(unit_chunks, unit_results)):
                unit_sample_rate = result.sample_rate
                segment_duration = duration_seconds(result.audio, unit_sample_rate)
                chunk_windows.append(
                    (current_seconds, current_seconds + segment_duration)
                )
                current_seconds += segment_duration
                if chunk_index < len(unit_chunks) - 1:
                    pause_ms = unit_pauses_ms[chunk_index]
                    if pause_ms > 0:
                        current_seconds += pause_ms / 1000
                    elif unit_crossfade_ms > 0:
                        next_duration = duration_seconds(
                            unit_results[chunk_index + 1].audio,
                            unit_sample_rate,
                        )
                        current_seconds -= min(
                            unit_crossfade_ms / 1000,
                            segment_duration,
                            next_duration,
                        )
                unit_audio_segments.append(result.audio)

            window_cursor = 0
            for segment in unit["segments"]:
                segment_chunk_count = len(segment["chunks"])
                segment_windows = chunk_windows[
                    window_cursor : window_cursor + segment_chunk_count
                ]
                window_cursor += segment_chunk_count
                if not segment_windows:
                    continue
                timings.append(
                    SegmentTiming(
                        index=len(timings) + 1,
                        text=segment["display_text"],
                        start_seconds=segment_windows[0][0],
                        end_seconds=segment_windows[-1][1],
                    )
                )

            if paragraph_audio_segments and unit_sample_rate != sample_rate:
                raise ConfigError("Không thể nối audio vì sample rate các đoạn không khớp.")
            sample_rate = unit_sample_rate
            paragraph_audio_segments.append(
                concatenate_segments_with_pauses(
                    unit_audio_segments,
                    sample_rate,
                    unit_pauses_ms,
                    unit_crossfade_ms,
                )
            )
            if unit_index < len(units) - 1:
                current_seconds += paragraph_pauses_ms[unit_index] / 1000

        check_cancel(cancel_event)
        audio_label = _audio_format_label(request.output_audio_format)
        save_message = f"Đang lưu {audio_label} và SRT..." if request.output_srt else f"Đang lưu {audio_label}..."
        emit_progress(progress_callback, save_message, len(chunks), len(chunks))
        combined = concatenate_segments_with_pauses(
            paragraph_audio_segments,
            sample_rate,
            paragraph_pauses_ms,
            0,
        )
        # Finalise the filename now that the real duration is known, so the
        # optional "_{voice}_{duration}" suffix can be appended.
        final_duration = duration_seconds(combined, sample_rate)
        output_stem = base_stem
        if request.append_stem_suffix:
            output_stem = _safe_stem(
                compose_stem(
                    base_stem,
                    voice_label=self._voice_label_for_stem(request),
                    duration_seconds=final_duration,
                )
            )
        audio_path, srt_path = _available_output_pair(
            output_dir,
            output_stem,
            request.overwrite,
            request.output_srt,
            request.output_audio_format,
        )
        save_audio_atomic(
            audio_path,
            combined,
            sample_rate,
            request.output_audio_format,
            request.mp3_bitrate_kbps,
        )
        if request.output_srt and srt_path is not None:
            write_srt(srt_path, timings)

        return GenerateSpeechResult(
            job_id=job_id,
            audio_path=audio_path,
            srt_path=srt_path,
            job_dir=job_dir,
            segment_count=len(timings),
            duration_seconds=final_duration,
            message="Đã tạo audio và SRT." if request.output_srt else "Đã tạo audio.",
            pronunciation_report_path=pronunciation_report_path,
            pronunciation_snapshot_hash=pronunciation_analysis.snapshot_hash,
            pronunciation_preset_ids=pronunciation_analysis.preset_ids,
            pronunciation_term_count=pronunciation_analysis.term_count,
            pronunciation_match_count=pronunciation_analysis.match_count,
            pronunciation_conflict_count=pronunciation_analysis.conflict_count,
        )

    def generate_from_source_file(
        self,
        source_path: Path,
        request_template: GenerateSpeechRequest,
        output_dir: Path | None = None,
        progress_callback: ProgressCallback | None = None,
        cancel_event: Event | None = None,
    ) -> GenerateSpeechResult:
        check_cancel(cancel_event)
        if request_template.output_mode == "split":
            return self.generate_split_from_source_file(
                source_path,
                request_template,
                output_dir,
                progress_callback,
                cancel_event,
            )
        spec = self.registry.get(request_template.model_id)
        text = read_source_text(
            source_path,
            preserve_higgs_tags=spec.provider == "higgs_remote",
        )
        request = request_template.model_copy(
            update={
                "text": text,
                "source_path": source_path,
                "output_dir": output_dir or source_path.parent,
                "output_stem": request_template.output_stem or source_path.stem,
            }
        )
        return self.generate_audio(request, progress_callback, cancel_event)

    def generate_split_from_source_file(
        self,
        source_path: Path,
        request_template: GenerateSpeechRequest,
        output_dir: Path | None = None,
        progress_callback: ProgressCallback | None = None,
        cancel_event: Event | None = None,
    ) -> GenerateSpeechResult:
        check_cancel(cancel_event)
        spec = self.registry.get(request_template.model_id)
        units = read_source_units(
            source_path,
            preserve_higgs_tags=spec.provider == "higgs_remote",
        )
        request = request_template.model_copy(
            update={
                "source_path": source_path,
                "output_dir": output_dir or source_path.parent,
                "output_stem": request_template.output_stem or source_path.stem,
            }
        )
        request = self.freeze_pronunciation(request)
        return self._generate_split_units(request, units, progress_callback, cancel_event)

    def _engine_for(
        self,
        spec: ModelSpec,
    ) -> BaseTtsEngine:
        with self._engine_lock:
            # Keep at most one model resident: free the VRAM held by any other
            # previously-used model before loading (or reusing) this one. This is
            # the "unload old model on switch" behaviour, applied at the moment a
            # generation actually needs the engine.
            self._release_engines_locked(keep_model_id=spec.model_id)
            engine = self._engines.get(spec.model_id)
            if engine is None:
                descriptor = provider_descriptor(spec.provider)
                if descriptor is None:
                    raise ConfigError(f"Provider chưa được hỗ trợ: {spec.provider}")
                engine = descriptor.engine_factory(spec, self.engine_cache)
                self._engines[spec.model_id] = engine
            set_confirm_switch = getattr(engine, "set_confirm_switch", None)
            if callable(set_confirm_switch):
                set_confirm_switch(self._remote_switch_confirm)
        return engine

    def set_remote_switch_confirm(
        self, callback: Callable[..., bool] | None
    ) -> None:
        """Install the UI confirmation hook used by ask-before-switch mode."""
        with self._engine_lock:
            self._remote_switch_confirm = callback
            for engine in self._engines.values():
                set_confirm_switch = getattr(engine, "set_confirm_switch", None)
                if callable(set_confirm_switch):
                    set_confirm_switch(callback)

    def _release_engines_locked(self, keep_model_id: str | None = None) -> list[str]:
        """Close and drop cached engines. Caller must hold ``_engine_lock``."""
        released: list[str] = []
        for model_id in list(self._engines):
            if keep_model_id is not None and model_id == keep_model_id:
                continue
            engine = self._engines.pop(model_id)
            close = getattr(engine, "close", None)
            if callable(close):
                try:
                    close()
                except Exception:
                    pass
            released.append(model_id)
        if released:
            _free_cuda_cache()
        return released

    def release_engines(self, keep_model_id: str | None = None) -> list[str]:
        """Free VRAM held by resident models.

        Closes each cached engine (in-process models like OmniVoice and
        persistent workers like VieNeu v3 turbo release their VRAM here; one-shot
        subprocess engines are already idle) and drops it from the cache so the
        next generation reloads on demand. Returns the released model ids.

        Not safe to call while a generation using one of those models is running;
        callers should gate on their own busy state.
        """
        with self._engine_lock:
            return self._release_engines_locked(keep_model_id=keep_model_id)

    def resident_models(self) -> list[str]:
        """Model ids whose engines are currently cached (may hold VRAM)."""
        with self._engine_lock:
            return list(self._engines)

    def _ensure_request_can_generate(self, request: GenerateSpeechRequest, spec: ModelSpec) -> None:
        _validate_request_for_model(request, spec)
        uses_remote_zerotts = (
            request.runtime_target == "remote"
            and spec.provider == "zerotts"
            and spec.model_id == "zerotts_202m_official"
        )
        if not uses_remote_zerotts and not self.storage.is_installed(spec):
            if spec.provider in ("vieneu", "valtec"):
                raise ModelMissingError(
                    f"{spec.display_name} chưa được cài. "
                    "Hãy dùng nút 'Tải model đang chọn' trong tab Quản lý model."
                )
            raise ModelMissingError(
                f"Model chưa có trong dự án: {spec.display_name}. Hãy tải model trước."
            )
        missing_required = []
        descriptor = provider_descriptor(spec.provider)
        if not uses_remote_zerotts and (not descriptor or descriptor.storage_mode != "remote"):
            missing_required = [
                item
                for item in self.missing_required_models()
                if item.model_type != "tts"
            ]
        if missing_required:
            names = ", ".join(item.display_name for item in missing_required)
            raise ModelMissingError(
                f"Thiếu model phụ trợ bắt buộc: {names}. "
                "Vào tab Quản lý model và bấm Tải các model bắt buộc còn thiếu."
            )

    def _cached_prompt_path_for(
        self,
        request: GenerateSpeechRequest,
        spec: ModelSpec,
    ) -> Path | None:
        """Return the engine cache asset_dir for this request, or None if caching is not applicable."""
        if not request.voice_profile_id or not _clean_path(request.reference_audio_path):
            return None
        if spec.provider not in ("omnivoice", "qwen", "vieneu"):
            return None
        try:
            profile = self.voice_profiles.get_profile(request.voice_profile_id)
            asset_dir, cache_hit = self.voice_policy.resolve_cached_asset(
                profile, spec.model_id, spec.provider
            )
            if not cache_hit:
                _clear_engine_cache_assets(asset_dir)
            return asset_dir if asset_dir != Path() else None
        except Exception:
            return None

    def profile_quality_for_model(self, profile_id: str, model_id: str) -> ProfileCompatibility:
        profile = self.voice_profiles.get_profile(profile_id)
        return self.voice_policy.check_compatibility(profile, model_id)

    def _voice_label_for_stem(self, request: GenerateSpeechRequest) -> str:
        """Readable name of the voice used, for the filename suffix.

        Profile name when cloning, otherwise the fixed voice/Higgs voice id.
        Returns an empty string when nothing meaningful applies (e.g. a model's
        single default voice).
        """
        if request.voice_profile_id:
            try:
                return self.voice_profiles.get_profile(request.voice_profile_id).name
            except Exception:
                return ""
        if request.speaker_id:
            return str(request.speaker_id)
        higgs = getattr(request, "higgs", None)
        if higgs and higgs.voice and higgs.voice != "default":
            return str(higgs.voice)
        return ""

    def _apply_voice_profile(self, request: GenerateSpeechRequest) -> GenerateSpeechRequest:
        if not request.voice_profile_id:
            return request
        profile = self.voice_profiles.get_profile(request.voice_profile_id)
        audio_path = self.voice_policy.resolve_audio_path(profile, request.model_id)
        transcript = self.voice_policy.resolve_transcript(profile, request.model_id) or request.reference_text
        update = {
            "reference_audio_path": audio_path,
            "reference_text": transcript,
            "speaker_id": None,
        }
        return request.model_copy(update=update)

    def _generate_split_text(
        self,
        request: GenerateSpeechRequest,
        prepared_text: str,
        progress_callback: ProgressCallback | None = None,
        cancel_event: Event | None = None,
    ) -> GenerateSpeechResult:
        units = text_units_from_blank_lines(prepared_text)
        return self._generate_split_units(request, units, progress_callback, cancel_event)

    def _generate_split_units(
        self,
        request: GenerateSpeechRequest,
        units,
        progress_callback: ProgressCallback | None = None,
        cancel_event: Event | None = None,
    ) -> GenerateSpeechResult:
        check_cancel(cancel_event)
        request = self._apply_voice_profile(request)
        if not units:
            raise ConfigError("Không có nội dung để đọc.")
        emit_progress(progress_callback, f"Đã tách thành {len(units)} file audio.", 0, len(units))
        spec = self.registry.get(request.model_id)
        self._ensure_request_can_generate(request, spec)
        job_id, job_dir = self.job_store.create_job_dir()
        output_stem = _resolve_output_stem(request)
        if request.append_stem_suffix:
            # Duration is per-file here, so only the voice is baked into the
            # shared stem now; each file adds its own duration at save time.
            voice = slug_component(self._voice_label_for_stem(request))
            if voice:
                output_stem = _safe_stem(f"{output_stem}_{voice}")
        output_dir = _split_output_dir(
            _resolve_output_dir(request, job_dir),
            output_stem,
            request.overwrite,
        )
        output_dir.mkdir(parents=True, exist_ok=True)
        self.job_store.save_json(job_dir / "request.json", request)
        self.job_store.save_json(
            job_dir / "split_units.json",
            {
                "unit_count": len(units),
                "units": [{"index": unit.index, "text": unit.text} for unit in units],
            },
        )
        source_text = "\n\n".join(unit.text for unit in units)
        pronunciation_report_path, pronunciation_analysis = (
            self._save_pronunciation_report(job_dir, request, source_text)
        )

        engine = self._engine_for(spec)
        cached_path = self._cached_prompt_path_for(request, spec)
        split_jobs = []
        engine_requests: list[TtsEngineRequest] = []
        for unit in units:
            pronunciation_unit = analyze_pronunciation(
                unit.text,
                request.pronunciation_snapshot,
            )
            chunks = _chunks_for_provider(
                pronunciation_unit.speech_text,
                request.language,
                request.max_chunk_chars,
                provider=spec.provider,
                chunk_join_mode=request.chunk_join_mode,
                higgs=request.higgs,
            )
            if not chunks:
                continue
            unit_stem = f"{output_stem}_{unit.index:03}"
            audio_path = _audio_output_path(output_dir, unit_stem, request.output_audio_format)
            start_index = len(engine_requests)
            for chunk in chunks:
                engine_requests.append(
                    TtsEngineRequest(
                        text=chunk,
                        language=request.language,
                        reference_audio_path=_clean_path(request.reference_audio_path),
                        reference_text=request.reference_text,
                        speaker_id=request.speaker_id,
                        instruct=self._resolve_instruct(request, spec),
                        num_step=request.omnivoice_num_step if spec.provider == "omnivoice" else None,
                        speed=request.speed,
                        pitch_shift=request.pitch_shift,
                        emotion=request.emotion,
                        runtime_target=request.runtime_target,
                        codec_repo=_codec_repo_for_request(request, spec),
                        temperature=request.temperature if spec.provider == "vieneu" else None,
                        top_k=request.top_k if spec.provider == "vieneu" else None,
                        piper_noise_scale=(
                            request.piper_noise_scale if spec.provider == "piper" else 0.667
                        ),
                        piper_noise_w=request.piper_noise_w if spec.provider == "piper" else 0.8,
                        piper_seed=request.piper_seed if spec.provider == "piper" else None,
                        f5_nfe_step=request.f5_nfe_step if spec.provider == "f5tts" else None,
                        f5_cfg_strength=request.f5_cfg_strength if spec.provider == "f5tts" else None,
                        f5_sway_sampling_coef=request.f5_sway_sampling_coef
                        if spec.provider == "f5tts"
                        else None,
                        f5_cross_fade_duration=request.f5_cross_fade_duration
                        if spec.provider == "f5tts"
                        else None,
                        f5_target_rms=request.f5_target_rms if spec.provider == "f5tts" else None,
                        f5_remove_silence=request.f5_remove_silence if spec.provider == "f5tts" else False,
                        f5_seed=request.f5_seed if spec.provider == "f5tts" else None,
                        f5_fix_duration=request.f5_fix_duration if spec.provider == "f5tts" else None,
                        chatterbox_temperature=(
                            request.chatterbox_temperature if spec.provider == "chatterbox" else None
                        ),
                        chatterbox_top_p=request.chatterbox_top_p if spec.provider == "chatterbox" else None,
                        chatterbox_top_k=request.chatterbox_top_k if spec.provider == "chatterbox" else None,
                        chatterbox_repetition_penalty=(
                            request.chatterbox_repetition_penalty if spec.provider == "chatterbox" else None
                        ),
                        chatterbox_seed=request.chatterbox_seed if spec.provider == "chatterbox" else None,
                        chatterbox_norm_loudness=(
                            request.chatterbox_norm_loudness if spec.provider == "chatterbox" else True
                        ),
                        gpu_safety_enabled=request.gpu_safety_enabled,
                        gpu_start_temperature_c=request.gpu_start_temperature_c,
                        gpu_abort_temperature_c=request.gpu_abort_temperature_c,
                        gpu_abort_temperature_sustain_seconds=request.gpu_abort_temperature_sustain_seconds,
                        gpu_emergency_temperature_c=request.gpu_emergency_temperature_c,
                        gpu_cooldown_max_wait_seconds=request.gpu_cooldown_max_wait_seconds,
                        gpu_resume_temperature_c=request.gpu_resume_temperature_c,
                        gpu_minimum_free_vram_mb=request.gpu_minimum_free_vram_mb,
                        gpu_runtime_minimum_free_vram_mb=request.gpu_runtime_minimum_free_vram_mb,
                        gpu_maximum_utilization_percent=request.gpu_maximum_utilization_percent,
                        gpu_maximum_encoder_utilization_percent=request.gpu_maximum_encoder_utilization_percent,
                        punctuation_pause_enabled=(
                            request.punctuation_pause_enabled
                            and _supports_punctuation_pauses(spec)
                        ),
                        sentence_pause_ms=request.sentence_pause_ms,
                        sentence_pause_random_enabled=request.sentence_pause_random_enabled,
                        sentence_pause_min_ms=request.sentence_pause_min_ms,
                        sentence_pause_max_ms=request.sentence_pause_max_ms,
                        comma_pause_ms=request.comma_pause_ms,
                        comma_pause_random_enabled=request.comma_pause_random_enabled,
                        comma_pause_min_ms=request.comma_pause_min_ms,
                        comma_pause_max_ms=request.comma_pause_max_ms,
                        clause_pause_ms=request.clause_pause_ms,
                        clause_pause_random_enabled=request.clause_pause_random_enabled,
                        clause_pause_min_ms=request.clause_pause_min_ms,
                        clause_pause_max_ms=request.clause_pause_max_ms,
                        ellipsis_pause_ms=request.ellipsis_pause_ms,
                        ellipsis_pause_random_enabled=request.ellipsis_pause_random_enabled,
                        ellipsis_pause_min_ms=request.ellipsis_pause_min_ms,
                        ellipsis_pause_max_ms=request.ellipsis_pause_max_ms,
                        cancel_event=cancel_event,
                        cached_prompt_path=cached_path,
                        status_callback=lambda message: emit_progress(
                            progress_callback,
                            message,
                            0,
                            max(1, len(engine_requests)),
                        ),
                        remote_endpoint=(
                            request.remote_endpoint
                            if spec.provider == "higgs_remote"
                            else None
                        ),
                        higgs=request.higgs if spec.provider == "higgs_remote" else None,
                        provider_options=dict(request.provider_options),
                    )
                )
            split_jobs.append(
                {
                    "unit": unit,
                    "chunks": chunks,
                    "start_index": start_index,
                    "count": len(chunks),
                    "audio_path": audio_path,
                }
            )

        if not engine_requests:
            raise ConfigError("Không có nội dung để đọc.")

        check_cancel(cancel_event)
        emit_progress(
            progress_callback,
            f"Đang tạo {len(engine_requests)} đoạn cho {len(split_jobs)} file audio...",
            0,
            len(engine_requests),
        )
        # Chunk callbacks are progress/checkpoint notifications only.  They
        # must never publish production split files because a callback may be
        # delivered before the engine has returned its authoritative results.
        published_chunk_paths: dict[int, Path] = {}
        saved_durations: dict[int, float] = {}
        saved_segment_counts: dict[int, int] = {}
        saved_audio_paths: dict[int, Path] = {}

        def remember_saved(
            job_index: int,
            audio_path: Path,
            audio_duration: float,
            segment_count: int,
        ) -> None:
            saved_audio_paths[job_index] = audio_path
            saved_durations[job_index] = audio_duration
            saved_segment_counts[job_index] = segment_count

        def on_chunk_ready(chunk_index: int, path: Path) -> None:
            # Keep this for observability and future explicit preview support,
            # but do not read or encode the file here.  The worker callback is
            # not the authoritative final-result boundary.
            published_chunk_paths[chunk_index] = path

        def on_batch_progress(done: int, total: int) -> None:
            emit_progress(
                progress_callback,
                f"Đã tạo {done}/{total} đoạn cho {len(split_jobs)} file audio...",
                done,
                total,
            )

        batch_results = engine.generate_batch(
            engine_requests,
            progress_callback=on_batch_progress,
            chunk_callback=on_chunk_ready,
        )
        check_cancel(cancel_event)
        if len(batch_results) != len(engine_requests):
            raise ConfigError("Engine trả về số đoạn audio không khớp với yêu cầu.")

        # Always reconcile every split job from the authoritative batch
        # results.  A callback may have observed a partially written file, so
        # no callback-created artifact or duration is trusted for production.
        for job_index, job in enumerate(split_jobs, start=1):
            check_cancel(cancel_event)
            emit_progress(
                progress_callback,
                f"Đang lưu file {job_index}/{len(split_jobs)}...",
                job_index - 1,
                len(split_jobs),
            )
            start_index = job["start_index"]
            job_results = batch_results[start_index : start_index + job["count"]]
            audio_path, audio_duration, segment_count = self._save_split_job_outputs(
                job,
                job_results,
                request,
            )
            remember_saved(job_index, audio_path, audio_duration, segment_count)
            emit_progress(
                progress_callback,
                f"Hoàn tất file {job_index}/{len(split_jobs)}.",
                job_index,
                len(split_jobs),
            )

        audio_paths = [
            saved_audio_paths[index]
            for index in range(1, len(split_jobs) + 1)
            if index in saved_audio_paths
        ]
        total_duration = sum(saved_durations.values())
        total_segments = sum(saved_segment_counts.values())
        if len(audio_paths) != len(split_jobs):
            raise ConfigError("Không lưu đủ số file audio đã tách.")
        paragraph_pauses_ms = _paragraph_pause_values(request, len(split_jobs))

        joined_audio_path = None
        joined_duration = None
        if request.join_split_output_audio:
            joined_stem = output_stem
            if request.append_stem_suffix:
                joined_stem = f"{output_stem}_{format_duration_stem(total_duration)}"
            joined_audio_path = _audio_output_path(output_dir, joined_stem, request.output_audio_format)
            joined_duration = self._join_split_jobs_from_results(
                split_jobs,
                batch_results,
                joined_audio_path,
                request,
                paragraph_pauses_ms,
            )

        timeline_segments = _split_timeline_segments(
            split_jobs, saved_durations, paragraph_pauses_ms
        )
        if joined_duration is not None and timeline_segments:
            timeline_delta = abs(timeline_segments[-1].end_seconds - joined_duration)
            if timeline_delta > 0.5:
                raise ConfigError(
                    "Timeline SRT không khớp duration audio tổng sau finalization "
                    f"(lệch {timeline_delta:.3f}s)."
                )

        srt_path = None
        if request.output_srt:
            srt_path = output_dir / f"{output_stem}.srt"
            write_srt(srt_path, timeline_segments)

        return GenerateSpeechResult(
            job_id=job_id,
            audio_path=joined_audio_path or audio_paths[0],
            srt_path=srt_path,
            job_dir=job_dir,
            segment_count=total_segments,
            duration_seconds=joined_duration or total_duration,
            message=(
                f"Đã tạo {len(audio_paths)} file audio riêng và file tổng."
                if joined_audio_path
                else f"Đã tạo {len(audio_paths)} file audio riêng."
            ),
            item_audio_paths=audio_paths,
            item_srt_paths=[],
            pronunciation_report_path=pronunciation_report_path,
            pronunciation_snapshot_hash=pronunciation_analysis.snapshot_hash,
            pronunciation_preset_ids=pronunciation_analysis.preset_ids,
            pronunciation_term_count=pronunciation_analysis.term_count,
            pronunciation_match_count=pronunciation_analysis.match_count,
            pronunciation_conflict_count=pronunciation_analysis.conflict_count,
        )

    def _save_split_job_outputs(
        self,
        job: dict,
        job_results: list[TtsEngineResult],
        request: GenerateSpeechRequest,
    ) -> tuple[Path, float, int]:
        combined, sample_rate, segment_count = self._build_split_job_audio(job, job_results, request)
        audio_duration = duration_seconds(combined, sample_rate)
        audio_path = job["audio_path"]
        if request.append_stem_suffix:
            audio_path = _with_duration_suffix(audio_path, audio_duration)
        save_audio_atomic(
            audio_path,
            combined,
            sample_rate,
            request.output_audio_format,
            request.mp3_bitrate_kbps,
        )

        return audio_path, audio_duration, segment_count

    def _build_split_job_audio(
        self,
        job: dict,
        job_results: list[TtsEngineResult],
        request: GenerateSpeechRequest,
    ) -> tuple:
        chunks = job["chunks"]
        audio_segments = []
        sample_rate = 24000

        for result in job_results:
            sample_rate = result.sample_rate
            audio_segments.append(result.audio)

        spec = self.registry.get(request.model_id)
        combined = concatenate_segments_with_pauses(
            audio_segments,
            sample_rate,
            _chunk_pause_values(request, spec, chunks),
            _chunk_crossfade_ms(request, spec),
        )

        return combined, sample_rate, len(chunks)

    def _join_split_jobs_from_results(
        self,
        split_jobs: list[dict],
        batch_results: list[TtsEngineResult],
        output_path: Path,
        request: GenerateSpeechRequest,
        paragraph_pauses_ms: list[int],
    ) -> float:
        audio_segments = []
        sample_rate = 24000
        for job in split_jobs:
            start_index = job["start_index"]
            job_results = batch_results[start_index : start_index + job["count"]]
            combined, current_rate, _segment_count = self._build_split_job_audio(job, job_results, request)
            if audio_segments and current_rate != sample_rate:
                raise ConfigError("Không thể nối file tổng vì sample rate các file audio không khớp.")
            sample_rate = current_rate
            audio_segments.append(combined)
        combined = concatenate_segments_with_pauses(
            audio_segments,
            sample_rate,
            paragraph_pauses_ms,
            0,
        )
        save_audio_atomic(
            output_path,
            combined,
            sample_rate,
            request.output_audio_format,
            request.mp3_bitrate_kbps,
        )
        return duration_seconds(combined, sample_rate)


def _split_timeline_segments(
    split_jobs: list[dict],
    durations: dict[int, float],
    paragraph_pauses_ms: list[int],
) -> list[SegmentTiming]:
    segments: list[SegmentTiming] = []
    current_seconds = 0.0
    for index, job in enumerate(split_jobs, start=1):
        duration = durations.get(index, 0.0)
        unit = job["unit"]
        segments.append(
            SegmentTiming(
                index=index,
                text=unit.text,
                start_seconds=current_seconds,
                end_seconds=current_seconds + duration,
            )
        )
        current_seconds += duration
        if index <= len(paragraph_pauses_ms):
            current_seconds += max(0, paragraph_pauses_ms[index - 1]) / 1000
    return segments


def _prepare_text(text: str, language: str) -> str:
    if language == "vi":
        return normalize_vietnamese_text(text)
    return text.strip()


def _prepared_text_units(
    text: str,
    language: str,
    max_chunk_chars: int,
    *,
    provider: str = "",
    chunk_join_mode: str = "auto",
    higgs=None,
    pronunciation_snapshot: PronunciationSnapshot | None = None,
) -> list[dict]:
    prepared_units = []
    for unit in text_units_from_blank_lines(text):
        pronunciation_active = bool(
            pronunciation_snapshot
            and pronunciation_snapshot.enabled
            and pronunciation_snapshot.presets
        )
        if not pronunciation_active:
            display_chunks = _chunks_for_provider(
                unit.text,
                language,
                max_chunk_chars,
                provider=provider,
                chunk_join_mode=chunk_join_mode,
                higgs=higgs,
            )
            segments = [
                {"display_text": chunk, "chunks": [chunk]}
                for chunk in display_chunks
            ]
        elif provider == "higgs_remote":
            analysis = analyze_pronunciation(unit.text, pronunciation_snapshot)
            speech_chunks = _chunks_for_provider(
                analysis.speech_text,
                language,
                max_chunk_chars,
                provider=provider,
                chunk_join_mode=chunk_join_mode,
                higgs=higgs,
            )
            segments = [
                {"display_text": unit.text, "chunks": speech_chunks}
            ] if speech_chunks else []
        else:
            segments = []
            display_text = unit.text.strip()
            descriptor = provider_descriptor(provider)
            policy = resolve_chunk_join_policy(chunk_join_mode, descriptor)
            raw_display_chunks = (
                [display_text]
                if policy.delegates_text_boundaries
                else split_text(display_text, max_chunk_chars)
            )
            for display_text in raw_display_chunks:
                analysis = analyze_pronunciation(
                    display_text,
                    pronunciation_snapshot,
                )
                speech_chunks = _chunks_for_provider(
                    analysis.speech_text,
                    language,
                    max_chunk_chars,
                    provider=provider,
                    chunk_join_mode=chunk_join_mode,
                    higgs=higgs,
                )
                if speech_chunks:
                    segments.append(
                        {
                            "display_text": display_text,
                            "chunks": speech_chunks,
                        }
                    )
        chunks = [chunk for segment in segments for chunk in segment["chunks"]]
        if chunks:
            prepared_units.append(
                {
                    "unit": unit,
                    "chunks": chunks,
                    "segments": segments,
                }
            )
    return prepared_units


def _chunks_for_provider(
    text: str,
    language: str,
    max_chunk_chars: int,
    *,
    provider: str,
    chunk_join_mode: str = "auto",
    higgs=None,
) -> list[str]:
    if provider == "higgs_remote":
        analysis = validate_higgs_script(text)
        errors = [
            issue.message
            for issue in analysis.issues
            if issue.severity == "error"
        ]
        if errors:
            raise ConfigError(
                "Higgs Script không hợp lệ: " + " ".join(errors[:3])
            )
        return compile_higgs_chunks(text, language, max_chunk_chars, higgs)
    descriptor = provider_descriptor(provider)
    prepared = (
        text.strip()
        if descriptor is not None and descriptor.native_text_preprocessing
        else _prepare_text(text, language)
    )
    policy = resolve_chunk_join_policy(chunk_join_mode, descriptor)
    if policy.delegates_text_boundaries:
        return [prepared] if prepared else []
    return split_text(prepared, max_chunk_chars)


def _paragraph_pause_ms(request: GenerateSpeechRequest) -> int:
    return max(0, int(request.paragraph_pause_ms))


def _paragraph_pause_values(
    request: GenerateSpeechRequest,
    unit_count: int,
    rng: RandomSource | None = None,
) -> list[int]:
    """Resolve one pause per paragraph boundary for both audio and timeline."""
    boundary_count = max(0, int(unit_count) - 1)
    if not request.paragraph_pause_random_enabled:
        return [_paragraph_pause_ms(request)] * boundary_count
    pause_range = PauseRange(
        request.paragraph_pause_min_ms,
        request.paragraph_pause_max_ms,
    )
    return [pause_range.sample(rng) for _ in range(boundary_count)]


def _supports_punctuation_pauses(spec: ModelSpec) -> bool:
    descriptor = provider_descriptor(spec.provider)
    return bool(descriptor and "punctuation_pauses" in descriptor.controls)


def _punctuation_pause_config(
    request: GenerateSpeechRequest,
) -> PunctuationPauseConfig:
    return PunctuationPauseConfig(
        sentence_ms=request.sentence_pause_ms,
        comma_ms=request.comma_pause_ms,
        clause_ms=request.clause_pause_ms,
        ellipsis_ms=request.ellipsis_pause_ms,
        sentence_range=_pause_range_for_request(request, "sentence"),
        comma_range=_pause_range_for_request(request, "comma"),
        clause_range=_pause_range_for_request(request, "clause"),
        ellipsis_range=_pause_range_for_request(request, "ellipsis"),
    )


def _pause_range_for_request(
    request: GenerateSpeechRequest, prefix: str
) -> PauseRange | None:
    if not getattr(request, f"{prefix}_pause_random_enabled"):
        return None
    return PauseRange(
        getattr(request, f"{prefix}_pause_min_ms"),
        getattr(request, f"{prefix}_pause_max_ms"),
    )


def _chunk_pause_values(
    request: GenerateSpeechRequest,
    spec: ModelSpec,
    chunks: list[str],
) -> list[int]:
    """Choose a pause for every Core chunk boundary.

    Punctuation-aware providers use the terminal mark. Other providers retain
    the explicit technical chunk pause and never receive hidden punctuation
    controls.
    """
    if len(chunks) < 2:
        return []
    descriptor = provider_descriptor(spec.provider)
    policy = resolve_chunk_join_policy(request.chunk_join_mode, descriptor)
    if policy.effective in {"native", "crossfade", "direct"}:
        return [0] * (len(chunks) - 1)
    fallback = max(0, int(request.chunk_pause_ms))
    if policy.effective == "silence":
        return [fallback] * (len(chunks) - 1)
    if not request.punctuation_pause_enabled or not _supports_punctuation_pauses(spec):
        return [fallback] * (len(chunks) - 1)
    config = _punctuation_pause_config(request)
    return [
        pause if (pause := pause_after_text(chunk, config)) is not None else fallback
        for chunk in chunks[:-1]
    ]


def _chunk_crossfade_ms(
    request: GenerateSpeechRequest,
    spec: ModelSpec,
) -> int:
    descriptor = provider_descriptor(spec.provider)
    policy = resolve_chunk_join_policy(request.chunk_join_mode, descriptor)
    if policy.effective != "crossfade":
        return 0
    return max(0, int(request.chunk_crossfade_ms))


def _read_tts_result(path: Path) -> TtsEngineResult:
    audio, sample_rate = read_audio_mono(path)
    return TtsEngineResult(audio=audio, sample_rate=int(sample_rate))


def _clean_path(path: Path | None) -> Path | None:
    if path is None:
        return None
    if str(path).strip() == "":
        return None
    return path


def _resolve_output_dir(request: GenerateSpeechRequest, default_job_dir: Path) -> Path:
    if request.output_dir:
        return request.output_dir
    if request.source_path:
        return request.source_path.parent
    return default_job_dir


def _resolve_output_stem(request: GenerateSpeechRequest) -> str:
    if request.output_stem and request.output_stem.strip():
        return _safe_stem(request.output_stem)
    if request.source_path:
        return _safe_stem(request.source_path.stem)
    derived = default_stem_from_text(request.text)
    return _safe_stem(derived) if derived else "output"


def _validate_request_for_model(request: GenerateSpeechRequest, spec: ModelSpec) -> None:
    if request.runtime_target == "remote" and not (
        spec.provider == "zerotts" and spec.model_id == "zerotts_202m_official"
    ):
        raise ConfigError("Colab từ xa hiện chỉ hỗ trợ ZeroTTS 202M Official.")
    caps = _effective_capabilities(spec)
    voice_mode = request.voice_source_mode or "fixed"
    voice_input = effective_voice_input(spec)
    if voice_mode not in voice_input.modes:
        supported_modes = ", ".join(voice_input.modes)
        raise ConfigError(
            f"{spec.display_name} không hỗ trợ nguồn giọng '{voice_mode}'. "
            f"Nguồn giọng hợp lệ: {supported_modes}."
        )
    if request.language not in caps.supported_languages:
        supported = ", ".join(language_label(item) for item in caps.supported_languages)
        raise ConfigError(
            f"{spec.display_name} không hỗ trợ ngôn ngữ {language_label(request.language)}. "
            f"Ngôn ngữ hỗ trợ: {supported}."
        )
    if voice_mode == "profile" and not _clean_path(request.reference_audio_path):
        raise ConfigError(f"{spec.display_name} cần chọn Profile giọng để clone voice.")
    if caps.requires_voice_profile and voice_mode != "profile":
        raise ConfigError(f"{spec.display_name} cần chọn Profile giọng để clone voice.")
    if not caps.supports_voice_profile and voice_mode == "profile":
        raise ConfigError(f"{spec.display_name} không hỗ trợ Profile giọng.")
    if not caps.supports_speed and abs(request.speed - 1.0) > 0.001:
        raise ConfigError(f"{spec.display_name} chưa hỗ trợ chỉnh Tốc độ đọc.")
    descriptor = provider_descriptor(spec.provider)
    if caps.supports_speed and descriptor is not None and not (
        descriptor.speed_minimum <= request.speed <= descriptor.speed_maximum
    ):
        raise ConfigError(
            f"Tốc độ của {spec.display_name} phải từ "
            f"{descriptor.speed_minimum:g} đến {descriptor.speed_maximum:g}."
        )
    if not caps.supports_pitch_shift and abs(request.pitch_shift) > 0.001:
        raise ConfigError(f"{spec.display_name} chưa hỗ trợ Pitch shift.")
    if not caps.supports_emotion and request.emotion not in ("", "natural"):
        raise ConfigError(f"{spec.display_name} không hỗ trợ Cảm xúc.")
    if caps.supports_emotion and caps.emotions and request.emotion not in caps.emotions:
        options = ", ".join(caps.emotions)
        raise ConfigError(f"Cảm xúc không hợp lệ cho {spec.display_name}: {options}.")
    if voice_mode == "fixed" and caps.supports_voice_presets and not request.speaker_id:
        raise ConfigError(f"{spec.display_name} cần chọn Preset giọng.")
    if request.speaker_id and request.speaker_id not in spec.voice_presets:
        raise ConfigError(f"Preset giọng không hợp lệ cho {spec.display_name}.")
    if descriptor is not None:
        try:
            request.provider_options = normalize_provider_options(
                descriptor,
                request.provider_options,
                settings=provider_settings_for_model(descriptor, spec.runtime),
            )
        except ValueError as exc:
            raise ConfigError(str(exc)) from exc
    _validate_vieneu_codec(request, spec)
    _validate_f5_request(request, spec)
    _validate_chatterbox_request(request, spec)


def _validate_vieneu_codec(request: GenerateSpeechRequest, spec: ModelSpec) -> None:
    if spec.provider != "vieneu":
        return
    if not request.codec_repo:
        return
    if not spec.runtime.get("codec_repo"):
        raise ConfigError(f"{spec.display_name} dùng codec riêng, không hỗ trợ chọn NeuCodec.")
    if not valid_codec_repo(request.codec_repo):
        raise ConfigError("Codec VieNeu không hợp lệ.")
    if (
        _clean_path(request.reference_audio_path)
        and request.codec_repo == ONNX_CODEC_REPO
        and not _is_vieneu_standard_gguf(spec)
    ):
        raise ConfigError(
            "NeuCodec ONNX Fast CPU không encode được audio mẫu để clone giọng. "
            "Hãy chọn NeuCodec Standard hoặc NeuCodec Distill khi dùng Profile giọng."
        )


def _validate_f5_request(request: GenerateSpeechRequest, spec: ModelSpec) -> None:
    if spec.provider != "f5tts":
        return
    if not _clean_path(request.reference_audio_path):
        raise ConfigError(f"{spec.display_name} cần chọn Profile giọng để clone voice.")
    if not (request.reference_text or "").strip():
        raise ConfigError(
            f"{spec.display_name} cần transcript của giọng mẫu. "
            "Hãy điền Transcript trong Profile giọng trước khi tạo audio."
        )


def _validate_chatterbox_request(request: GenerateSpeechRequest, spec: ModelSpec) -> None:
    if spec.provider != "chatterbox":
        return
    if not _clean_path(request.reference_audio_path):
        raise ConfigError(f"{spec.display_name} cần chọn Profile giọng để clone voice.")


def _effective_capabilities(spec: ModelSpec) -> ModelCapabilities:
    return spec.capabilities


def _is_vieneu_standard_gguf(spec: ModelSpec) -> bool:
    return (
        spec.provider == "vieneu"
        and str(spec.runtime.get("vieneu_mode") or "") == "standard"
        and bool(spec.runtime.get("gguf_filename"))
    )


def _free_cuda_cache() -> None:
    """Best-effort release of freed CUDA allocations in the main process.

    Only matters for in-process engines (e.g. OmniVoice) that load the model
    into this process; subprocess engines free VRAM when their process exits.
    Torch may not be importable in a pure-subprocess deployment — that's fine.
    """
    try:
        import gc

        import torch
    except Exception:
        return
    try:
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            torch.cuda.ipc_collect()
    except Exception:
        pass


def _clear_engine_cache_assets(asset_dir: Path) -> None:
    if asset_dir == Path() or not asset_dir.exists():
        return
    for name in (
        "ref_codes.npy",
        "ref_codes.pkl",
        "voice_clone_prompt.pkl",
        "voice_clone_prompt.pt",
    ):
        path = asset_dir / name
        if path.exists():
            try:
                path.unlink()
            except Exception:
                pass


def _codec_repo_for_request(request: GenerateSpeechRequest, spec: ModelSpec) -> str | None:
    if spec.provider != "vieneu" or not spec.runtime.get("codec_repo"):
        return None
    return valid_codec_repo(request.codec_repo) or None


def _runtime_default(runtime: dict, key: str, fallback):
    value = runtime.get(key)
    return fallback if value is None else value


def _safe_stem(value: str) -> str:
    invalid = '<>:"/\\|?*'
    cleaned = "".join("_" if char in invalid else char for char in value)
    cleaned = cleaned.strip().strip(".")
    return cleaned or "output"


def _split_output_dir(base_dir: Path, stem: str, overwrite: bool) -> Path:
    folder = base_dir / stem
    if overwrite or not folder.exists():
        return folder
    for index in range(1, 1000):
        candidate = base_dir / f"{stem}_{index}"
        if not candidate.exists():
            return candidate
    raise ConfigError(f"Không tìm được thư mục xuất trống trong: {base_dir}")


def _audio_output_path(output_dir: Path, stem: str, output_audio_format: str) -> Path:
    return output_dir / f"{stem}{_audio_extension(output_audio_format)}"


def _with_duration_suffix(path: Path, seconds: float) -> Path:
    """Insert a ``_{duration}`` token before the file extension."""
    return path.with_name(f"{path.stem}_{format_duration_stem(seconds)}{path.suffix}")


def _audio_extension(output_audio_format: str) -> str:
    return ".mp3" if output_audio_format == "mp3" else ".wav"


def _audio_format_label(output_audio_format: str) -> str:
    return "MP3" if output_audio_format == "mp3" else "WAV"


def _available_output_pair(
    output_dir: Path,
    stem: str,
    overwrite: bool,
    output_srt: bool,
    output_audio_format: str,
) -> tuple[Path, Path | None]:
    audio_path = _audio_output_path(output_dir, stem, output_audio_format)
    srt_path = output_dir / f"{stem}.srt" if output_srt else None
    srt_available = srt_path is None or not srt_path.exists()
    if overwrite or (not audio_path.exists() and srt_available):
        return audio_path, srt_path
    for index in range(1, 1000):
        audio_candidate = _audio_output_path(output_dir, f"{stem}_{index}", output_audio_format)
        srt_candidate = output_dir / f"{stem}_{index}.srt" if output_srt else None
        srt_candidate_available = srt_candidate is None or not srt_candidate.exists()
        if not audio_candidate.exists() and srt_candidate_available:
            return audio_candidate, srt_candidate
    raise ConfigError(f"Không tìm được tên file trống trong: {output_dir}")
