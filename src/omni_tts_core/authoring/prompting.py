from __future__ import annotations

import json

from omni_tts_core.authoring.catalog import AuthoringFeatureDescriptor
from omni_tts_core.authoring.dialects.higgs import sentence_spans
from omni_tts_core.authoring.schemas import AuthoringBrief, VoiceContext

PROMPT_VERSION = "2"


def build_performance_prompt(
    source_text: str,
    brief: AuthoringBrief,
    voice_context: VoiceContext,
    feature_descriptors: tuple[AuthoringFeatureDescriptor, ...],
    *,
    variant_index: int,
) -> tuple[str, str]:
    """Ask for semantic decisions only; source text is rendered locally."""

    sentences = sentence_spans(source_text)
    sentence_payload = [
        {"index": item.index, "text": item.text.strip()} for item in sentences
    ]
    allowed_lines: list[str] = []
    disabled_features: list[str] = []
    for descriptor in feature_descriptors:
        selection = brief.control_scope.selection(descriptor.key)
        supported = {item.value for item in descriptor.values}
        allowed = [
            value
            for value in selection.allowed_values
            if value in supported
        ]
        if not selection.enabled or not allowed:
            disabled_features.append(descriptor.key)
            allowed_lines.append(
                f"- {descriptor.key}: DISABLED; always return its empty/default value."
            )
        else:
            allowed_lines.append(
                f"- {descriptor.key}: {', '.join(allowed)}."
            )
    control_contract = "\n".join(allowed_lines)
    disabled_contract = ", ".join(disabled_features) or "none"
    system = f"""
You are a professional speech performance director for text-to-speech.
Analyze meaning, rhetoric, context, and the selected narrator voice. Return ONLY
a JSON object. Do not rewrite, translate, summarize, correct, or repeat the
source text. Your output is a provider-neutral performance plan; application
code will render provider syntax later.

JSON shape:
{{
  "summary": "short Vietnamese explanation",
  "warnings": ["optional warning"],
  "decisions": [
    {{
      "sentence_index": 0,
      "emotion": "",
      "style": "",
      "pace": "default",
      "pitch": "default",
      "expressiveness": "default",
      "pause_after": "none",
      "sfx_before": "",
      "sfx_cue": "",
      "importance": 1,
      "reason": "short Vietnamese reason"
    }}
  ]
}}

Strict control contract:
{control_contract}
Disabled feature keys: {disabled_contract}.
For disabled feature keys, do not infer or substitute a related feature.
Application code will enforce every allow-list after your response.

Rules:
- Use sparse, meaningful decisions. No decision is required for a neutral sentence.
- Sentence-level delivery applies only to the selected sentence.
- A science/explainer hook must sound intelligent and controlled, not like a
  trailer or a childish performance.
- Do not use pitch to turn a voice into male or female.
- A pause is for a semantic turn, reveal, contrast, or deliberate beat.
- Vocal SFX is allowed only when the exact written cue already exists in the
  sentence. Put that exact substring in sfx_cue. Never invent cue words.
- Avoid singing/shouting for science unless the user explicitly requests it.
- One sentence should normally receive one emotion and at most one additional
  delivery adjustment.
""".strip()
    user = {
        "brief": brief.model_dump(mode="json"),
        "voice_context": voice_context.model_dump(mode="json"),
        "candidate_variant": variant_index + 1,
        "sentences": sentence_payload,
    }
    return system, json.dumps(user, ensure_ascii=False, indent=2)
