from __future__ import annotations

import json
import re
import subprocess
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from threading import Event, Lock
from typing import Callable, Protocol

from omni_tts_core.paths import ensure_dir
from omni_tts_core.progress import check_cancel
from omni_tts_shared.errors import GpuSafetyError


StatusCallback = Callable[[str], None]


class WorkerPauseControl(Protocol):
    def suspend(self) -> None: ...

    def resume(self) -> None: ...


@dataclass(frozen=True)
class GpuSafetyConfig:
    enabled: bool = True
    start_temperature_c: int = 75
    abort_temperature_c: int = 82
    abort_temperature_sustain_seconds: float = 10.0
    emergency_temperature_c: int = 90
    cooldown_initial_wait_seconds: float = 10.0
    cooldown_max_wait_seconds: float = 300.0
    resume_temperature_c: int = 72
    minimum_free_vram_mb: int = 6000
    runtime_minimum_free_vram_mb: int = 700
    maximum_gpu_utilization_percent: int = 20
    maximum_encoder_utilization_percent: int = 5
    poll_seconds: float = 2.0
    wait_timeout_seconds: float = 7200.0
    safe_samples_required: int = 3

    @classmethod
    def from_runtime(cls, runtime: dict, overrides: dict | None = None) -> "GpuSafetyConfig":
        values = dict(runtime)
        values.update({key: value for key, value in (overrides or {}).items() if value is not None})
        return cls(
            enabled=bool(values.get("gpu_safety_enabled", True)),
            start_temperature_c=int(values.get("gpu_start_temperature_c", 75)),
            abort_temperature_c=int(values.get("gpu_abort_temperature_c", 82)),
            abort_temperature_sustain_seconds=max(
                0.0,
                float(values.get("gpu_abort_temperature_sustain_seconds", 10.0)),
            ),
            emergency_temperature_c=int(values.get("gpu_emergency_temperature_c", 90)),
            cooldown_initial_wait_seconds=max(
                1.0,
                float(values.get("gpu_cooldown_initial_wait_seconds", 10.0)),
            ),
            cooldown_max_wait_seconds=max(
                0.0,
                float(values.get("gpu_cooldown_max_wait_seconds", 300.0)),
            ),
            resume_temperature_c=int(values.get("gpu_resume_temperature_c", 72)),
            minimum_free_vram_mb=int(values.get("gpu_minimum_free_vram_mb", 6000)),
            runtime_minimum_free_vram_mb=int(values.get("gpu_runtime_minimum_free_vram_mb", 700)),
            maximum_gpu_utilization_percent=int(values.get("gpu_maximum_utilization_percent", 20)),
            maximum_encoder_utilization_percent=int(
                values.get("gpu_maximum_encoder_utilization_percent", 5)
            ),
            poll_seconds=max(0.5, float(values.get("gpu_poll_seconds", 2.0))),
            wait_timeout_seconds=max(1.0, float(values.get("gpu_wait_timeout_seconds", 7200.0))),
            safe_samples_required=max(1, int(values.get("gpu_safe_samples_required", 3))),
        )


@dataclass(frozen=True)
class GpuSnapshot:
    timestamp: str
    name: str
    driver_version: str
    temperature_c: int
    gpu_utilization_percent: int
    encoder_utilization_percent: int
    memory_total_mb: int
    memory_used_mb: int
    memory_free_mb: int


@dataclass(frozen=True)
class GpuTemperatureLimits:
    target_c: int | None = None
    slowdown_c: int | None = None
    shutdown_c: int | None = None


