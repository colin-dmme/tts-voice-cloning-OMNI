from threading import Barrier, Lock
from types import SimpleNamespace
from datetime import datetime, timezone
import hashlib

from colin_remote_compute.broker.models import RemoteTtsRequest, WorkerProfile
from colin_remote_compute.context import ManagedExecution
from colin_remote_compute.inference_units import InferenceUnit, execute_units
from colin_remote_compute.pc_lifecycle import PcWorkerUnavailable
from colin_remote_compute.pc_pool import CpuPoolLifecycle
from colin_remote_compute.piper_model_sync import InstalledPiperPackage
import colin_remote_compute.pc_pool as pool_module
from colin_remote_compute.store import ColabStore
from omni_tts_core.service import _chunks_for_provider
from omni_tts_shared.errors import GenerationError
import pytest


def test_pool_sync_uses_selected_machines_and_includes_verified_worker(tmp_path, monkeypatch):
    from colin_remote_compute.broker.models import WorkerModelCapability

    model_id = "piper_manual_voice"
    manifest = {"model_id": model_id, "label": "Piper thử nghiệm", "sample_rate": 22050,
                "onnx": {"sha256": "a" * 64, "size": 7}, "config": {"sha256": "b" * 64, "size": 8}}
    package = InstalledPiperPackage(manifest, {})
    monkeypatch.setattr(InstalledPiperPackage, "find", lambda _model: package)
    profiles = [WorkerProfile(profile_id=f"pc-test-{index}", worker_id=f"pc-test-{index}", label=f"Test {index}",
                              broker_url="http://127.0.0.1:1") for index in range(2)]
    store = ColabStore(tmp_path / "queue")
    job = store.create("text", {"remote_target": {"kind": "cpu_pool"}})
    lifecycle = CpuPoolLifecycle(store, job["job_id"], profiles, 2)
    monkeypatch.setattr(lifecycle, "_allowed", lambda profile: profile == profiles[0])
    model = WorkerModelCapability(model_id=model_id, provider_id="piper", execution_backend="cpu",
                                  revision=package.signature[0], sample_rate=22050, supports_segments=True)
    assigned = []

    def assign(sent, ids):
        assert sent == manifest
        assigned.extend(ids)
        return ids

    def devices():
        return [{"worker_id": profile.worker_id, "desired_state": "running", "observed_state": "idle",
                 "last_seen_at": datetime.now(timezone.utc).isoformat(), "worker_version": "1.1.0"}
                for profile in profiles]

    lifecycle.broker = SimpleNamespace(
        list_pc_devices=devices,
        list_workers=lambda: [SimpleNamespace(capabilities=SimpleNamespace(
            worker_id=assigned[0], worker_type="remote_pc", models=[model]))] if assigned else [],
        health=lambda: {"pc_model_sync": "1"},
        ensure_piper_package=lambda _manifest, _files, check: check(),
        assign_piper_model=assign,
    )
    ticks = [0.0]
    monkeypatch.setattr(pool_module, "time", SimpleNamespace(
        monotonic=lambda: ticks[0], sleep=lambda _seconds: ticks.__setitem__(0, ticks[0] + 1),
    ))

    def execute(context, profile, unit, digest, _rate):
        assert profile == profiles[0]
        data = b"test result"
        _, cache, proof = context.cache_paths(unit.request, unit.destination, is_pc=True)
        cache.write_bytes(data)
        proof.write_text(hashlib.sha256(data).hexdigest())
        unit.destination.write_bytes(data)
        store.record_cpu_result(job["job_id"], digest, profile.worker_id, 1)
        return profile.worker_id

    monkeypatch.setattr(lifecycle, "_run_unit", execute)
    context = ManagedExecution(store, job["job_id"], lifecycle)
    units = [InferenceUnit(RemoteTtsRequest(client_job_id="source", inference_unit_id=str(i), idempotency_key=str(i),
                                           model_id=model_id, text="Không ghi nội dung này"), tmp_path / f"{i}.wav")
             for i in range(2)]
    lifecycle.dispatch(context, units)
    lifecycle.dispatch(context, units)
    assert assigned == [profiles[0].worker_id]
    assert store.cpu_contributions(job["job_id"]) == [{"worker_id": profiles[0].worker_id, "segments": 2}]
    events = store.events(job["job_id"])
    assert {row["level"] for row in events} >= {"dispatch", "success", "sync"}
    assert all("Không ghi nội dung" not in row["message"] and "Test 1" not in row["message"] for row in events)


def test_pool_splits_paragraphs_for_providers_with_native_chunk_boundaries():
    text = "Hôm nay cả nhóm đi từ sớm. Đến buổi trưa chúng tôi dừng lại bên hồ."
    for provider in ("zerotts", "vieneu"):
        assert len(_chunks_for_provider(text, "vi", 35, provider=provider)) == 1
        assert len(_chunks_for_provider(text, "vi", 35, provider=provider, force_split=True)) > 1


