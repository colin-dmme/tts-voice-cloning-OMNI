from __future__ import annotations

from pathlib import Path
from threading import Event

from omni_tts_core.audio.wav_tools import concatenate_segments, duration_seconds, save_wav
from omni_tts_core.config import AppSettings
from omni_tts_core.engine_profile_cache import EngineProfileCache
from omni_tts_core.model_catalog import open_catalog
from omni_tts_core.engines.base import TtsEngineRequest
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
            OmniVoiceEngine | VieneuSubprocessEngine | QwenSubprocessEngine | ValtecSubprocessEngine,
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

    def generate_audio(
        self,
        request: GenerateSpeechRequest,
        progress_callback: ProgressCallback | None = None,
        cancel_event: Event | None = None,
    ) -> GenerateSpeechResult:
        check_cancel(cancel_event)
        request = self._apply_voice_profile(request)
        spec = self.registry.get(request.model_id)
        self._ensure_request_can_generate(request, spec)
        if request.output_mode == "split":
            return self._generate_split_text(request, request.text, progress_callback, cancel_event)
        text = _prepare_text(request.text, request.language)
        chunks = split_text(text, request.max_chunk_chars)
        if not chunks:
            raise ConfigError("Không có nội dung để đọc.")
        emit_progress(progress_callback, f"Đã tách thành {len(chunks)} đoạn.", 0, len(chunks))

        job_id, job_dir = self.job_store.create_job_dir()
        output_dir = _resolve_output_dir(request, job_dir)
        output_stem = _resolve_output_stem(request)
        output_dir.mkdir(parents=True, exist_ok=True)
        audio_path, srt_path = _available_output_pair(
            output_dir,
            output_stem,
            request.overwrite,
            request.output_srt,
        )
        self.job_store.save_json(job_dir / "request.json", request)
        self.job_store.save_json(
            job_dir / "chunks.json",
            {
                "max_chunk_chars": request.max_chunk_chars,
                "chunk_count": len(chunks),
                "chunks": chunks,
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
                cancel_event=cancel_event,
                cached_prompt_path=cached_path,
            )
            for chunk in chunks
        ]
        check_cancel(cancel_event)
        emit_progress(progress_callback, f"Đang tạo {len(chunks)} đoạn...", 0, len(chunks))
        batch_results = engine.generate_batch(engine_requests)
        check_cancel(cancel_event)
        emit_progress(progress_callback, f"Hoàn tất {len(chunks)} đoạn.", len(chunks), len(chunks))

        audio_segments = []
        timings: list[SegmentTiming] = []
        current_seconds = 0.0
        sample_rate = 24000
        pause_seconds = request.sentence_pause_ms / 1000

        for index, (chunk, result) in enumerate(zip(chunks, batch_results), start=1):
            sample_rate = result.sample_rate
            segment_duration = duration_seconds(result.audio, sample_rate)
            timings.append(
                SegmentTiming(
                    index=index,
                    text=chunk,
                    start_seconds=current_seconds,
                    end_seconds=current_seconds + segment_duration,
                )
            )
            current_seconds += segment_duration + pause_seconds
            audio_segments.append(result.audio)

        check_cancel(cancel_event)
        save_message = "Đang lưu WAV và SRT..." if request.output_srt else "Đang lưu WAV..."
        emit_progress(progress_callback, save_message, len(chunks), len(chunks))
        combined = concatenate_segments(audio_segments, sample_rate, request.sentence_pause_ms, self.settings.crossfade_ms)
        save_wav(audio_path, combined, sample_rate)
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
    ) -> OmniVoiceEngine | VieneuSubprocessEngine | QwenSubprocessEngine | ValtecSubprocessEngine:
        if spec.model_id not in self._engines:
            if spec.provider == "omnivoice":
                self._engines[spec.model_id] = OmniVoiceEngine(spec, self.engine_cache)
            elif spec.provider == "vieneu":
                self._engines[spec.model_id] = VieneuSubprocessEngine(spec, self.engine_cache)
            elif spec.provider == "qwen":
                self._engines[spec.model_id] = QwenSubprocessEngine(spec, self.engine_cache)
            elif spec.provider == "valtec":
                self._engines[spec.model_id] = ValtecSubprocessEngine(spec)
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
            audio_path = output_dir / f"{unit_stem}.wav"
            srt_path = output_dir / f"{unit_stem}.srt" if request.output_srt else None
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
                    "srt_path": srt_path,
                }
            )

        if not engine_requests:
            raise ConfigError("Không có nội dung để đọc.")

        check_cancel(cancel_event)
        emit_progress(
            progress_callback,
            f"Đang tạo {len(engine_requests)} đoạn cho {len(split_jobs)} file audio...",
            0,
            len(units),
        )
        batch_results = engine.generate_batch(engine_requests)
        check_cancel(cancel_event)
        if len(batch_results) != len(engine_requests):
            raise ConfigError("Engine trả về số đoạn audio không khớp với yêu cầu.")

        audio_paths: list[Path] = []
        srt_paths: list[Path] = []
        total_duration = 0.0
        total_segments = 0
        pause_seconds = request.sentence_pause_ms / 1000

        for job_index, job in enumerate(split_jobs, start=1):
            check_cancel(cancel_event)
            emit_progress(
                progress_callback,
                f"Đang lưu file {job_index}/{len(split_jobs)}...",
                job_index - 1,
                len(units),
            )
            start_index = job["start_index"]
            job_results = batch_results[start_index : start_index + job["count"]]
            chunks = job["chunks"]

            audio_segments = []
            timings: list[SegmentTiming] = []
            current_seconds = 0.0
            sample_rate = 24000
            for segment_index, (chunk, result) in enumerate(zip(chunks, job_results), start=1):
                sample_rate = result.sample_rate
                segment_duration = duration_seconds(result.audio, sample_rate)
                timings.append(
                    SegmentTiming(
                        index=segment_index,
                        text=chunk,
                        start_seconds=current_seconds,
                        end_seconds=current_seconds + segment_duration,
                    )
                )
                current_seconds += segment_duration + pause_seconds
                audio_segments.append(result.audio)

            combined = concatenate_segments(
                audio_segments,
                sample_rate,
                request.sentence_pause_ms,
                self.settings.crossfade_ms,
            )
            audio_path = job["audio_path"]
            srt_path = job["srt_path"]
            save_wav(audio_path, combined, sample_rate)
            if request.output_srt and srt_path is not None:
                write_srt(srt_path, timings)

            audio_paths.append(audio_path)
            if srt_path is not None:
                srt_paths.append(srt_path)
            total_duration += duration_seconds(combined, sample_rate)
            total_segments += len(timings)
            emit_progress(
                progress_callback,
                f"Hoàn tất file {job_index}/{len(split_jobs)}.",
                job_index,
                len(units),
            )

        return GenerateSpeechResult(
            job_id=job_id,
            audio_path=audio_paths[0],
            srt_path=srt_paths[0] if srt_paths else None,
            job_dir=job_dir,
            segment_count=total_segments,
            duration_seconds=total_duration,
            message=f"Đã tạo {len(audio_paths)} file audio riêng.",
            item_audio_paths=audio_paths,
            item_srt_paths=srt_paths,
        )


def _prepare_text(text: str, language: str) -> str:
    if language == "vi":
        return normalize_vietnamese_text(text)
    return text.strip()


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


def _available_output_pair(
    output_dir: Path,
    stem: str,
    overwrite: bool,
    output_srt: bool,
) -> tuple[Path, Path | None]:
    audio_path = output_dir / f"{stem}.wav"
    srt_path = output_dir / f"{stem}.srt" if output_srt else None
    srt_available = srt_path is None or not srt_path.exists()
    if overwrite or (not audio_path.exists() and srt_available):
        return audio_path, srt_path
    for index in range(1, 1000):
        audio_candidate = output_dir / f"{stem}_{index}.wav"
        srt_candidate = output_dir / f"{stem}_{index}.srt" if output_srt else None
        srt_candidate_available = srt_candidate is None or not srt_candidate.exists()
        if not audio_candidate.exists() and srt_candidate_available:
            return audio_candidate, srt_candidate
    raise ConfigError(f"Không tìm được tên file trống trong: {output_dir}")
