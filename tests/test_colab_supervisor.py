from __future__ import annotations

import wave
from pathlib import Path
from threading import Event
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from colin_colab_remote import client, context
from colin_colab_remote.broker.profiles import WorkerProfileDocument
from colin_colab_remote.client import ColabClient, jsonable
from colin_colab_remote.daemon import ColabSupervisor, output_proof, proof_valid, restore_settings
from colin_colab_remote.settings import ColabSettings, SettingsStore
from colin_studio_tts_mcp.contracts import TextGenerationInput
from colin_studio_tts_mcp.job_manager import McpJobManager
from colin_studio_tts_mcp.job_store import McpJobStore
from omni_tts_core.app_controller import (
    AppController,
    FileGenerationEvent,
    FileGenerationOutcome,
    FileGenerationTask,
)
from omni_tts_core.file_queue import FileQueueStatus
from omni_tts_core.progress import ProgressEvent
from omni_tts_core.ui_presenters.settings_state import GenerationSettings
from omni_tts_shared.errors import GenerationCancelled, GenerationError
from omni_tts_shared.schemas import GenerateSpeechResult


def result_in(directory):
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "voice.wav"
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(48000)
        output.writeframes(b"\x01\x00" * 480)
    return GenerateSpeechResult(job_id="core-test-job", audio_path=path, job_dir=directory,
                                segment_count=1, duration_seconds=0.01, message="Complete")


class FakeLifecycle:
    def __init__(self):
        self.settings = ColabSettings(enabled=True)
        self.document = WorkerProfileDocument()
        self.releases = 0
        self.fail_release = False

    def expired(self):
        return False

    def release(self):
        self.releases += 1
        if self.fail_release:
            raise GenerationError("Fake cleanup failed")


class FakeController:
    def __init__(self, directory):
        self.directory = directory
        self.calls = []
        self.failure = None
        self.result = result_in(directory)

    def generate_text(self, text, settings, progress_callback=None, cancel_event=None):
        assert context.managed_execution() is not None
        assert not client.should_manage(settings)
        assert cancel_event is not None and not cancel_event.is_set()
        self.calls.append((text, settings))
        if self.failure:
            raise self.failure
        if progress_callback:
            progress_callback(ProgressEvent("Generated", 1, 1))
        return self.result

    def generate_files(self, tasks, settings, progress_callback=None, cancel_event=None, file_event_callback=None):
        assert context.managed_execution() is not None
        assert not client.should_manage(settings)
        assert cancel_event is not None and not cancel_event.is_set()
        self.calls.append((tasks, settings))
        if self.failure:
            raise self.failure
        outcomes = []
        for task in tasks:
            file_event_callback(FileGenerationEvent(task.item_id, task.source_path, FileQueueStatus.DONE,
                progress_percent=100, result=self.result))
            outcomes.append(FileGenerationOutcome(task.item_id, task.source_path, FileQueueStatus.DONE, self.result))
        return outcomes


@pytest.fixture
def queued(tmp_path, monkeypatch):
    directory = tmp_path / "managed"
    monkeypatch.setenv("COLIN_COLAB_DATA_DIR", str(directory))
    monkeypatch.setattr(ColabClient, "ensure_daemon", lambda self: None)
    SettingsStore(directory).save(ColabSettings(enabled=True))
    transport = ColabClient(directory)
    controller = FakeController(tmp_path / "results")
    supervisor = ColabSupervisor(directory, controller_factory=lambda: controller)
    lifecycle = FakeLifecycle()
    monkeypatch.setattr(supervisor, "lifecycle", lambda: lifecycle)
    settings = GenerationSettings(model_id="zerotts_202m_official", runtime_target="remote",
                                  output_dir=tmp_path / "explicit-output", speaker_id="maichi")
    return SimpleNamespace(directory=directory, client=transport, store=transport.store, controller=controller,
                           supervisor=supervisor, lifecycle=lifecycle, settings=settings)


def submit_text(queued, settings=None, key=None):
    return queued.client.submit("text", {"text": "Xin chào", "settings": settings or queued.settings}, key)


def test_managed_execution_is_disabled_by_default(tmp_path, monkeypatch):
    monkeypatch.setenv("COLIN_COLAB_DATA_DIR", str(tmp_path / "fresh"))
    settings = GenerationSettings(model_id="zerotts_202m_official", runtime_target="remote")
    assert not SettingsStore().load().enabled
    assert not client.should_manage(settings)
    with pytest.raises(GenerationError, match="Bật Colab"):
        ColabClient().submit("text", {"text": "Xin chào", "settings": settings})


