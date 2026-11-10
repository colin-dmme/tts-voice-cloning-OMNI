"""Built-in Nhịp đọc presets and the first-time conversion from old pause settings."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from omni_tts_shared.narrative_pacing import NarrativePacingOptions

_BETWEEN = ("connector", "paragraph", "question", "emphasis", "subtopic", "section")


def _scaled(base: NarrativePacingOptions, factor: float, layers: tuple[str, ...]) -> dict[str, list[int]]:
    from omni_tts_core.rhythm.layers import layer_range

    ranges = {}
    for layer in layers:
        low, high = layer_range(base, layer) or (0, 0)
        ranges[layer] = [round(low * factor), round(high * factor)]
    return ranges


def _natural() -> dict[str, Any]:
    return {}


def _audiobook() -> dict[str, Any]:
    base = NarrativePacingOptions()
    ranges = _scaled(base, 1.25, _BETWEEN)
    ranges.update(sentence_end=[650, 750], question_end=[720, 820], comma=[220, 300])
    return {"layer_ranges": ranges}


def _news() -> dict[str, Any]:
    base = NarrativePacingOptions()
    ranges = _scaled(base, 0.8, (*_BETWEEN, "sentence_end", "question_end", "clause"))
    return {"layer_ranges": ranges, "short_sentence_pause_ms": 0}


# id -> (label, description, factory of option updates)
RHYTHM_PRESETS: dict[str, tuple[str, str, Any]] = {
    "podcast": ("Podcast tự nhiên", "Mặc định, theo số đo giọng đọc thật.", _natural),
    "audiobook": ("Đọc chậm / sách nói", "Nghỉ giữa đoạn dài hơn 25%, cuối câu 0,65–0,75s.", _audiobook),
    "news": ("Nhanh / tin tức", "Nghỉ ngắn hơn 20%, bỏ nhịp quanh câu ngắn.", _news),
}


def apply_rhythm_preset(options: NarrativePacingOptions, preset_id: str) -> NarrativePacingOptions:
    """Reset the pause values to a preset; switches, scope and music are kept."""
    if preset_id not in RHYTHM_PRESETS:
        raise ValueError(f"Không có preset nhịp đọc '{preset_id}'.")
    fresh = NarrativePacingOptions()
    keep = {"enabled", "scope", "model_switches", "music", "seed", "section_before_units",
            "sections_enabled", "sentence_pauses_enabled", "section_interval_minutes"}
    values = {k: v for k, v in fresh.model_dump().items() if k not in keep}
    values.update(RHYTHM_PRESETS[preset_id][2]())
    return options.model_copy(update=values)


# Rough silence a model leaves on its own when it reads straight through
# (phase-0 medians across CPU models). Old settings added silence on top of it.
_NATURAL_MS = {"sentence": 300, "comma": 150, "clause": 120, "ellipsis": 250}


def rhythm_from_legacy(values: Mapping[str, Any]) -> dict[str, list[int]]:
    """Suggest Nhịp đọc ranges from the old "added silence" settings.

    Old punctuation pauses were inserted on top of what the model leaves; Nhịp
    đọc works in total silence, so the model's typical natural pause is added.
    The result is a suggestion for the user to confirm, never applied silently.
    """
    def pair(prefix: str) -> tuple[int, int]:
        if values.get(f"{prefix}_pause_random_enabled"):
            return int(values.get(f"{prefix}_pause_min_ms", 0)), int(values.get(f"{prefix}_pause_max_ms", 0))
        fixed = int(values.get(f"{prefix}_pause_ms", 0))
        return fixed, fixed

    ranges: dict[str, list[int]] = {}
    if values.get("punctuation_pause_enabled"):
        for prefix, layers in (("sentence", ("sentence_end", "question_end")), ("comma", ("comma",)),
                               ("clause", ("clause",)), ("ellipsis", ("ellipsis",))):
            low, high = pair(prefix)
            natural = _NATURAL_MS[prefix]
            for layer in layers:
                ranges[layer] = [min(8000, low + natural), min(8000, high + natural)]
    low, high = pair("paragraph")
    if high > 0:
        ranges["paragraph"] = [low, high]
    return ranges
