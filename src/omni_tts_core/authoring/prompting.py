from __future__ import annotations

import json

from omni_tts_core.authoring.dialects.higgs import sentence_spans
from omni_tts_core.authoring.schemas import AuthoringBrief, VoiceContext
from omni_tts_core.higgs.authoring_catalog import EMOTIONS, SOUND_EFFECTS, STYLES

PROMPT_VERSION = "1"


def build_performance_prompt(
    source_text: str,
    brief: AuthoringBrief,
    voice_context: VoiceContext,
    *,
    variant_index: int,
) -> tuple[str, str]:
    """Ask for semantic decisions only; source text is rendered locally."""

    sentences = sentence_spans(source_text)
    sentence_payload = [
        {"index": item.index, "text": item.text.strip()} for item in sentences
    ]
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

Allowed emotion values: {", ".join(EMOTIONS)} or empty.
Allowed style values: {", ".join(STYLES)} or empty.
Allowed pace values: default, very_slow, slow, fast, very_fast.
Allowed pitch values: default, low, high.
Allowed expressiveness values: default, low, high.
Allowed pause_after values: none, short, long.
Allowed vocal SFX values: {", ".join(SOUND_EFFECTS)} or empty.

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