def test_pool_uses_two_slots_and_reassigns_without_reordering(tmp_path, monkeypatch):
    store = ColabStore(tmp_path / "queue")
    profiles = [WorkerProfile(profile_id=f"pc-test-{index}", worker_id=f"pc-test-{index}", label=str(index),
                              broker_url="http://127.0.0.1:18958") for index in range(3)]
    job = store.create("text", {"remote_target": {"kind": "cpu_pool"}})
    lifecycle = CpuPoolLifecycle(store, job["job_id"], profiles, 2)
    context = ManagedExecution(store, job["job_id"], lifecycle)
    group = ("cpu-revision", 48000)
    monkeypatch.setattr(lifecycle, "_groups", lambda _units: {group: profiles[:2], ("other", 48000): profiles[2:]})
    monkeypatch.setattr(lifecycle, "_allowed", lambda profile: profile in profiles[:2])
    started, lock, barrier = [], Lock(), Barrier(2, timeout=4)

    def execute(_context, profile, unit, _digest, rate):
        assert rate == 48000 and unit.request.model_revision == "cpu-revision"
        with lock:
            started.append((profile.label, unit.request.text))
            first_two = len(started) <= 2
        if first_two:
            barrier.wait()
        if profile == profiles[0]:
            raise PcWorkerUnavailable("lease expired")
        unit.destination.write_text(unit.request.text, encoding="utf-8")

    monkeypatch.setattr(lifecycle, "_run_unit", execute)
    units = [InferenceUnit(RemoteTtsRequest(client_job_id="source", inference_unit_id=str(index),
                                           idempotency_key=f"key-{index}", model_id="zerotts_202m_official",
                                           text=f"unit {index}"), tmp_path / f"{index}.wav") for index in range(4)]
    assert job["job_id"].startswith("cpu-job-")
    assert [item.destination.read_text(encoding="utf-8") for item in execute_units(context, units)] == [
        item.request.text for item in units
    ]
    assert len(started) == 5 and {name for name, _text in started} == {"0", "1"}


def test_pool_cancel_reconciles_every_outstanding_unit(tmp_path):
    store = ColabStore(tmp_path)
    profile = WorkerProfile(profile_id="pc-test", worker_id="pc-test", label="Test", broker_url="http://127.0.0.1:1")
    job = store.create("text", {"remote_target": {"kind": "cpu_pool"}})
    lifecycle = CpuPoolLifecycle(store, job["job_id"], [profile], 2)
    keys = [job["job_id"] + ":pc-pending:" + str(index) for index in range(2)]
    for index, key in enumerate(keys):
        store.set_state(key, f"remote-{index}")
    cancelled = []

    def cancel(remote):
        cancelled.append(remote)
        return SimpleNamespace(status="cancelled")

    lifecycle.broker = SimpleNamespace(
        get_job_by_idempotency=lambda remote: SimpleNamespace(job_id=remote, status="running"), cancel=cancel,
    )
    store.control(job["job_id"], "cancel")
    assert store.wait_or_retry(job["job_id"], "cancel", "cancel")["status"] == "cancelling"
    lifecycle.cancel_pending()
    assert sorted(cancelled) == ["remote-0", "remote-1"]
    assert not lifecycle.has_pending()


@pytest.mark.parametrize("recover", [True, False])
def test_pool_retries_after_all_machines_temporarily_fail(tmp_path, monkeypatch, recover):
    store = ColabStore(tmp_path / "queue")
    profiles = [WorkerProfile(profile_id=f"pc-retry-{i}", worker_id=f"pc-retry-{i}", label=str(i),
                              broker_url="http://127.0.0.1:18958") for i in range(2)]
    job = store.create("text", {"remote_target": {"kind": "cpu_pool"}})
    lifecycle = CpuPoolLifecycle(store, job["job_id"], profiles, 2)
    context = ManagedExecution(store, job["job_id"], lifecycle)
    monkeypatch.setattr(lifecycle, "_groups", lambda _: {("r1", 48000): profiles})
    monkeypatch.setattr(lifecycle, "_allowed", lambda _: True)
    ticks, attempts, mutex = [0.0], {}, Lock()
    monkeypatch.setattr(pool_module, "time", SimpleNamespace(
        monotonic=lambda: ticks[0], sleep=lambda seconds: ticks.__setitem__(0, ticks[0] + seconds),
    ))

    def process(_context, profile, unit, _digest, _rate):
        with mutex:
            attempt = attempts[profile.profile_id] = attempts.get(profile.profile_id, 0) + 1
        if not recover or attempt == 1:
            raise PcWorkerUnavailable("temporary upload failure")
        unit.destination.write_text(unit.request.text, encoding="utf-8")

    monkeypatch.setattr(lifecycle, "_run_unit", process)
    units = [InferenceUnit(RemoteTtsRequest(
        client_job_id="retry-source", inference_unit_id=str(i), idempotency_key=f"retry-{i}",
        model_id="zerotts_202m_official", text=f"unit {i}",
    ), tmp_path / f"{i}.wav") for i in range(2)]
    if recover:
        list(execute_units(context, units))
        assert [unit.destination.read_text(encoding="utf-8") for unit in units] == ["unit 0", "unit 1"]
    else:
        with pytest.raises(GenerationError, match="Nhóm CPU"):
            list(execute_units(context, units))
        assert set(attempts.values()) == {3}
