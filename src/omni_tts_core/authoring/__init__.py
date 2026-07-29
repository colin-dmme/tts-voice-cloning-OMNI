"""Provider-neutral AI-assisted speech authoring.

The authoring layer produces a semantic performance plan first.  A dialect
adapter then renders that plan into the syntax understood by a TTS provider
(Higgs Script today, other inline/request-based controls later).
"""

from omni_tts_core.authoring.schemas import (
    AiProviderSettings,
    AuthoringBrief,
    AuthoringCandidate,
    AuthoringPreset,
    AuthoringSession,
    PerformanceDecision,
    PerformancePlan,
    VoiceContext,
)

__all__ = [
    "AiProviderSettings",
    "AuthoringBrief",
    "AuthoringCandidate",
    "AuthoringPreset",
    "AuthoringSession",
    "PerformanceDecision",
    "PerformancePlan",
    "VoiceContext",
]
