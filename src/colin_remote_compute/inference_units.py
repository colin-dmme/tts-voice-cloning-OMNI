"""Common unit submission for remote provider adapters."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .broker.models import RemoteTtsRequest


@dataclass(frozen=True)
class InferenceUnit:
    request: RemoteTtsRequest
    destination: Path
    cancel_event: object = None
    reference_audio: bytes | None = None


def execute_units(coordinator, units):
    lifecycle = getattr(coordinator, "lifecycle", None)
    if getattr(lifecycle, "is_cpu_pool", False):
        prepared = list(units)
        lifecycle.dispatch(coordinator, prepared)
        yield from prepared
        return
    for unit in units:
        options = {"cancel_event": unit.cancel_event}
        if unit.reference_audio is not None:
            options["reference_audio"] = unit.reference_audio
        coordinator.execute(unit.request, unit.destination, **options)
        yield unit