def test_settings_snapshot_roundtrip_preserves_paths_provider_options_and_epub(tmp_path):
    settings = GenerationSettings(model_id="vieneu_v3_turbo", runtime_target="remote",
        output_dir=tmp_path / "out", reference_audio_path=tmp_path / "reference.wav",
        speaker_id="Ngọc Huyền", temperature=0.65, provider_options={"top_k": 17},
        epub_options={"chapter_start": 2, "chapter_end": 5, "breaks": {"chapter": {"mode": "silence", "duration_ms": 1700}}})
    restored = restore_settings(jsonable(settings))
    assert restored.output_dir == settings.output_dir
    assert restored.reference_audio_path == settings.reference_audio_path
    assert restored.provider_options == settings.provider_options
    assert restored.temperature == 0.65
    request = restored.to_request("Nội dung")
    assert request.epub_options.chapter_start == 2
    assert request.epub_options.chapter_end == 5
    assert request.epub_options.break_for("chapter").duration_ms == 1700


def test_mcp_remote_generation_reuses_idempotency_key_without_a_second_job(queued, tmp_path):
    manager = McpJobManager(object(), McpJobStore(tmp_path / "mcp.sqlite3"),
                            gpu_preferences=SimpleNamespace(load=lambda: {}))
    request = TextGenerationInput(text="Xin chào", model_id="zerotts_202m_official",
        idempotency_key="mcp-request-one", generation={"runtime_target": "remote"},
        output={"directory": str(tmp_path / "mcp-output")})
    try:
        first = manager.start_text(request)
        repeated = manager.start_text(request)
        assert first["job_id"].startswith("colab-")
        assert repeated["job_id"] == first["job_id"]
        assert len(queued.store.list()) == 1
        assert manager.store.list() == []
        assert manager.active_count() == 1
        with pytest.raises(ValueError, match="nội dung khác"):
            manager.start_text(request.model_copy(update={"text": "Nội dung mới"}))
        assert manager.get(first["job_id"])["job_id"] == first["job_id"]
    finally:
        manager._executor.shutdown(wait=True)


def test_qt_controller_text_and_files_use_managed_helpers(queued, monkeypatch, tmp_path):
    controller = object.__new__(AppController)
    controller.validate_license_for_model = Mock()
    text = Mock(return_value=queued.controller.result)
    files = Mock(return_value=[])
    monkeypatch.setattr(client, "generate_text", text)
    monkeypatch.setattr(client, "generate_files", files)
    progress = Mock()
    events = Mock()
    cancelled = Event()
    controller.generate_text("Xin chào", queued.settings, progress, cancelled)
    text.assert_called_once_with("Xin chào", queued.settings, progress, cancelled)
    tasks = [FileGenerationTask("file-one", tmp_path / "source.txt")]
    controller.generate_files(tasks, queued.settings, progress, events, cancelled)
    files.assert_called_once_with(tasks, queued.settings, progress, events, cancelled)


def test_cancel_before_running_does_not_construct_controller_or_allocate_runtime(queued):
    job = submit_text(queued)
    queued.client.control(job["job_id"], "cancel")
    queued.supervisor.run_job(queued.store.next_job())
    assert queued.store.get(job["job_id"])["status"] == "cancelled"
    assert queued.controller.calls == []
    assert queued.lifecycle.releases == 0
    assert context.managed_execution() is None


def test_profile_change_requires_a_new_request_before_running(queued, monkeypatch, tmp_path):
    from omni_tts_core.voice_profiles import VoiceProfileManager
    from omni_tts_shared.schemas import VoiceProfile
    audio = result_in(tmp_path / "reference").audio_path
    profile = VoiceProfile(profile_id="saved-profile", name="Test", audio_path=audio,
                           transcript="Nội dung gốc", duration_seconds=3, sample_rate=48000)
    monkeypatch.setattr(VoiceProfileManager, "get_profile", lambda self, profile_id: profile)
    queued.settings.model_id = "vieneu_v3_turbo"
    queued.settings.voice_profile_id = profile.profile_id
    queued.settings.voice_source_mode = "profile"
    job = submit_text(queued)
    profile.transcript = "Đã chỉnh lại nội dung"
    queued.supervisor.run_job(queued.store.next_job())
    record = queued.store.get(job["job_id"])
    assert record["status"] == "waiting"
    assert "Profile giọng đã đổi" in record["error"]
    assert queued.controller.calls == []


def test_cancellation_wins_when_a_running_job_reports_an_error(queued):
    job = submit_text(queued)
    queued.store.control(job["job_id"], "cancel")
    record = queued.store.wait_or_retry(job["job_id"], "Temporary error", "unavailable", retry=True)
    assert record["status"] == "cancelled"
    assert record["finished_at"]