class GpuSafetyGuard:
    def __init__(
        self,
        config: GpuSafetyConfig,
        *,
        snapshot_reader: Callable[[], GpuSnapshot] | None = None,
        log_path: Path | None = None,
        clock: Callable[[], float] | None = None,
        waiter: Callable[[float, Event | None], None] | None = None,
    ) -> None:
        self.config = config
        self._snapshot_reader = snapshot_reader or read_nvidia_snapshot
        self.log_path = log_path or (ensure_dir("logs") / "gpu_safety.jsonl")
        self._clock = clock or time.monotonic
        self._waiter = waiter or _wait_with_cancel
        self._last_runtime_poll = float("-inf")
        self._cooldown_required = False
        self._temperature_above_abort_since: float | None = None

    def wait_until_safe(
        self,
        cancel_event: Event | None,
        status_callback: StatusCallback | None = None,
    ) -> GpuSnapshot | None:
        if not self.config.enabled:
            return None
        started_at = time.monotonic()
        safe_count = 0
        last_message = ""
        while True:
            check_cancel(cancel_event)
            snapshot = self._read_or_raise("preflight")
            reasons = self._preflight_reasons(snapshot)
            if not reasons:
                safe_count += 1
                if safe_count >= self.config.safe_samples_required:
                    self._cooldown_required = False
                    append_gpu_event(self.log_path, "preflight-safe", snapshot=snapshot)
                    return snapshot
                message = (
                    f"GPU đã an toàn, đang xác nhận {safe_count}/{self.config.safe_samples_required}: "
                    f"{snapshot.temperature_c}°C, trống {snapshot.memory_free_mb} MB."
                )
            else:
                safe_count = 0
                message = "Đang chờ GPU an toàn: " + "; ".join(reasons)
            if message != last_message:
                if status_callback is not None:
                    status_callback(message)
                append_gpu_event(self.log_path, "preflight-wait", snapshot=snapshot, message=message)
                last_message = message
            if time.monotonic() - started_at >= self.config.wait_timeout_seconds:
                raise GpuSafetyError(
                    "Đã chờ GPU quá lâu nhưng GPU vẫn nóng hoặc đang bị tác vụ khác sử dụng. "
                    "Hàng đợi đã dừng an toàn; hãy dừng tác vụ GPU khác rồi chạy lại."
                )
            _wait_with_cancel(self.config.poll_seconds, cancel_event)

    def check_runtime(
        self,
        status_callback: StatusCallback | None = None,
        *,
        report_stop: bool = True,
    ) -> GpuSnapshot | None:
        if not self.config.enabled:
            return None
        now = self._clock()
        if now - self._last_runtime_poll < self.config.poll_seconds:
            return None
        self._last_runtime_poll = now
        snapshot = self._read_or_raise("runtime")
        reasons = []
        temperature_reason = self._runtime_temperature_reason(snapshot, now, status_callback)
        if temperature_reason:
            reasons.append(temperature_reason)
        if snapshot.encoder_utilization_percent > self.config.maximum_encoder_utilization_percent:
            reasons.append(
                f"NVENC đang chạy {snapshot.encoder_utilization_percent}% "
                f"(ngưỡng {self.config.maximum_encoder_utilization_percent}%)"
            )
        if snapshot.memory_free_mb < self.config.runtime_minimum_free_vram_mb:
            reasons.append(
                f"VRAM trống chỉ còn {snapshot.memory_free_mb} MB "
                f"(cần {self.config.runtime_minimum_free_vram_mb} MB)"
            )
        if reasons:
            self._cooldown_required = True
            self._temperature_above_abort_since = None
            prefix = "Đã dừng Chatterbox để bảo vệ GPU: " if report_stop else "GPU cần tạm nghỉ: "
            message = prefix + "; ".join(reasons)
            if report_stop and status_callback is not None:
                status_callback(message)
            append_gpu_event(
                self.log_path,
                "runtime-stop" if report_stop else "runtime-cooldown-trigger",
                snapshot=snapshot,
                message=message,
            )
            raise GpuSafetyError(message + ". Các chunk đã hoàn thành được giữ để chạy tiếp.")
        return snapshot

    def check_runtime_with_cooldown(
        self,
        control: WorkerPauseControl,
        cancel_event: Event | None,
        status_callback: StatusCallback | None = None,
    ) -> GpuSnapshot | None:
        try:
            return self.check_runtime(status_callback, report_stop=False)
        except GpuSafetyError as trigger:
            max_wait = self.config.cooldown_max_wait_seconds
            if max_wait <= 0:
                raise GpuSafetyError(
                    f"{trigger} Thời gian chờ phục hồi đang đặt là 0 giây nên worker không thể tự tiếp tục."
                ) from trigger

            control.suspend()
            started_at = self._clock()
            delay = self.config.cooldown_initial_wait_seconds
            last_reasons = [str(trigger)]
            append_gpu_event(
                self.log_path,
                "runtime-cooldown-start",
                message=str(trigger),
                details={"maximum_wait_seconds": max_wait},
            )
            try:
                while True:
                    check_cancel(cancel_event)
                    elapsed = max(0.0, self._clock() - started_at)
                    remaining_budget = max_wait - elapsed
                    if remaining_budget <= 0:
                        detail = "; ".join(last_reasons)
                        message = (
                            f"GPU chưa phục hồi sau {max_wait:.0f} giây chờ. "
                            f"Colin TTS đã dừng an toàn. Trạng thái cuối: {detail}"
                        )
                        append_gpu_event(self.log_path, "runtime-cooldown-timeout", message=message)
                        raise GpuSafetyError(message)

                    wait_seconds = min(delay, remaining_budget)
                    message = (
                        f"Đã tạm dừng worker để GPU nguội; kiểm tra lại sau {wait_seconds:.0f} giây "
                        f"(đã chờ {elapsed:.0f}/{max_wait:.0f} giây)."
                    )
                    if status_callback is not None:
                        status_callback(message)
                    append_gpu_event(
                        self.log_path,
                        "runtime-cooldown-wait",
                        message=message,
                        details={"delay_seconds": wait_seconds, "elapsed_seconds": elapsed},
                    )
                    self._waiter(wait_seconds, cancel_event)
                    check_cancel(cancel_event)

                    snapshot = self._read_or_raise("runtime-cooldown")
                    last_reasons = self._runtime_recovery_reasons(snapshot)
                    if not last_reasons:
                        self._cooldown_required = False
                        self._temperature_above_abort_since = None
                        message = (
                            f"GPU đã phục hồi: {snapshot.temperature_c}°C, "
                            f"VRAM trống {snapshot.memory_free_mb} MB, NVENC "
                            f"{snapshot.encoder_utilization_percent}%. Đang tiếp tục worker."
                        )
                        if status_callback is not None:
                            status_callback(message)
                        append_gpu_event(
                            self.log_path,
                            "runtime-cooldown-resume",
                            snapshot=snapshot,
                            message=message,
                        )
                        return snapshot

                    elapsed = max(0.0, self._clock() - started_at)
                    message = "GPU vẫn chưa an toàn: " + "; ".join(last_reasons)
                    if status_callback is not None:
                        status_callback(message)
                    append_gpu_event(
                        self.log_path,
                        "runtime-cooldown-check",
                        snapshot=snapshot,
                        message=message,
                        details={"elapsed_seconds": elapsed},
                    )
                    delay *= 2.0
            finally:
                control.resume()

    def _runtime_temperature_reason(
        self,
        snapshot: GpuSnapshot,
        now: float,
        status_callback: StatusCallback | None,
    ) -> str:
        temperature = snapshot.temperature_c
        abort_temperature = self.config.abort_temperature_c
        emergency_temperature = self.config.emergency_temperature_c
        if temperature >= emergency_temperature:
            self._temperature_above_abort_since = None
            return (
                f"nhiệt độ nguy cấp {temperature}°C >= {emergency_temperature}°C "
                "(tạm nghỉ ngay, không chờ xác nhận)"
            )
        if temperature < abort_temperature:
            if self._temperature_above_abort_since is not None:
                append_gpu_event(
                    self.log_path,
                    "runtime-temperature-recovered",
                    snapshot=snapshot,
                    message="Nhiệt độ đã hạ; xóa bộ đếm quá nhiệt liên tục.",
                )
            self._temperature_above_abort_since = None
            return ""

        sustain_seconds = self.config.abort_temperature_sustain_seconds
        if self._temperature_above_abort_since is None:
            self._temperature_above_abort_since = now
        elapsed = max(0.0, now - self._temperature_above_abort_since)
        if elapsed >= sustain_seconds:
            return (
                f"nhiệt độ {temperature}°C >= {abort_temperature}°C liên tục "
                f"{elapsed:.1f}/{sustain_seconds:.1f} giây"
            )

        remaining = max(0.0, sustain_seconds - elapsed)
        message = (
            f"GPU đang nóng {temperature}°C >= {abort_temperature}°C; "
            f"chỉ tạm nghỉ nếu giữ liên tục thêm {remaining:.1f} giây."
        )
        if status_callback is not None:
            status_callback(message)
        append_gpu_event(
            self.log_path,
            "runtime-temperature-grace",
            snapshot=snapshot,
            message=message,
            details={"elapsed_seconds": elapsed, "required_seconds": sustain_seconds},
        )
        return ""

    def _runtime_recovery_reasons(self, snapshot: GpuSnapshot) -> list[str]:
        reasons = []
        if snapshot.temperature_c > self.config.resume_temperature_c:
            reasons.append(
                f"nhiệt độ {snapshot.temperature_c}°C > mức chạy lại "
                f"{self.config.resume_temperature_c}°C"
            )
        if snapshot.memory_free_mb < self.config.runtime_minimum_free_vram_mb:
            reasons.append(
                f"VRAM trống {snapshot.memory_free_mb} MB < "
                f"{self.config.runtime_minimum_free_vram_mb} MB"
            )
        if snapshot.encoder_utilization_percent > self.config.maximum_encoder_utilization_percent:
            reasons.append(
                f"NVENC {snapshot.encoder_utilization_percent}% > "
                f"{self.config.maximum_encoder_utilization_percent}%"
            )
        return reasons

    def record_worker_failure(self, message: str) -> None:
        self._cooldown_required = True
        snapshot = None
        try:
            snapshot = self._snapshot_reader()
        except Exception:
            pass
        append_gpu_event(self.log_path, "worker-failure", snapshot=snapshot, message=message)

    def _read_or_raise(self, phase: str) -> GpuSnapshot:
        try:
            return self._snapshot_reader()
        except Exception as exc:
            append_gpu_event(self.log_path, "snapshot-error", message=f"{phase}: {exc}")
            raise GpuSafetyError(
                "Không đọc được trạng thái NVIDIA/CUDA. Hàng đợi đã dừng để tránh làm màn hình mất tín hiệu. "
                f"Chi tiết: {exc}"
            ) from exc

    def _preflight_reasons(self, snapshot: GpuSnapshot) -> list[str]:
        reasons = []
        temperature_limit = (
            self.config.resume_temperature_c
            if self._cooldown_required
            else self.config.start_temperature_c
        )
        if snapshot.temperature_c > temperature_limit:
            reasons.append(f"{snapshot.temperature_c}°C > {temperature_limit}°C")
        if snapshot.memory_free_mb < self.config.minimum_free_vram_mb:
            reasons.append(
                f"VRAM trống {snapshot.memory_free_mb} MB < {self.config.minimum_free_vram_mb} MB"
            )
        if snapshot.gpu_utilization_percent > self.config.maximum_gpu_utilization_percent:
            reasons.append(
                f"GPU đang dùng {snapshot.gpu_utilization_percent}% > "
                f"{self.config.maximum_gpu_utilization_percent}%"
            )
        if snapshot.encoder_utilization_percent > self.config.maximum_encoder_utilization_percent:
            reasons.append(
                f"NVENC đang dùng {snapshot.encoder_utilization_percent}% > "
                f"{self.config.maximum_encoder_utilization_percent}%"
            )
        return reasons


