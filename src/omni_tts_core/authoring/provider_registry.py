from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from omni_tts_core.authoring.providers.gemini import (
    GEMINI_MODELS,
    GeminiAuthoringProvider,
    supports_sampling_temperature,
)
from omni_tts_core.authoring.schemas import AiProviderSettings

AuthoringClientFactory = Callable[[str, AiProviderSettings], object]


@dataclass(frozen=True)
class AiProviderDescriptor:
    provider_id: str
    label: str
    client_factory: AuthoringClientFactory
    default_models: tuple[str, ...]
    supports_temperature: Callable[[str], bool]


AI_PROVIDERS: dict[str, AiProviderDescriptor] = {
    "gemini": AiProviderDescriptor(
        provider_id="gemini",
        label="Gemini",
        client_factory=GeminiAuthoringProvider,
        default_models=GEMINI_MODELS,
        supports_temperature=supports_sampling_temperature,
    )
}


def ai_provider_descriptor(provider_id: str) -> AiProviderDescriptor | None:
    return AI_PROVIDERS.get(provider_id)


def ai_provider_choices() -> list[tuple[str, str]]:
    return [
        (descriptor.label, descriptor.provider_id)
        for descriptor in AI_PROVIDERS.values()
    ]