def test_generation_success_and_cleanup_failure_are_reported_separately(queued):
    queued.lifecycle.fail_release = True
    job = submit_text(queued)
    queued.supervisor.run_job(queued.store.next_job())
    record = queued.store.get(job["job_id"])
    assert record["status"] == "succeeded"
    assert record["progress"] == 100
    assert Path(record["result"]["audio_path"]).is_file()
    assert record["error"] is None
    assert queued.store.state("cleanup_error")
    assert queued.client.wait(job["job_id"])["audio_path"] == str(queued.controller.result.audio_path)


def test_supervisor_persists_file_events_and_wait_restores_core_event_types(queued, tmp_path):
    source = tmp_path / "file.txt"
    source.write_text("Xin chào", encoding="utf-8")
    job = queued.client.submit("files", {"tasks": [FileGenerationTask("file-one", source)], "settings": queued.settings})
    queued.supervisor.run_job(queued.store.next_job())
    events, progress = [], []
    result = queued.client.wait(job["job_id"], file_event_callback=events.append, progress_callback=progress.append)
    assert len(result["files"]) == 1
    assert len(events) == 1
    assert isinstance(events[0], FileGenerationEvent)
    assert events[0].status == FileQueueStatus.DONE
    assert events[0].source_path == source
    assert isinstance(events[0].result, GenerateSpeechResult)
    assert progress[-1].percent == 100


def test_completed_file_job_replays_events_beyond_one_storage_page(queued, tmp_path):
    source = tmp_path / "file.txt"
    source.write_text("Xin chào", encoding="utf-8")
    job = queued.client.submit("files", {"tasks": [FileGenerationTask("file-one", source)], "settings": queued.settings})
    for index in range(225):
        queued.store.add_file_event(job["job_id"], jsonable(FileGenerationEvent(
            f"part-{index}", source, FileQueueStatus.RUNNING, progress_percent=index / 224 * 100)))
    queued.store.update(job["job_id"], status="succeeded", result={"files": []})
    events = []
    queued.client.wait(job["job_id"], file_event_callback=events.append)
    assert [event.item_id for event in events] == [f"part-{index}" for index in range(225)]


def test_text_helper_returns_typed_result_through_submit_and_wait(queued, monkeypatch):
    waited = Mock(return_value=jsonable(queued.controller.result))
    monkeypatch.setattr(queued.client, "wait", waited)
    monkeypatch.setattr(client, "ColabClient", lambda: queued.client)
    result = client.generate_text("Xin chào", queued.settings)
    assert isinstance(result, GenerateSpeechResult)
    assert result.audio_path == queued.controller.result.audio_path
    assert len(queued.store.list()) == 1


def test_files_helper_forwards_live_file_event_callback(queued, tmp_path, monkeypatch):
    source = tmp_path / "source.txt"
    source.write_text("Xin chào", encoding="utf-8")
    event_callback = Mock()
    waited = Mock(return_value={"files": []})
    monkeypatch.setattr(queued.client, "wait", waited)
    monkeypatch.setattr(client, "ColabClient", lambda: queued.client)
    client.generate_files([FileGenerationTask("file-one", source)], queued.settings, file_event_callback=event_callback)
    assert waited.call_args.kwargs["file_event_callback"] is event_callback


def test_explicit_resume_reuses_same_job_and_input_snapshot(queued):
    queued.controller.failure = GenerationError("Temporary generation failure")
    job = submit_text(queued, key="one-stable-request")
    queued.supervisor.run_job(queued.store.next_job())
    failed = queued.store.get(job["job_id"])
    assert failed["status"] == "waiting"
    queued.controller.failure = None
    resumed = queued.client.control(job["job_id"], "resume")
    assert resumed["job_id"] == job["job_id"]
    queued.supervisor.run_job(queued.store.next_job())
    final = queued.store.get(job["job_id"])
    assert final["status"] == "succeeded"
    assert final["payload"] == failed["payload"]
    assert queued.controller.calls[0][1].output_dir == queued.controller.calls[1][1].output_dir
    assert len(queued.store.list()) == 1


def test_default_output_directory_is_frozen_for_a_managed_job_across_resume(queued):
    settings = GenerationSettings(model_id="zerotts_202m_official", runtime_target="remote")
    queued.controller.failure = GenerationError("Temporary generation failure")
    job = submit_text(queued, settings=settings)
    queued.supervisor.run_job(queued.store.next_job())
    first_settings = queued.controller.calls[0][1]
    assert first_settings.output_dir is not None
    assert job["job_id"] in str(first_settings.output_dir)
    queued.controller.failure = None
    queued.client.control(job["job_id"], "resume")
    queued.supervisor.run_job(queued.store.next_job())
    assert queued.controller.calls[-1][1].output_dir == first_settings.output_dir


