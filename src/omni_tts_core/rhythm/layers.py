"""The pause layers of Nhịp đọc and where their values live in the options."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from omni_tts_shared.narrative_pacing import RANGE_LAYERS, NarrativePacingOptions

Layer = Literal[
    "comma", "clause", "ellipsis",
    "sentence_end", "question_end", "short_sentence",
    "connector", "paragraph", "question", "emphasis", "subtopic", "section",
    "music_theme", "music_short", "music_long",
]
Group = Literal["in_sentence", "sentence_end", "between_paragraphs", "music"]


@dataclass(frozen=True)
class LayerSpec:
    layer: Layer
    group: Group
    label: str
    # Option field holding the target total silence (ms); None for music.
    field: str | None
    # Added to the field value (the ellipsis has no field of its own yet).
    offset_ms: int = 0


LAYERS: tuple[LayerSpec, ...] = (
    LayerSpec("comma", "in_sentence", "Dấu phẩy ,", "comma_min_pause_ms"),
    LayerSpec("clause", "in_sentence", "Chấm phẩy / hai chấm ; :", "colon_pause_ms"),
    LayerSpec("ellipsis", "in_sentence", "Ba chấm …", "sentence_end_pause_ms", 30),
    LayerSpec("sentence_end", "sentence_end", "Cuối câu . !", "sentence_end_pause_ms"),
    LayerSpec("question_end", "sentence_end", "Cuối câu hỏi ?", "question_end_pause_ms"),
    LayerSpec("short_sentence", "sentence_end", "Quanh câu ngắn", "short_sentence_pause_ms"),
    LayerSpec("connector", "between_paragraphs", "Nối ý", "connector_pause_ms"),
    LayerSpec("paragraph", "between_paragraphs", "Đoạn thường", "paragraph_pause_ms"),
    LayerSpec("question", "between_paragraphs", "Sau đoạn kết bằng câu hỏi", "question_pause_ms"),
    LayerSpec("emphasis", "between_paragraphs", "Câu ngắn chốt ý", "emphasis_pause_ms"),
    LayerSpec("subtopic", "between_paragraphs", "Chuyển ý", "subtopic_pause_ms"),
    LayerSpec("section", "between_paragraphs", "Chuyển mục", "section_pause_ms"),
    LayerSpec("music_theme", "music", "Nhạc mở / kết series", None),
    LayerSpec("music_short", "music", "Nhạc chuyển ngắn", None),
    LayerSpec("music_long", "music", "Nhạc chuyển dài", None),
)
LAYER_BY_ID: dict[str, LayerSpec] = {spec.layer: spec for spec in LAYERS}
LAYER_GROUPS: dict[Group, str] = {
    "in_sentence": "Trong câu",
    "sentence_end": "Cuối câu",
    "between_paragraphs": "Giữa đoạn",
    "music": "Nhạc",
}
TEXT_LAYERS = tuple(spec.layer for spec in LAYERS if spec.group in {"in_sentence", "sentence_end"})


if {s.layer for s in LAYERS if s.field} != set(RANGE_LAYERS):
    raise ValueError("RANGE_LAYERS in omni_tts_shared.narrative_pacing is out of sync with LAYERS")
MARK_LAYERS: dict[str, str] = {
    ",": "comma", ";": "clause", ":": "clause", "…": "ellipsis",
    ".": "sentence_end", "!": "sentence_end", "?": "question_end", "？": "question_end",
}


def layer_range(options: NarrativePacingOptions, layer: str) -> tuple[int, int] | None:
    """(min, max) total silence for a layer; equal values mean a fixed pause."""
    spec = LAYER_BY_ID[layer]
    if spec.field is None:
        return None
    ranged = options.layer_ranges.get(layer)
    if ranged is not None:
        return int(ranged[0]), int(ranged[1])
    value = int(getattr(options, spec.field)) + spec.offset_ms
    return value, value


def has_range(options: NarrativePacingOptions, layer: str) -> bool:
    value = layer_range(options, layer)
    return value is not None and value[0] != value[1]


def sample_ms(options: NarrativePacingOptions, layer: str, rng) -> int:
    low, high = layer_range(options, layer) or (0, 0)
    return low if low == high else rng.randint(low, high)


def midpoint_ms(options: NarrativePacingOptions, *layers: str) -> int:
    values = [v for layer in layers if (r := layer_range(options, layer)) for v in r]
    return round((min(values) + max(values)) / 2) if values else 0
