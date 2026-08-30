from __future__ import annotations

from pathlib import Path

from omni_tts_core.model_catalog import generate_catalog_html
from omni_tts_core.model_registry import ModelRegistry
from omni_tts_core.runtime_status import RuntimeStatusService
from omni_tts_core.worker_installation import (
    base_installer_for_spec,
    gpu_installer_for_spec,
    worker_for_spec,
    worker_label_for_spec,
)


def test_vieneu_v3_catalog_matches_sdk_330_snapshot() -> None:
    spec = ModelRegistry().get("vieneu_v3_turbo")

    assert spec.display_name == "VieNeu v3 Turbo 3.3 · 48 kHz"
    assert worker_for_spec(spec) == "vieneu_v3_worker"
    assert worker_label_for_spec(spec) == "VieNeu v3"
    assert spec.default_voice_preset == "Adam"
    assert len(spec.voice_presets) == 20
    assert {"Ngọc Huyền", "Mỹ Duyên", "Quỳnh Anh", "Đức Trí", "Kim Thanh", "Adam"} <= set(
        spec.voice_presets
    )


def test_vieneu_v2_keeps_the_existing_worker_with_clear_label() -> None:
    spec = ModelRegistry().get("vieneu_v2_standard")

    assert worker_for_spec(spec) == "vieneu_worker"
    assert worker_label_for_spec(spec) == "VieNeu v2"


def test_vieneu_v3_has_dedicated_windows_installers() -> None:
    spec = ModelRegistry().get("vieneu_v3_turbo")

    assert base_installer_for_spec(spec).name == "install_vieneu_v3_worker.bat"
    assert gpu_installer_for_spec(spec).name == "install_vieneu_v3_worker_cuda.bat"


def test_vieneu_v3_runtime_status_names_actual_cpu_backend() -> None:
    spec = ModelRegistry().get("vieneu_v3_turbo")
    worker_python = Path("engines/vieneu_v3_worker/.venv/Scripts/python.exe")
    if not worker_python.exists():
        return

    status = RuntimeStatusService().status_for(spec.model_id)
    assert status.actual_device == "cpu"
    assert "SDK 3.3.0" in status.message
    assert "CPU ONNX INT8" in status.message
    assert "CPU / ONNX Runtime" in status.device_name


def test_catalog_distinguishes_vieneu_v3_from_vieneu_v2() -> None:
    html = generate_catalog_html()

    assert "vieneu_v3_turbo · VieNeu v3" in html
    assert "vieneu_v2_standard · VieNeu v2" in html
    assert "CPU ONNX INT8 mặc định · GPU PyTorch tùy chọn" in html
