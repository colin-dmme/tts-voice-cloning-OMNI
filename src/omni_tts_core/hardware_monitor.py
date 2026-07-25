"""Global hardware telemetry: GPU (nvidia-smi) + CPU/RAM (psutil).

Ported and extended from the S3Voice reference probe. Produces a superset
HardwareSnapshot that both the live UI (hardware bar + temperature chart) and
the GPU safety guard consume. A short cache prevents the UI poll and the guard
poll from spawning nvidia-smi twice within the same window.
"""

from __future__ import annotations

import csv
import io
import shutil
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from threading import Lock

import psutil

from omni_tts_core.gpu_safety import GpuSnapshot

CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


@dataclass(frozen=True)
class HardwareSnapshot:
    timestamp: float
    gpu_name: str | None = None
    gpu_temperature_c: float | None = None
    gpu_utilization_percent: float | None = None
    gpu_encoder_utilization_percent: float | None = None
    gpu_memory_total_mb: int | None = None
    gpu_memory_used_mb: int | None = None
    gpu_power_w: float | None = None
    gpu_power_limit_w: float | None = None
    cpu_utilization_percent: float | None = None
    cpu_temperature_c: float | None = None
    ram_used_gb: float | None = None
    ram_total_gb: float | None = None
    error: str | None = None

    @property
    def gpu_memory_free_mb(self) -> int | None:
        if self.gpu_memory_total_mb is None or self.gpu_memory_used_mb is None:
            return None
        return max(0, self.gpu_memory_total_mb - self.gpu_memory_used_mb)

    @property
    def has_gpu(self) -> bool:
        return self.gpu_temperature_c is not None and self.gpu_memory_total_mb is not None


class HardwareProbe:
    # encoder utilization is required by the GPU safety guard; extra vs S3Voice.
    GPU_FIELDS = (
        "name",
        "temperature.gpu",
        "utilization.gpu",
        "utilization.encoder",
        "memory.total",
        "memory.used",
        "power.draw",
        "power.limit",
    )

    def __init__(
        self,
        nvidia_smi: str | Path | None = None,
        cache_seconds: float = 1.0,
    ) -> None:
        # None auto-detects; an explicit "" forces GPU-less mode (used in tests).
        if nvidia_smi is None:
            self.nvidia_smi = str(shutil.which("nvidia-smi") or "")
        else:
            self.nvidia_smi = str(nvidia_smi)
        self._cache_seconds = max(0.0, cache_seconds)
        self._lock = Lock()
        self._cached: HardwareSnapshot | None = None
        psutil.cpu_percent(interval=None)

    def snapshot(self) -> HardwareSnapshot:
        """Return a cached snapshot if fresh, else probe hardware."""
        with self._lock:
            now = time.time()
            if (
                self._cached is not None
                and now - self._cached.timestamp < self._cache_seconds
            ):
                return self._cached
            snapshot = self._probe()
            self._cached = snapshot
            return snapshot

    def _probe(self) -> HardwareSnapshot:
        timestamp = time.time()
        cpu_percent = psutil.cpu_percent(interval=None)
        memory = psutil.virtual_memory()
        base = {
            "timestamp": timestamp,
            "cpu_utilization_percent": cpu_percent,
            "cpu_temperature_c": self._cpu_temperature(),
            "ram_used_gb": memory.used / (1024**3),
            "ram_total_gb": memory.total / (1024**3),
        }
        if not self.nvidia_smi:
            return HardwareSnapshot(**base, error="Không tìm thấy nvidia-smi")
        try:
            command = [
                self.nvidia_smi,
                f"--query-gpu={','.join(self.GPU_FIELDS)}",
                "--format=csv,noheader,nounits",
            ]
            result = subprocess.run(
                command,
                check=True,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=5,
                creationflags=CREATE_NO_WINDOW,
            )
            row = next(csv.reader(io.StringIO(result.stdout)))
            values = [item.strip() for item in row]
            return HardwareSnapshot(
                **base,
                gpu_name=values[0] or None,
                gpu_temperature_c=self._float(values[1]),
                gpu_utilization_percent=self._float(values[2]),
                gpu_encoder_utilization_percent=self._float(values[3]),
                gpu_memory_total_mb=self._int(values[4]),
                gpu_memory_used_mb=self._int(values[5]),
                gpu_power_w=self._float(values[6]),
                gpu_power_limit_w=self._float(values[7]),
            )
        except (OSError, subprocess.SubprocessError, StopIteration, IndexError) as error:
            return HardwareSnapshot(**base, error=str(error))

    @staticmethod
    def _float(value: str) -> float | None:
        if not value or value.casefold() in {"n/a", "[n/a]"}:
            return None
        try:
            return float(value)
        except ValueError:
            return None

    @classmethod
    def _int(cls, value: str) -> int | None:
        number = cls._float(value)
        return round(number) if number is not None else None

    @staticmethod
    def _cpu_temperature() -> float | None:
        getter = getattr(psutil, "sensors_temperatures", None)
        if getter is None:
            return None
        try:
            groups = getter(fahrenheit=False)
        except (OSError, NotImplementedError, AttributeError):
            return None
        values = [
            float(entry.current)
            for entries in groups.values()
            for entry in entries
            if entry.current is not None and 0 < float(entry.current) < 150
        ]
        return max(values) if values else None


def to_gpu_snapshot(snapshot: HardwareSnapshot) -> GpuSnapshot:
    """Adapt a HardwareSnapshot into the GpuSnapshot the safety guard expects.

    Raises RuntimeError when GPU telemetry is unavailable, so the guard treats
    it exactly like a failed nvidia-smi read (stops the queue rather than
    running blind).
    """
    if not snapshot.has_gpu:
        detail = snapshot.error or "GPU telemetry không khả dụng"
        raise RuntimeError(detail)
    return GpuSnapshot(
        timestamp=datetime.now().isoformat(timespec="seconds"),
        name=snapshot.gpu_name or "",
        driver_version="",
        temperature_c=int(round(snapshot.gpu_temperature_c or 0)),
        gpu_utilization_percent=int(round(snapshot.gpu_utilization_percent or 0)),
        encoder_utilization_percent=int(round(snapshot.gpu_encoder_utilization_percent or 0)),
        memory_total_mb=int(snapshot.gpu_memory_total_mb or 0),
        memory_used_mb=int(snapshot.gpu_memory_used_mb or 0),
        memory_free_mb=int(snapshot.gpu_memory_free_mb or 0),
    )
