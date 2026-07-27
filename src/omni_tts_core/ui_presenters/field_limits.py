"""Numeric ranges for generation controls, read from the request schema itself.

A GUI that invents its own spin-box range can offer a value ``GenerateSpeechRequest``
rejects, and the user only discovers it when generation dies on a raw pydantic
error (top-k 500 on VieNeu, NFE step 1 on F5, 100 °C in the GPU thresholds…).
So the min/max always comes from the schema; a GUI supplies only presentation —
step size and decimal places.

``sentinel`` covers the "trống = ngẫu nhiên" seeds: the request wants ``None`` or
``>= 0``, while a spin box needs a real number, so ``-1`` is the agreed
GUI-side value for "không đặt seed".
"""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel

from omni_tts_shared.schemas import GenerateSpeechRequest

# step and decimals per field; decimals 0 means the GUI should use an int widget.
_PRESENTATION: dict[str, tuple[float, int]] = {
    "speed": (0.05, 2),
    "pitch_shift": (0.5, 1),
    "sentence_pause_ms": (50, 0),
    "comma_pause_ms": (10, 0),
    "clause_pause_ms": (10, 0),
    "ellipsis_pause_ms": (50, 0),
    "chunk_pause_ms": (10, 0),
    "paragraph_pause_ms": (50, 0),
    "max_chunk_chars": (20, 0),
    "temperature": (0.05, 2),
    "top_k": (10, 0),
    "f5_nfe_step": (1, 0),
    "f5_cfg_strength": (0.1, 2),
    "f5_sway_sampling_coef": (0.1, 2),
    "f5_cross_fade_duration": (0.01, 3),
    "f5_target_rms": (0.01, 3),
    "f5_fix_duration": (0.5, 2),
    "f5_seed": (1, 0),
    "chatterbox_temperature": (0.05, 2),
    "chatterbox_top_p": (0.01, 2),
    "chatterbox_top_k": (10, 0),
    "chatterbox_repetition_penalty": (0.05, 2),
    "chatterbox_seed": (1, 0),
    "gpu_start_temperature_c": (1, 0),
    "gpu_abort_temperature_c": (1, 0),
    "gpu_abort_temperature_sustain_seconds": (1, 1),
    "gpu_emergency_temperature_c": (1, 0),
    "gpu_cooldown_max_wait_seconds": (10, 0),
    "gpu_resume_temperature_c": (1, 0),
    "gpu_minimum_free_vram_mb": (256, 0),
    "gpu_runtime_minimum_free_vram_mb": (128, 0),
    "gpu_maximum_utilization_percent": (1, 0),
    "gpu_maximum_encoder_utilization_percent": (1, 0),
    "mp3_bitrate_kbps": (32, 0),
    "connect_timeout_seconds": (1, 0),
    "request_timeout_seconds": (10, 0),
    "max_retries": (1, 0),
    "max_new_tokens": (128, 0),
    "temperature": (0.05, 2),
    "top_p": (0.01, 2),
    "top_k": (10, 0),
    "seed": (1, 0),
    "initial_codec_chunk_frames": (1, 0),
    "concurrency": (1, 0),
}

# Fields where the GUI needs one extra value below the schema minimum to mean
# "không đặt" (sent to the core as None).
_SENTINELS: dict[str, float] = {
    "f5_seed": -1,
    "chatterbox_seed": -1,
    "seed": -1,
}

_FALLBACK = (0.0, 1_000_000.0)


@dataclass(frozen=True)
class FieldLimit:
    """What a GUI needs to build one numeric input for a request field."""

    field: str
    minimum: float
    maximum: float
    step: float
    decimals: int
    sentinel: float | None = None

    @property
    def widget_minimum(self) -> float:
        """Lowest value the widget may show (the sentinel when there is one)."""
        return self.minimum if self.sentinel is None else self.sentinel

    @property
    def is_integer(self) -> bool:
        return self.decimals == 0

    def ints(self) -> tuple[int, int, int]:
        """(minimum, maximum, step) for an integer widget."""
        return int(self.widget_minimum), int(self.maximum), max(1, int(self.step))

    def clamp(self, value: float) -> float:
        """Keep a stored/typed value inside what the request model accepts."""
        if self.sentinel is not None and value <= self.sentinel:
            return self.sentinel
        return min(max(value, self.minimum), self.maximum)

    def to_request_value(self, value: float | None) -> float | int | None:
        """Widget value → request value, turning the sentinel back into None."""
        if value is None:
            return None
        if self.sentinel is not None and value <= self.sentinel:
            return None
        clamped = self.clamp(value)
        return int(clamped) if self.is_integer else clamped


def limit(field: str) -> FieldLimit:
    """Range for one ``GenerateSpeechRequest`` field."""
    minimum, maximum = _bounds(field)
    step, decimals = _PRESENTATION.get(field, (1.0, 2))
    return FieldLimit(
        field=field,
        minimum=minimum,
        maximum=maximum,
        step=float(step),
        decimals=decimals,
        sentinel=_SENTINELS.get(field),
    )


def limit_for(model: type[BaseModel], field: str) -> FieldLimit:
    """Range for a nested provider schema without flattening it into the GUI."""
    minimum, maximum = _bounds_for(model, field)
    step, decimals = _PRESENTATION.get(field, (1.0, 2))
    return FieldLimit(
        field=field,
        minimum=minimum,
        maximum=maximum,
        step=float(step),
        decimals=decimals,
        sentinel=_SENTINELS.get(field),
    )


def default_of(field: str) -> float | None:
    """Schema default, when the field declares one."""
    info = GenerateSpeechRequest.model_fields.get(field)
    if info is None:
        return None
    value = info.default
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _bounds(field: str) -> tuple[float, float]:
    return _bounds_for(GenerateSpeechRequest, field)


def _bounds_for(model: type[BaseModel], field: str) -> tuple[float, float]:
    info = model.model_fields.get(field)
    if info is None:
        return _FALLBACK
    minimum, maximum = _FALLBACK
    for constraint in info.metadata:
        if hasattr(constraint, "ge"):
            minimum = float(constraint.ge)
        elif hasattr(constraint, "gt"):
            minimum = float(constraint.gt)
        if hasattr(constraint, "le"):
            maximum = float(constraint.le)
        elif hasattr(constraint, "lt"):
            maximum = float(constraint.lt)
    return minimum, maximum