def test_changed_source_is_rejected_on_resume_before_controller_run(queued, tmp_path):
    source = tmp_path / "source.txt"
    source.write_text("Original", encoding="utf-8")
    queued.controller.failure = GenerationError("Temporary generation failure")
    job = queued.client.submit("files", {"tasks": [FileGenerationTask("file-one", source)], "settings": queued.settings})
    queued.supervisor.run_job(queued.store.next_job())
    assert len(queued.controller.calls) == 1
    source.write_text("Changed after enqueue", encoding="utf-8")
    queued.controller.failure = None
    queued.client.control(job["job_id"], "resume")
    queued.supervisor.run_job(queued.store.next_job())
    assert len(queued.controller.calls) == 1
    assert queued.store.get(job["job_id"])["status"] == "waiting"


def test_cancel_racing_with_completed_generation_keeps_verified_result_but_reports_cancelled(queued, monkeypatch):
    job = submit_text(queued)

    def generate_then_cancel(*args, **kwargs):
        queued.store.control(job["job_id"], "cancel")
        return queued.controller.result

    monkeypatch.setattr(queued.controller, "generate_text", generate_then_cancel)
    queued.supervisor.run_job(queued.store.next_job())
    record = queued.store.get(job["job_id"])
    assert record["status"] == "cancelled"
    assert Path(record["result"]["audio_path"]).is_file()
    with pytest.raises(GenerationCancelled):
        queued.client.wait(job["job_id"])


def test_file_resume_skips_verified_files_and_keeps_call_identity_for_remaining_file(queued, tmp_path, monkeypatch):
    tasks = []
    for name in ("one", "two"):
        source = tmp_path / f"{name}.txt"
        source.write_text(name, encoding="utf-8")
        tasks.append(FileGenerationTask(name, source))
    calls = []
    fail_second = [True]

    def generate_files(current, settings, progress_callback=None, cancel_event=None, file_event_callback=None):
        task = current[0]
        calls.append((task.item_id, context.managed_execution().next_call_id()))
        if task.item_id == "two" and fail_second[0]:
            raise GenerationError("Second file failed temporarily")
        result = result_in(tmp_path / "rendered" / task.item_id)
        file_event_callback(FileGenerationEvent(task.item_id, task.source_path, FileQueueStatus.DONE, result=result))
        return [FileGenerationOutcome(task.item_id, task.source_path, FileQueueStatus.DONE, result)]

    monkeypatch.setattr(queued.controller, "generate_files", generate_files)
    job = queued.client.submit("files", {"tasks": tasks, "settings": queued.settings})
    queued.supervisor.run_job(queued.store.next_job())
    assert queued.store.get(job["job_id"])["status"] == "waiting"
    first = tmp_path / "rendered/one/voice.wav"
    first_stamp = first.stat().st_mtime_ns
    fail_second[0] = False
    queued.client.control(job["job_id"], "resume")
    queued.supervisor.run_job(queued.store.next_job())
    record = queued.store.get(job["job_id"])
    assert record["status"] == "succeeded"
    assert [item[0] for item in calls] == ["one", "two", "two"]
    assert calls[1][1] == calls[2][1]
    assert first.stat().st_mtime_ns == first_stamp
    assert [item["item_id"] for item in record["result"]["files"]] == ["one", "two"]


@pytest.mark.parametrize("missing_outcome", (False, True))
def test_incomplete_file_outcomes_are_not_reported_success(queued, tmp_path, monkeypatch, missing_outcome):
    source = tmp_path / "source.txt"
    source.write_text("Source", encoding="utf-8")
    task = FileGenerationTask("one", source)
    outcomes = [] if missing_outcome else [FileGenerationOutcome("one", source, FileQueueStatus.FAILED)]
    monkeypatch.setattr(queued.controller, "generate_files", lambda *args, **kwargs: outcomes)
    job = queued.client.submit("files", {"tasks": [task], "settings": queued.settings})
    queued.supervisor.run_job(queued.store.next_job())
    assert queued.store.get(job["job_id"])["status"] == "waiting"


def test_file_output_proof_rejects_a_missing_required_split_file(queued, tmp_path):
    result = queued.controller.result.model_copy(update={"item_audio_paths": [tmp_path / "missing-required.wav"]})
    outcome = jsonable(FileGenerationOutcome("one", tmp_path / "source.txt", FileQueueStatus.DONE, result))
    try:
        record = output_proof(outcome)
    except (GenerationError, OSError):
        return
    assert not proof_valid(record)
