from datetime import datetime, timezone
from threading import Barrier, Lock
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pytest
import soundfile as sf

from colin_remote_compute import local_cpu, pc_pool
from colin_remote_compute.broker.models import RemoteTtsRequest, WorkerModelCapability, WorkerProfile
from colin_remote_compute.broker.profiles import WorkerProfileStore
from colin_remote_compute.client import ColabClient
from colin_remote_compute.context import ManagedExecution
from colin_remote_compute.inference_units import InferenceUnit, execute_units
from colin_remote_compute.local_cpu import LOCAL_CPU_ID, LocalCpuExecutor, _folder_revision
from colin_remote_compute.pc_pool import CpuPoolLifecycle
from colin_remote_compute.store import ColabStore
from omni_tts_core.ui_presenters.settings_state import GenerationSettings
from omni_tts_shared.errors import GenerationError
from omni_tts_shared.schemas import RemoteComputeTarget


@pytest.mark.parametrize("model_id,provider,rate", [
    ("zerotts_202m_official", "zerotts", 48000), ("piper_ngoc_huyen", "piper", 22050),
    ("vieneu_v3_turbo", "vieneu", 48000),
])
def test_local_and_remote_take_work_concurrently_and_keep_source_order(tmp_path, monkeypatch, model_id, provider, rate):
    profiles = WorkerProfileStore(tmp_path / "profiles.json")
    profile = WorkerProfile(profile_id="pc-remote", worker_id="pc-remote", label="Remote PC", broker_url="http://127.0.0.1:1")
    profiles.upsert(profile)
    profiles.set_cpu_pool_local(True)
    monkeypatch.setattr(pc_pool, "profile_store", lambda: profiles)
    cap = WorkerModelCapability(model_id=model_id, provider_id=provider, execution_backend="cpu", revision="same",
                                sample_rate=rate, supports_batch=True, supports_segments=True)
    monkeypatch.setattr(pc_pool, "LocalCpuExecutor", lambda _: SimpleNamespace(capability=cap, close=Mock()))
    broker = SimpleNamespace(
        list_pc_devices=lambda: [{"worker_id": profile.worker_id, "desired_state": "running", "observed_state": "idle",
                                  "last_seen_at": datetime.now(timezone.utc).isoformat()}],
        list_workers=lambda: [SimpleNamespace(capabilities=SimpleNamespace(
            worker_id=profile.worker_id, worker_type="remote_pc", models=[cap]))],
    )
    monkeypatch.setattr(pc_pool, "broker_for", lambda _: broker)
    store = ColabStore(tmp_path / "queue")
    job = store.create("text", {"remote_target": {"kind": "cpu_pool"}})
    lifecycle = CpuPoolLifecycle(store, job["job_id"], [profile], 2, include_local=True)
    started, mutex, barrier = [], Lock(), Barrier(2, timeout=5)

    def execute(_context, machine, unit, _digest, _rate):
        assert unit.request.model_revision == "same" and _rate == rate
        with mutex:
            started.append(machine.profile_id)
            first_two = len(started) <= 2
        if first_two:
            barrier.wait()
        unit.destination.write_text(unit.request.text)

    monkeypatch.setattr(lifecycle, "_run_unit", execute)
    context = ManagedExecution(store, job["job_id"], lifecycle)
    units = [InferenceUnit(RemoteTtsRequest(client_job_id="source", inference_unit_id=str(i), idempotency_key=str(i),
                                           model_id=model_id, text=f"source {i}"), tmp_path / f"{i}.wav") for i in range(4)]
    assert [unit.destination.read_text() for unit in execute_units(context, units)] == [f"source {i}" for i in range(4)]
    assert set(started[:2]) == {LOCAL_CPU_ID, profile.profile_id}
    assert lifecycle.local.close.call_count > 0
    events = store.events(job["job_id"])
    assert len([event for event in events if "hoàn tất đoạn" in event["message"]]) == 4
    assert not any("source " in event["message"] for event in events)
    profiles.set_cpu_pool_local(False)
    assert not lifecycle._allowed(lifecycle.local_profile)