def read_nvidia_snapshot() -> GpuSnapshot:
    fields = (
        "name,driver_version,temperature.gpu,utilization.gpu,utilization.encoder,"
        "memory.total,memory.used,memory.free"
    )
    completed = subprocess.run(
        [
            "nvidia-smi",
            f"--query-gpu={fields}",
            "--format=csv,noheader,nounits",
        ],
        capture_output=True,
        text=True,
        timeout=8,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "nvidia-smi thất bại").strip()
        raise RuntimeError(detail)
    line = next((item.strip() for item in completed.stdout.splitlines() if item.strip()), "")
    values = [item.strip() for item in line.split(",")]
    if len(values) != 8:
        raise RuntimeError(f"nvidia-smi trả về dữ liệu không hợp lệ: {line}")
    return GpuSnapshot(
        timestamp=datetime.now().isoformat(timespec="seconds"),
        name=values[0],
        driver_version=values[1],
        temperature_c=_integer(values[2]),
        gpu_utilization_percent=_integer(values[3]),
        encoder_utilization_percent=_integer(values[4]),
        memory_total_mb=_integer(values[5]),
        memory_used_mb=_integer(values[6]),
        memory_free_mb=_integer(values[7]),
    )


def read_nvidia_temperature_limits() -> GpuTemperatureLimits:
    completed = subprocess.run(
        ["nvidia-smi", "-q", "-d", "TEMPERATURE"],
        capture_output=True,
        text=True,
        timeout=8,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "nvidia-smi thất bại").strip()
        raise RuntimeError(detail)
    return parse_nvidia_temperature_limits(completed.stdout)


