from __future__ import annotations

from omni_tts_core.authoring.schemas import VoiceContext, VoicePresentation
from omni_tts_core.authoring.stores import AuthoringStateStore
from omni_tts_shared.schemas import VoiceProfile


class VoiceContextResolver:
    """Resolve profile metadata plus user overrides without guessing in a GUI."""

    def __init__(self, store: AuthoringStateStore) -> None:
        self.store = store

    def resolve(
        self,
        *,
        profile: VoiceProfile | None = None,
        fixed_voice_id: str = "",
        presentation: VoicePresentation = "auto",
        description: str = "",
        remember: bool = False,
    ) -> VoiceContext:
        voice_key = self.voice_key(profile=profile, fixed_voice_id=fixed_voice_id)
        saved = self.store.voice_context(voice_key)
        resolved_presentation: VoicePresentation = presentation
        if presentation == "auto" and saved and saved.presentation != "auto":
            resolved_presentation = saved.presentation
        resolved_description = description.strip()
        if not resolved_description and saved:
            resolved_description = saved.description
        context = VoiceContext(
            profile_id=profile.profile_id if profile else "",
            voice_id=fixed_voice_id,
            display_name=profile.name if profile else (fixed_voice_id or "Giọng mặc định"),
            presentation=resolved_presentation,
            language=profile.language if profile else "auto",
            project=profile.project if profile else "",
            notes=profile.notes if profile else "",
            description=resolved_description,
            source="profile" if profile else ("fixed_voice" if fixed_voice_id else "default"),
        )
        if remember and voice_key:
            self.store.save_voice_context(voice_key, context)
        return context

    @staticmethod
    def voice_key(
        *,
        profile: VoiceProfile | None = None,
        fixed_voice_id: str = "",
    ) -> str:
        if profile:
            return f"profile:{profile.profile_id}"
        if fixed_voice_id:
            return f"voice:{fixed_voice_id}"
        return "voice:default"