def test_revision_mismatch_cannot_mix_local_with_remote(tmp_path, monkeypatch):
    store = ColabStore(tmp_path / "queue")
    job = store.create("text", {})
    lifecycle = CpuPoolLifecycle(store, job["job_id"], [], 4, include_local=True)
    lifecycle.local = SimpleNamespace(close=Mock())
    other = SimpleNamespace(profile_id="pc-other", label="Other PC")
    monkeypatch.setattr(lifecycle, "_groups", lambda _: {("local", 48000): [lifecycle.local_profile],
                                                       ("remote", 48000): [other, other]})
    chosen = []
    monkeypatch.setattr(lifecycle, "_distribute", lambda _context, _pending, available, *a, **kw: chosen.extend(available))
    unit = InferenceUnit(RemoteTtsRequest(client_job_id="one", inference_unit_id="1", idempotency_key="1",
                                        model_id="zerotts_202m_official", text="private text"), tmp_path / "out.wav")
    lifecycle.dispatch(ManagedExecution(store, job["job_id"], lifecycle), [unit])
    assert lifecycle.local_profile not in chosen
    assert any("không cùng phiên bản" in item["message"] for item in store.events(job["job_id"]))


def test_local_output_is_verified_and_resume_does_not_synthesize_again(tmp_path, monkeypatch):
    executor = object.__new__(LocalCpuExecutor)
    executor.spec = SimpleNamespace(provider="zerotts", runtime={})
    executor.root, executor.worker_name = tmp_path, "zerotts_worker"
    executor.capability = WorkerModelCapability(model_id="zerotts_202m_official", provider_id="zerotts",
                                               execution_backend="cpu", sample_rate=48000, revision="same")
    executor.worker = Mock()

    def synthesize(payload, **_kwargs):
        assert payload["options"] == {"seed": 123}
        sf.write(payload["chunks"][0]["output_path"], np.ones(2400, dtype="float32") * .01, 48000)

    executor.worker.run.side_effect = synthesize
    store = ColabStore(tmp_path / "queue")
    job = store.create("text", {})
    lifecycle = SimpleNamespace(document=None, expired=lambda: False, is_existing_worker=True)
    context = ManagedExecution(store, job["job_id"], lifecycle)
    request = RemoteTtsRequest(client_job_id="one", inference_unit_id="1", idempotency_key="1",
                               model_id="zerotts_202m_official", model_revision="same", text="Xin chào", provider_options={"seed":123})
    destination = tmp_path / "result.wav"
    unit = InferenceUnit(request, destination)
    executor.execute(context, unit, "digest", 48000)
    assert sf.info(destination).samplerate == 48000
    assert store.state(job["job_id"] + ":verified_units") == 1
    destination.unlink()
    executor.execute(context, unit, "digest", 48000)
    assert executor.worker.run.call_count == 1
    assert destination.is_file()


def test_unverified_folder_revision_is_rejected(tmp_path):
    (tmp_path / "model.onnx").write_bytes(b"model")
    with pytest.raises(GenerationError, match="phiên bản"):
        _folder_revision(tmp_path, ["model.onnx"])


def test_fast_machine_events_are_all_delivered_even_between_two_polls(tmp_path):
    client = ColabClient(tmp_path)
    job = client.store.create("text", {})
    messages = [f"Máy {i % 3} · hoàn tất đoạn {i}" for i in range(225)]
    for message in messages:
        client.store.add_event(job["job_id"], message)
    client.store.complete(job["job_id"], {"ok": True})
    events = []
    client.wait(job["job_id"], progress_callback=events.append)
    assert [event.message for event in events[:225]] == messages