def parse_nvidia_temperature_limits(output: str) -> GpuTemperatureLimits:
    def value_for(label: str) -> int | None:
        match = re.search(rf"^\s*{re.escape(label)}\s*:\s*(\d+)\s*C\s*$", output, re.MULTILINE)
        return int(match.group(1)) if match else None

    return GpuTemperatureLimits(
        target_c=value_for("GPU Target Temperature"),
        slowdown_c=value_for("GPU Slowdown Temp"),
        shutdown_c=value_for("GPU Shutdown Temp"),
    )


def gpu_temperature_guidance() -> str:
    try:
        snapshot = read_nvidia_snapshot()
        limits = read_nvidia_temperature_limits()
    except Exception:
        return "Khuyến nghị chung: bắt đầu dưới 75°C, dừng ở 82°C; không dùng giới hạn phần cứng làm ngưỡng chạy liên tục."
    published_max = 91 if "GTX 1080 Ti" in snapshot.name else None
    parts = [snapshot.name]
    if published_max is not None:
        parts.append(f"max NVIDIA {published_max}°C")
    if limits.target_c is not None:
        parts.append(f"target {limits.target_c}°C")
    if limits.slowdown_c is not None:
        parts.append(f"giảm xung {limits.slowdown_c}°C")
    if limits.shutdown_c is not None:
        parts.append(f"tự tắt {limits.shutdown_c}°C")
    return " · ".join(parts) + ". Nên giữ ngưỡng dừng ở 82°C."


_LOG_LOCK = Lock()


def append_gpu_event(
    path: Path,
    event: str,
    *,
    snapshot: GpuSnapshot | None = None,
    message: str = "",
    details: dict | None = None,
) -> None:
    payload = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "event": event,
        "message": message,
        "gpu": asdict(snapshot) if snapshot is not None else None,
        "details": details or {},
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with _LOG_LOCK:
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def is_fatal_cuda_error(message: str) -> bool:
    normalized = message.casefold()
    fatal_markers = (
        "cufft_internal_error",
        "cufft error",
        "torch.cuda",
        "cuda driver",
        "cuda initialization",
        "cuda error: unknown error",
        "device-side assert",
        "device is unavailable",
        "device unavailable",
        "device has been lost",
        "unspecified launch failure",
    )
    return any(marker in normalized for marker in fatal_markers)


def _integer(value: str) -> int:
    try:
        return int(float(value))
    except ValueError as exc:
        raise RuntimeError(f"Không đọc được giá trị GPU: {value}") from exc


def _wait_with_cancel(seconds: float, cancel_event: Event | None) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        check_cancel(cancel_event)
        remaining = deadline - time.monotonic()
        time.sleep(min(0.25, max(0.0, remaining)))
