from colin_remote_compute import client as client_module
from colin_remote_compute.client import ColabClient


def test_queued_job_reports_the_work_ahead_and_keeps_reporting(tmp_path, monkeypatch):
    client = ColabClient(tmp_path)
    payload = {"remote_target": {"kind": "cpu_pool"}}
    first = client.store.create("text", payload)
    client.store.next_job()
    client.store.update(first["job_id"], message="Nhóm CPU · 28/219 đoạn đã xác minh · 2 máy")
    # Paused jobs do not block the scheduler.
    paused = client.store.create("text", payload)
    client.store.control(paused["job_id"], "pause")
    second = client.store.create("text", payload)
    current = client.store.create("text", payload)
    events, clock = [], [0.0]

    def advance(_seconds):
        clock[0] += 15
        if clock[0] >= 45:
            client.store.complete(current["job_id"], {"ok": True})

    monkeypatch.setattr(client_module.time, "sleep", advance)
    monkeypatch.setattr(client_module.time, "monotonic", lambda: clock[0])
    assert client.wait(current["job_id"], progress_callback=events.append) == {"ok": True}
    assert all(event.message.strip() for event in events)
    assert "2 tác vụ phía trước" in events[0].message
    assert "28/219" in events[0].message
    assert "30 giây" in events[1].message
    assert events[0].percent == 0  # The work ahead is not this job's progress.
    assert events[-1].percent == 100
    assert client.store.get(first["job_id"])["status"] == "running"
    assert client.store.get(second["job_id"])["status"] == "queued"


def test_wait_reports_cancellation_without_blank_or_repeated_progress(tmp_path, monkeypatch):
    from omni_tts_shared.errors import GenerationCancelled
    import pytest

    client = ColabClient(tmp_path)
    job = client.store.create("text", {})
    events, ticks = [], [0]

    def advance(_seconds):
        ticks[0] += 1
        if ticks[0] == 1:
            client.store.control(job["job_id"], "cancel")
        elif ticks[0] == 2:
            client.store.update(job["job_id"], message="")  # No visible change.
        else:
            client.store.update(job["job_id"], status="cancelled", message="Đã hủy")

    monkeypatch.setattr(client_module.time, "sleep", advance)
    with pytest.raises(GenerationCancelled):
        client.wait(job["job_id"], progress_callback=events.append)
    assert all(event.message.strip() for event in events)
    assert "Đang hủy" in events[1].message
    assert len(events) == 3


def test_running_legacy_record_has_a_nonempty_start_message(tmp_path):
    client = ColabClient(tmp_path)
    job = client.store.create("text", {})
    client.store.next_job()
    events = []

    def on_progress(event):
        events.append(event)
        client.store.complete(job["job_id"], {"ok": True})

    client.wait(job["job_id"], progress_callback=on_progress)
    assert events[0].message.strip()


def test_waiting_job_reports_recovery_metadata_and_work_folder(tmp_path):
    import pytest
    from omni_tts_shared.errors import GenerationError
    client = ColabClient(tmp_path)
    job = client.store.create("text", {})
    client.store.set_state(job["job_id"] + ":verified_units", 219)
    client.store.wait_or_retry(job["job_id"], "Select music theme", "retry_required")
    events = []
    with pytest.raises(GenerationError, match="Select music"):
        client.wait(job["job_id"], progress_callback=events.append)
    assert events[-1].managed_job_id == job["job_id"]
    assert events[-1].verified_units == 219
    assert events[-1].status == "waiting"
    assert client.work_dir(job["job_id"]).is_dir()
