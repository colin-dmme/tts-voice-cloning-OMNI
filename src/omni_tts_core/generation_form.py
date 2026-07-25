from __future__ import annotations

from omni_tts_core.model_registry import ModelRegistry, effective_voice_input
from omni_tts_shared.schemas import GenerationFormDescriptor, VoiceOption, VoiceSourceMode


class GenerationFormPresenter:
    """Builds a UI-agnostic form description from the selected model contract."""

    def __init__(self, registry: ModelRegistry) -> None:
        self.registry = registry

    def describe(
        self,
        model_id: str,
        preferred_mode: VoiceSourceMode | None = None,
    ) -> GenerationFormDescriptor:
        spec = self.registry.get(model_id)
        contract = effective_voice_input(spec)
        selected_mode = (
            preferred_mode
            if preferred_mode in contract.modes
            else contract.default_mode
        )
        fixed_voices = [
            VoiceOption(voice_id=voice_id, label=label)
            for voice_id, label in spec.voice_presets.items()
        ]
        requires_fixed_voice = (
            selected_mode == "fixed"
            and spec.capabilities.supports_voice_presets
            and bool(fixed_voices)
        )
        status_text = self._status_text(
            selected_mode,
            fixed_voices=bool(fixed_voices),
            profile_required=spec.capabilities.requires_voice_profile,
        )
        return GenerationFormDescriptor(
            model_id=model_id,
            voice_modes=contract.modes,
            selected_voice_mode=selected_mode,
            show_voice_mode_selector=len(contract.modes) > 1,
            fixed_label=contract.fixed_label,
            fixed_tooltip=contract.fixed_tooltip,
            profile_label=contract.profile_label,
            profile_tooltip=contract.profile_tooltip,
            fixed_voices=fixed_voices,
            default_fixed_voice_id=(
                spec.default_voice_preset
                if spec.default_voice_preset in spec.voice_presets
                else next(iter(spec.voice_presets), None)
            ),
            requires_fixed_voice=requires_fixed_voice,
            show_fixed_voice=selected_mode == "fixed" and bool(fixed_voices),
            show_profile=selected_mode == "profile",
            status_text=status_text,
        )

    @staticmethod
    def _status_text(
        mode: VoiceSourceMode,
        *,
        fixed_voices: bool,
        profile_required: bool,
    ) -> str:
        if mode == "profile":
            return (
                "Chế độ Profile: app dùng audio mẫu đã lưu để clone giọng; "
                "giọng cố định được bỏ qua."
            )
        if fixed_voices:
            return (
                "Chế độ giọng cố định: app dùng model/voice đã huấn luyện sẵn; "
                "Profile giọng và audio mẫu không được dùng."
            )
        if profile_required:
            return "Model này cần Profile giọng."
        return (
            "Chế độ giọng mặc định của model: không dùng Profile giọng "
            "hoặc audio mẫu."
        )
