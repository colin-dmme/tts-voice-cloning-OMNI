from threading import Barrier, Lock
from types import SimpleNamespace

from colin_remote_compute.broker.models import RemoteTtsRequest, WorkerProfile
from colin_remote_compute.context import ManagedExecution
from colin_remote_compute.inference_units import InferenceUnit, execute_units
from colin_remote_compute.pc_lifecycle import PcWorkerUnavailable
from colin_remote_compute.pc_pool import CpuPoolLifecycle
from colin_remote_compute.store import ColabStore
from omni_tts_core.service import _chunks_for_provider


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
