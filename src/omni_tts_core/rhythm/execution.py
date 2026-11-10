"""Turn a resolved Nhịp đọc plan into concrete job settings.

The service calls :func:`prepare_rhythm` once per job. In the "full" scope it
rewrites the old pause settings so each layer has one owner:

- ``app_split`` layers drive the punctuation splitter (values from Nhịp đọc);
- ``library_param`` layers become engine pause options (Kokoro);
- paragraph pauses and duplicated provider settings are neutralised, because
  the pacing pass owns the boundaries between paragraphs;
- the pacing pass then stretches only the layers nobody else owns.

With Nhịp đọc off nothing changes. In the "pacing_only" scope only the model
switches that do not fight the old settings act (OmniVoice long silences).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from omni_tts_core.rhythm.layers import layer_range, midpoint_ms
from omni_tts_core.rhythm.resolver import (
    RhythmPlan,
    context_for_model,
    resolve_rhythm_plan,
)
from omni_tts_shared.narrative_pacing import NarrativePacingOptions
from omni_tts_shared.schemas import GenerateSpeechRequest

# Punctuation splitter groups -> the Nhịp đọc layer that sets their pause.
_SPLIT_GROUPS = {"sentence": "sentence_end", "comma": "comma", "clause": "clause", "ellipsis": "ellipsis"}
_HIGGS_TOKEN = "<|prosody:"


@dataclass(frozen=True)
class RhythmExecution:
    plan: RhythmPlan
    request: GenerateSpeechRequest
    pacing_options: NarrativePacingOptions
    engine_options: dict[str, Any] = field(default_factory=dict)
    skip_layers: frozenset[str] = frozenset()

    @property
    def pacing_active(self) -> bool:
        return self.plan.enabled

    def report(self) -> dict[str, Any]:
        return {**self.plan.as_dict(), "engine_options": dict(self.engine_options),
                "skipped_by_pacing": sorted(self.skip_layers)}


def prepare_rhythm(request: GenerateSpeechRequest, spec: Any, *, source_kind: str = "text") -> RhythmExecution:
    options = request.narrative_pacing
    context = context_for_model(
        spec, output_mode=request.output_mode, source_kind=source_kind,
        chunk_join_mode=request.chunk_join_mode, runtime_target=request.runtime_target,
        text_has_tokens=_HIGGS_TOKEN in (request.text or ""),
    )
    plan = resolve_rhythm_plan(options, context)
    if not plan.enabled:
        return RhythmExecution(plan, request, options)
    pacing_options = options
    if source_kind == "epub":
        # Chapters, scenes and chapter music belong to the EPUB settings.
        pacing_options = options.model_copy(update={
            "sections_enabled": False,
            "music": options.music.model_copy(update={"enabled": False}),
        })
    engine_options: dict[str, Any] = {}
    if plan.switch_value("omnivoice_keep_long_silence") == "on":
        engine_options["postprocess_output"] = False
    if options.scope != "full":
        return RhythmExecution(plan, request, pacing_options, engine_options)

    updates: dict[str, Any] = {}
    split_layers = set(plan.owned_by("app_split"))
    updates["punctuation_pause_enabled"] = bool(split_layers)
    if split_layers:
        # Workers trim each fragment's edge silence so the split pause is the
        # total pause heard (Piper otherwise adds ~0.45 s around every split).
        engine_options["split_total"] = True
    for prefix, layer in _SPLIT_GROUPS.items():
        low, high = layer_range(options, layer) or (0, 0)
        if layer not in split_layers:
            low = high = 0
        updates.update({
            f"{prefix}_pause_ms": low, f"{prefix}_pause_random_enabled": low != high,
            f"{prefix}_pause_min_ms": low, f"{prefix}_pause_max_ms": high,
        })
    by_param: dict[str, list[str]] = {}
    for item in plan.layers:
        if item.mechanism == "library_param" and item.param and item.state not in {"off", "not_applicable"}:
            by_param.setdefault(item.param, []).append(item.layer)
    for param, layers in by_param.items():
        engine_options[param] = midpoint_ms(options, *layers) / 1000
    if "sentence_pause" in engine_options:
        # Core chunk seams mostly fall on sentence ends; give them the same pause.
        updates["chunk_pause_ms"] = round(engine_options["sentence_pause"] * 1000)
    if request.output_mode == "merged":
        # The pacing pass owns every boundary between paragraphs.
        updates.update(paragraph_pause_ms=0, paragraph_pause_random_enabled=False,
                       paragraph_pause_min_ms=0, paragraph_pause_max_ms=0)
    locked = set(plan.locked_controls)
    if locked & set(request.provider_options):
        updates["provider_options"] = {k: v for k, v in request.provider_options.items() if k not in locked}
    skip = frozenset(plan.owned_by("app_split", "library_param", "native_token"))
    return RhythmExecution(plan, request.model_copy(update=updates), pacing_options, engine_options, skip)
