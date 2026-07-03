from __future__ import annotations

from pathlib import Path
from threading import Event

from omni_tts_core.audio.wav_tools import concatenate_segments, duration_seconds, read_audio_mono, save_audio
from omni_tts_core.config import AppSettings
from omni_tts_core.engine_profile_cache import EngineProfileCache
from omni_tts_core.model_catalog import open_catalog
from omni_tts_core.engines.chatterbox_engine import ChatterboxSubprocessEngine
from omni_tts_core.engines.base import TtsEngineRequest, TtsEngineResult
from omni_tts_core.engines.f5tts_engine import F5TtsSubprocessEngine
from omni_tts_core.engines.omnivoice_engine import OmniVoiceEngine
from omni_tts_core.engines.qwen_engine import QwenSubprocessEngine
from omni_tts_core.engines.valtec_engine import ValtecSubprocessEngine
from omni_tts_core.engines.vieneu_engine import VieneuSubprocessEngine
from omni_tts_core.jobs.store import JobStore
from omni_tts_core.model_registry import ModelRegistry, ModelSpec
from omni_tts_core.model_storage import ModelStorage
from omni_tts_core.progress import ProgressCallback, check_cancel, emit_progress
from omni_tts_core.runtime_status import RuntimeStatusService
from omni_tts_core.subtitles.srt_builder import write_srt
from omni_tts_core.text.splitter import split_text
from omni_tts_core.text.source_reader import read_source_text, read_source_units, text_units_from_blank_lines
from omni_tts_core.text.vi_normalizer import normalize_vietnamese_text
from omni_tts_core.voice_profile_policy import ProfileCompatibility, VoiceProfilePolicy
from omni_tts_core.worker_installation import install_gpu_acceleration
from omni_tts_core.voice_profiles import VoiceProfileManager
from omni_tts_shared.errors import ConfigError, ModelMissingError
from omni_tts_shared.languages import language_label
from omni_tts_shared.schemas import (
    GenerateSpeechRequest,
    GenerateSpeechResult,
    ModelCapabilities,
    ModelStatus,
    ProfileSaveWarning,
    RuntimeStatus,
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
    ) -> None:
        self.settings = settings or AppSettings()
        self.registry = registry or ModelRegistry()
        self.storage = storage or ModelStorage(self.registry)
        self.runtime_status = RuntimeStatusService(self.registry, self.storage)
        self.voice_profiles = voice_profiles or VoiceProfileManager()
        self.engine_cache = EngineProfileCache()
        self.voice_policy = VoiceProfilePolicy(self.registry, self.engine_cache)
        self.job_store = JobStore(self.settings.outputs_root)
        self._engines: dict[
            str,
            OmniVoiceEngine
            | ChatterboxSubprocessEngine
            | VieneuSubprocessEngine
            | QwenSubprocessEngine
            | ValtecSubprocessEngine
            | F5TtsSubprocessEngine,
        ] = {}

    def list_voice_profiles(self) -> list[VoiceProfile]:
        return self.voice_profiles.list_profiles()

    def save_voice_profile(
        self,
        name: str,
        audio_path: Path,
        transcript: str,
        language: str = "vi",
        project: str = "",
        notes: str = "",
        profile_id: str | None = None,
    ) -> tuple[VoiceProfile, list[ProfileSaveWarning]]:
        return self.voice_profiles.save_profile(
            name=name,
            audio_path=audio_path,
            transcript=transcript,
            language=language,
            project=project,
            notes=notes,
            profile_id=profile_id,
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

    def supports_vieneu_codec(self, model_id: str) -> bool:
        spec = self.registry.get(model_id)
        return spec.provider == "vieneu" and bool(spec.runtime.get("codec_repo"))

    def supports_vieneu_sampling(self, model_id: str) -> bool:
        return self.registry.get(model_id).provider == "vieneu"

    def supports_f5_settings(self, model_id: str) -> bool:
        return self.registry.get(model_id).provider == "f5tts"

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
        return self.registry.get(model_id).provider == "chatterbox"

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

    def download_model(self, model_id: str) -> ModelStatus:
        return self.storage.download(model_id)

    def install_gpu_acceleration(self, model_id: str) -> str:
        spec = self.registry.get(model_id)
        message = install_gpu_acceleration(spec.provider)
        self.runtime_status.detector.clear()
        return message

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
        units = _prepared_text_units(request.text, request.language, request.max_chunk_chars)
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
        output_stem = _resolve_output_stem(request)
        output_dir.mkdir(parents=True, exist_ok=True)
        audio_path, srt_path = _available_output_pair(
            output_dir,
            output_stem,
            request.overwrite,
            request.output_srt,
            request.output_audio_format,
        )
        self.job_store.save_json(job_dir / "request.json", request)
        self.job_store.save_json(
            job_dir / "chunks.json",
            {
                "max_chunk_chars": request.max_chunk_chars,
                "sentence_pause_ms": request.sentence_pause_ms,
                "paragraph_pause_ms": _paragraph_pause_ms(request),
                "unit_count": len(units),
                "chunk_count": len(chunks),
                "units": [
                    {
                        "index": unit["unit"].index,
                        "text": unit["unit"].text,
                        "chunks": unit["chunks"],
                    }
                    for unit in units
                ],
            },
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
                speed=request.speed,
                pitch_shift=request.pitch_shift,
                emotion=request.emotion,
                runtime_target=request.runtime_target,
                codec_repo=_codec_repo_for_request(request, spec),
                temperature=request.temperature if spec.provider == "vieneu" else None,
                top_k=request.top_k if spec.provider == "vieneu" else None,
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
                cancel_event=cancel_event,
                cached_prompt_path=cached_path,
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
        sentence_pause_seconds = request.sentence_pause_ms / 1000
        paragraph_pause_seconds = _paragraph_pause_ms(request) / 1000

        for unit_index, unit in enumerate(units):
            unit_chunks = unit["chunks"]
            unit_results = batch_results[chunk_cursor : chunk_cursor + len(unit_chunks)]
            chunk_cursor += len(unit_chunks)
            unit_audio_segments = []
            unit_sample_rate = sample_rate

            for chunk_index, (chunk, result) in enumerate(zip(unit_chunks, unit_results)):
                unit_sample_rate = result.sample_rate
                segment_duration = duration_seconds(result.audio, unit_sample_rate)
                timings.append(
                    SegmentTiming(
                        index=len(timings) + 1,
                        text=chunk,
                        start_seconds=current_seconds,
                        end_seconds=current_seconds + segment_duration,
                    )
                )
                current_seconds += segment_duration
                if chunk_index < len(unit_chunks) - 1:
                    current_seconds += sentence_pause_seconds
                unit_audio_segments.append(result.audio)

            if paragraph_audio_segments and unit_sample_rate != sample_rate:
                raise ConfigError("Không thể nối audio vì sample rate các đoạn không khớp.")
            sample_rate = unit_sample_rate
            paragraph_audio_segments.append(
                concatenate_segments(
                    unit_audio_segments,
                    sample_rate,
                    request.sentence_pause_ms,
                    self.settings.crossfade_ms,
                )
            )
            if unit_index < len(units) - 1:
                current_seconds += paragraph_pause_seconds

        check_cancel(cancel_event)
        audio_label = _audio_format_label(request.output_audio_format)
        save_message = f"Đang lưu {audio_label} và SRT..." if request.output_srt else f"Đang lưu {audio_label}..."
        emit_progress(progress_callback, save_message, len(chunks), len(chunks))
        combined = concatenate_segments(paragraph_audio_segments, sample_rate, _paragraph_pause_ms(request), 0)
        save_audio(audio_path, combined, sample_rate, request.output_audio_format, request.mp3_bitrate_kbps)
        if request.output_srt and srt_path is not None:
            write_srt(srt_path, timings)

        return GenerateSpeechResult(
            job_id=job_id,
            audio_path=audio_path,
            srt_path=srt_path,
            job_dir=job_dir,
            segment_count=len(timings),
            duration_seconds=duration_seconds(combined, sample_rate),
            message="Đã tạo audio và SRT." if request.output_srt else "Đã tạo audio.",
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
        text = read_source_text(source_path)
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
        units = read_source_units(source_path)
        request = request_template.model_copy(
            update={
                "source_path": source_path,
                "output_dir": output_dir or source_path.parent,
                "output_stem": request_template.output_stem or source_path.stem,
            }
        )
        return self._generate_split_units(request, units, progress_callback, cancel_event)

    def _engine_for(
        self,
        spec: ModelSpec,
    ) -> (
        OmniVoiceEngine
        | ChatterboxSubprocessEngine
        | VieneuSubprocessEngine
        | QwenSubprocessEngine
        | ValtecSubprocessEngine
        | F5TtsSubprocessEngine
    ):
        if spec.model_id not in self._engines:
            if spec.provider == "omnivoice":
                self._engines[spec.model_id] = OmniVoiceEngine(spec, self.engine_cache)
            elif spec.provider == "chatterbox":
                self._engines[spec.model_id] = ChatterboxSubprocessEngine(spec)
            elif spec.provider == "vieneu":
                self._engines[spec.model_id] = VieneuSubprocessEngine(spec, self.engine_cache)
            elif spec.provider == "qwen":
                self._engines[spec.model_id] = QwenSubprocessEngine(spec, self.engine_cache)
            elif spec.provider == "valtec":
                self._engines[spec.model_id] = ValtecSubprocessEngine(spec)
            elif spec.provider == "f5tts":
                self._engines[spec.model_id] = F5TtsSubprocessEngine(spec)
            else:
                raise ConfigError(f"Provider chưa được hỗ trợ: {spec.provider}")
        return self._engines[spec.model_id]

    def _ensure_request_can_generate(self, request: GenerateSpeechRequest, spec: ModelSpec) -> None:
        _validate_request_for_model(request, spec)
        if not self.storage.is_installed(spec):
            if spec.provider in ("vieneu", "valtec"):
                raise ModelMissingError(
                    f"{spec.display_name} chưa được cài. "
                    "Hãy dùng nút 'Tải model đang chọn' trong tab Quản lý model."
                )
            raise ModelMissingError(
                f"Model chưa có trong dự án: {spec.display_name}. Hãy tải model trước."
            )
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

        engine = self._engine_for(spec)
        cached_path = self._cached_prompt_path_for(request, spec)
        split_jobs = []
        engine_requests: list[TtsEngineRequest] = []
        for unit in units:
            text = _prepare_text(unit.text, request.language)
            chunks = split_text(text, request.max_chunk_chars)
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
                        speed=request.speed,
                        pitch_shift=request.pitch_shift,
                        emotion=request.emotion,
                        runtime_target=request.runtime_target,
                        codec_repo=_codec_repo_for_request(request, spec),
                        temperature=request.temperature if spec.provider == "vieneu" else None,
                        top_k=request.top_k if spec.provider == "vieneu" else None,
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
                        cancel_event=cancel_event,
                        cached_prompt_path=cached_path,
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
        saved_audio_paths: dict[int, Path] = {}
        saved_durations: dict[int, float] = {}
        saved_segment_counts: dict[int, int] = {}
        chunk_paths: dict[int, Path] = {}

        def remember_saved(
            job_index: int,
            audio_path: Path,
            audio_duration: float,
            segment_count: int,
        ) -> None:
            saved_audio_paths[job_index] = audio_path
            saved_durations[job_index] = audio_duration
            saved_segment_counts[job_index] = segment_count

        def save_ready_jobs_from_chunk_paths() -> None:
            for job_index, job in enumerate(split_jobs, start=1):
                if job_index in saved_audio_paths:
                    continue
                start_index = job["start_index"]
                paths = []
                for chunk_index in range(start_index, start_index + job["count"]):
                    path = chunk_paths.get(chunk_index)
                    if path is None:
                        break
                    paths.append(path)
                else:
                    check_cancel(cancel_event)
                    job_results = [_read_tts_result(path) for path in paths]
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

        def on_chunk_ready(chunk_index: int, path: Path) -> None:
            chunk_paths[chunk_index] = path
            save_ready_jobs_from_chunk_paths()

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

        for job_index, job in enumerate(split_jobs, start=1):
            if job_index in saved_audio_paths:
                continue
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

        srt_path = None
        if request.output_srt:
            srt_path = output_dir / f"{output_stem}.srt"
            write_srt(
                srt_path,
                _split_timeline_segments(split_jobs, saved_durations, _paragraph_pause_ms(request)),
            )

        joined_audio_path = None
        joined_duration = None
        if request.join_split_output_audio:
            joined_audio_path = _audio_output_path(output_dir, output_stem, request.output_audio_format)
            joined_duration = self._join_split_jobs_from_results(
                split_jobs,
                batch_results,
                joined_audio_path,
                request,
            )

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
        )

    def _save_split_job_outputs(
        self,
        job: dict,
        job_results: list[TtsEngineResult],
        request: GenerateSpeechRequest,
    ) -> tuple[Path, float, int]:
        combined, sample_rate, segment_count = self._build_split_job_audio(job, job_results, request)
        audio_path = job["audio_path"]
        save_audio(audio_path, combined, sample_rate, request.output_audio_format, request.mp3_bitrate_kbps)

        return audio_path, duration_seconds(combined, sample_rate), segment_count

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

        combined = concatenate_segments(
            audio_segments,
            sample_rate,
            request.sentence_pause_ms,
            self.settings.crossfade_ms,
        )

        return combined, sample_rate, len(chunks)

    def _join_split_jobs_from_results(
        self,
        split_jobs: list[dict],
        batch_results: list[TtsEngineResult],
        output_path: Path,
        request: GenerateSpeechRequest,
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
        combined = concatenate_segments(audio_segments, sample_rate, _paragraph_pause_ms(request), 0)
        save_audio(output_path, combined, sample_rate, request.output_audio_format, request.mp3_bitrate_kbps)
        return duration_seconds(combined, sample_rate)


def _split_timeline_segments(
    split_jobs: list[dict],
    durations: dict[int, float],
    paragraph_pause_ms: int,
) -> list[SegmentTiming]:
    segments: list[SegmentTiming] = []
    current_seconds = 0.0
    padding_seconds = max(0, paragraph_pause_ms) / 1000
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
        current_seconds += duration + padding_seconds
    return segments


def _prepare_text(text: str, language: str) -> str:
    if language == "vi":
        return normalize_vietnamese_text(text)
    return text.strip()


def _prepared_text_units(text: str, language: str, max_chunk_chars: int) -> list[dict]:
    prepared_units = []
    for unit in text_units_from_blank_lines(text):
        prepared_text = _prepare_text(unit.text, language)
        chunks = split_text(prepared_text, max_chunk_chars)
        if chunks:
            prepared_units.append(
                {
                    "unit": unit,
                    "chunks": chunks,
                }
            )
    return prepared_units


def _paragraph_pause_ms(request: GenerateSpeechRequest) -> int:
    return max(0, int(request.paragraph_pause_ms))


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
    return "output"


def _validate_request_for_model(request: GenerateSpeechRequest, spec: ModelSpec) -> None:
    caps = _effective_capabilities(spec)
    if request.language not in caps.supported_languages:
        supported = ", ".join(language_label(item) for item in caps.supported_languages)
        raise ConfigError(
            f"{spec.display_name} không hỗ trợ ngôn ngữ {language_label(request.language)}. "
            f"Ngôn ngữ hỗ trợ: {supported}."
        )
    if caps.requires_voice_profile and not _clean_path(request.reference_audio_path):
        raise ConfigError(f"{spec.display_name} cần chọn Profile giọng để clone voice.")
    if not caps.supports_voice_profile and _clean_path(request.reference_audio_path):
        raise ConfigError(f"{spec.display_name} không hỗ trợ Profile giọng.")
    if not caps.supports_speed and abs(request.speed - 1.0) > 0.001:
        raise ConfigError(f"{spec.display_name} chưa hỗ trợ chỉnh Tốc độ đọc.")
    if not caps.supports_pitch_shift and abs(request.pitch_shift) > 0.001:
        raise ConfigError(f"{spec.display_name} chưa hỗ trợ Pitch shift.")
    if not caps.supports_emotion and request.emotion not in ("", "natural"):
        raise ConfigError(f"{spec.display_name} không hỗ trợ Cảm xúc.")
    if caps.supports_emotion and caps.emotions and request.emotion not in caps.emotions:
        options = ", ".join(caps.emotions)
        raise ConfigError(f"Cảm xúc không hợp lệ cho {spec.display_name}: {options}.")
    if caps.supports_voice_presets and not request.speaker_id and not _clean_path(request.reference_audio_path):
        if caps.supports_voice_profile:
            raise ConfigError(f"Hãy chọn Preset giọng hoặc Profile giọng cho {spec.display_name}.")
        raise ConfigError(f"{spec.display_name} cần chọn Preset giọng.")
    if request.speaker_id and request.speaker_id not in spec.voice_presets:
        raise ConfigError(f"Preset giọng không hợp lệ cho {spec.display_name}.")
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


def _clear_engine_cache_assets(asset_dir: Path) -> None:
    if asset_dir == Path() or not asset_dir.exists():
        return
    for name in ("ref_codes.npy", "ref_codes.pkl", "voice_clone_prompt.pkl"):
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