def test_mcp_and_settings_preserve_explicit_local_opt_in():
    from colin_studio_tts_mcp.contracts import TextGenerationInput
    target = {"kind": "cpu_pool", "include_local": True}
    request = TextGenerationInput(text="Xin chào", model_id="zerotts_202m_official",
                                  generation={"runtime_target": "remote", "remote_compute": target})
    settings = request.to_settings()
    assert settings.remote_include_local
    restored = GenerationSettings.from_snapshot(settings.to_snapshot())
    assert restored.to_request("Xin chào").remote_compute.include_local
    with pytest.raises(ValueError):
        RemoteComputeTarget(kind="existing_worker", include_local=True)


def test_cpu_pool_selection_saves_checkboxes_without_changing_remote_only_choice(tmp_path, monkeypatch):
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    from colin_colab_remote.ui.remote_compute_section import RemoteComputeGroup
    from omni_tts_core.runtime_devices import CPU_POOL_CHOICE, REMOTE_CPU_CHOICE
    app = QApplication.instance() or QApplication([])
    group = RemoteComputeGroup()
    group.store = WorkerProfileStore(tmp_path / "profiles.json")
    group.reload()
    group.set_runtime_choice(CPU_POOL_CHOICE, allow_colab=True)
    group.local_cpu.setChecked(True)
    assert group.include_local and group.store.load().cpu_pool_local
    assert not group.manage_cpu_button.isHidden()
    group.set_runtime_choice(REMOTE_CPU_CHOICE, allow_colab=True)
    assert not group.include_local
    assert group.store.load().cpu_pool_local
    group.close()
    app.processEvents()


def test_resident_worker_drains_stderr_during_long_use(tmp_path, monkeypatch):
    import sys
    from pathlib import Path
    from omni_tts_core.engines import preset_onnx_engine
    script = tmp_path / "synthesize.py"
    script.write_text("import sys\nfor line in sys.stdin:\n sys.stderr.write('x' * 100000)\n sys.stderr.flush()\n print('{\"ok\": true}', flush=True)\n")
    monkeypatch.setattr(preset_onnx_engine, "worker_venv_python", lambda _: Path(sys.executable))
    worker = preset_onnx_engine._JsonLineWorker("fake", "CPU test")
    worker.worker_script, worker.worker_dir = script, tmp_path
    try:
        worker.run({}, timeout=5, cancel_event=None, tick_callback=lambda: None)
        worker.run({}, timeout=5, cancel_event=None, tick_callback=lambda: None)
    finally:
        worker.close()


def test_settings_panel_restores_pool_and_local_choice_without_changing_machine_policy(tmp_path, monkeypatch):
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    from omni_tts_core.app_controller import AppController
    from omni_tts_core.runtime_devices import CPU_POOL_CHOICE
    from omni_tts_ui_qt.context import AppContext
    from omni_tts_ui_qt.pages.settings_panel import SettingsPanel
    from omni_tts_ui_qt.preferences import QtPreferences
    app = QApplication.instance() or QApplication([])
    panel = SettingsPanel(AppContext(controller=AppController(), probe=Mock(), safety_gate=Mock(),
        preferences=QtPreferences(path=tmp_path / "prefs.json"), log=Mock(),
        set_worker_status=Mock(), show_page=Mock(), register_settings_provider=Mock()))
    store = WorkerProfileStore(tmp_path / "profiles.json")
    panel.remote_compute_group.store = store
    try:
        panel._select_model("zerotts_202m_official")
        panel.device_combo.setCurrentIndex(panel.device_combo.findData(CPU_POOL_CHOICE))
        panel.remote_compute_group.local_cpu.setChecked(True)
        assert panel.current_settings().remote_include_local
        data = panel.current_settings().to_preferences()
        data["remote_include_local"] = False
        panel.load_preferences(data)
        assert panel.device_combo.currentData() == CPU_POOL_CHOICE
        assert not panel.current_settings().remote_include_local
        assert store.load().cpu_pool_local  # History restore cannot stop other jobs.
    finally:
        panel.close()
        app.processEvents()
