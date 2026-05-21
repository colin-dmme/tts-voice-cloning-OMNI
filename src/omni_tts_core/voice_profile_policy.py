from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel

from omni_tts_core.model_registry import ModelRegistry
from omni_tts_shared.schemas import AudioSampleMeta, VoiceProfile

if TYPE_CHECKING:
    from omni_tts_core.engine_profile_cache import EngineProfileCache


class ProfileCompatibility(BaseModel):
    status: Literal["ok", "warn", "error"]
    message: str
    selected_sample_id: str = ""


class VoiceProfilePolicy:
    def __init__(
        self,
        registry: ModelRegistry,
        cache: "EngineProfileCache | None" = None,
    ) -> None:
        self._registry = registry
        self._cache = cache

    def check_compatibility(self, profile: VoiceProfile, model_id: str) -> ProfileCompatibility:
        spec = self._registry.get(model_id)
        hints = spec.ref_audio_hints
        sample = self._selected_sample(profile, model_id)
        duration = sample.duration_seconds if sample is not None else profile.duration_seconds
        transcript = self._selected_transcript(profile, model_id)

        if duration == 0.0:
            return ProfileCompatibility(status="ok", message="")

        opt_min = hints.optimal_min_seconds
        opt_max = hints.optimal_max_seconds

        if duration < hints.min_seconds:
            return ProfileCompatibility(
                status="error",
                message=f"Audio quá ngắn ({duration:.1f}s). Model cần ít nhất {hints.min_seconds:.1f}s.",
            )
        if duration > hints.max_seconds:
            return ProfileCompatibility(
                status="warn",
                message=f"Audio dài ({duration:.1f}s) vượt giới hạn {hints.max_seconds:.1f}s.",
            )

        issues: list[str] = []
        if duration < opt_min:
            issues.append(f"ngắn hơn tối ưu ({duration:.1f}s < {opt_min:.1f}s)")
        elif duration > opt_max:
            issues.append(f"dài hơn tối ưu ({duration:.1f}s > {opt_max:.1f}s)")

        if hints.needs_transcript and not transcript.strip():
            issues.append("model cần transcript nhưng chưa điền")

        if issues:
            return ProfileCompatibility(
                status="warn",
                message="Lưu ý: " + "; ".join(issues) + ".",
            )

        parts = [f"{duration:.1f}s"]
        if (hints.needs_transcript or spec.provider == "omnivoice") and transcript.strip():
            parts.append("có transcript")
        return ProfileCompatibility(status="ok", message="Phù hợp (" + ", ".join(parts) + ")")

    def select_best_sample(self, profile: VoiceProfile, model_id: str) -> str:
        return profile.default_sample_id or ""

    def resolve_audio_path(self, profile: VoiceProfile, model_id: str) -> Path:
        sample = self._selected_sample(profile, model_id)
        if sample is not None:
            return sample.audio_path
        return profile.audio_path

    def resolve_transcript(self, profile: VoiceProfile, model_id: str) -> str:
        spec = self._registry.get(model_id)
        transcript = self._selected_transcript(profile, model_id)
        if spec.provider == "omnivoice" and transcript.strip():
            return transcript
        if not spec.ref_audio_hints.needs_transcript:
            return ""
        return transcript

    def resolve_cached_asset(
        self,
        profile: VoiceProfile,
        model_id: str,
        provider: str,
    ) -> tuple[Path, bool]:
        """
        Returns (asset_dir, cache_hit).
        asset_dir is where the engine should read/write cached assets.
        cache_hit=True when meta.json hashes are valid — engine still checks
        whether the specific asset file exists before loading.
        """
        if self._cache is None:
            return Path(), False
        sample_id = self.select_best_sample(profile, model_id)
        audio_path = self.resolve_audio_path(profile, model_id)
        transcript = self.resolve_transcript(profile, model_id)
        asset_dir = self._cache.asset_dir(profile.profile_id, sample_id, provider, model_id)
        hit = self._cache.is_valid(asset_dir, audio_path, transcript)
        return asset_dir, hit

    def _selected_sample(self, profile: VoiceProfile, model_id: str) -> AudioSampleMeta | None:
        sample_id = self.select_best_sample(profile, model_id)
        if sample_id:
            for sample in profile.extra_samples:
                if sample.sample_id == sample_id:
                    return sample
        return None

    def _selected_transcript(self, profile: VoiceProfile, model_id: str) -> str:
        sample = self._selected_sample(profile, model_id)
        if sample is not None:
            return sample.transcript
        return profile.transcript
