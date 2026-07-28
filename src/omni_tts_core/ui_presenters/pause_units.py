"""Presentation conversion for pause controls.

The generation contract remains integer milliseconds for engine accuracy and
backward-compatible preferences. User-facing controls may use seconds through
this adapter without duplicating conversion rules in a GUI.
"""

from __future__ import annotations

from dataclasses import dataclass

from omni_tts_core.ui_presenters import field_limits

MILLISECONDS_PER_SECOND = 1000
PAUSE_FIELDS = frozenset(
    {
        "sentence_pause_ms",
        "sentence_pause_min_ms",
        "sentence_pause_max_ms",
        "comma_pause_ms",
        "comma_pause_min_ms",
        "comma_pause_max_ms",
        "clause_pause_ms",
        "clause_pause_min_ms",
        "clause_pause_max_ms",
        "ellipsis_pause_ms",
        "ellipsis_pause_min_ms",
        "ellipsis_pause_max_ms",
        "chunk_pause_ms",
        "paragraph_pause_ms",
    }
)


@dataclass(frozen=True)
class PauseSecondsLimit:
    minimum: float
    maximum: float
    step: float
    decimals: int = 3


def milliseconds_to_seconds(value: float | int) -> float:
    return float(value) / MILLISECONDS_PER_SECOND


def seconds_to_milliseconds(value: float | int) -> int:
    return int(round(float(value) * MILLISECONDS_PER_SECOND))


def seconds_limit(field: str) -> PauseSecondsLimit:
    if field not in PAUSE_FIELDS:
        raise KeyError(f"Không phải trường khoảng nghỉ: {field}")
    limit = field_limits.limit(field)
    return PauseSecondsLimit(
        minimum=milliseconds_to_seconds(limit.widget_minimum),
        maximum=milliseconds_to_seconds(limit.maximum),
        step=milliseconds_to_seconds(limit.step),
    )


def default_seconds(field: str) -> float:
    value = field_limits.default_of(field)
    if value is None:
        raise KeyError(f"Trường khoảng nghỉ không có mặc định: {field}")
    return milliseconds_to_seconds(value)
