from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from omni_tts_core.file_queue import (
    FileQueueOutputManifest,
    FileQueueStatus,
    FileQueueStore,
    settings_fingerprint,
)
from omni_tts_core.progress import ProgressEvent
from omni_tts_shared.schemas import GenerateSpeechResult
from omni_tts_ui_tkinter.app import _result_output_manifest
from omni_tts_ui_tkinter.controller import TkinterController
from omni_tts_ui_tkinter.state import UiSettings


class _FakeJobStore:
    @staticmethod
    def save_json(path: Path, payload) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}", encoding="utf-8")


class _FakeService:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.job_store = _FakeJobStore()

    def generate_from_source_file(
        self,
        source_path: Path,
        request_template,
        output_dir=None,
        progress_callback=None,
        cancel_event=None,
    ) -> GenerateSpeechResult:
        if "bad" in source_path.name:
            raise RuntimeError("worker failed")
        if progress_callback is not None:
            progress_callback(ProgressEvent("Đang tạo", 1, 2))
            progress_callback(ProgressEvent("Đã tạo", 2, 2))
        job_dir = self.root / f"job-{source_path.stem}"
        job_dir.mkdir(parents=True, exist_ok=True)
        audio_path = self.root / f"{source_path.stem}.wav"
        audio_path.write_bytes(b"wav")
        return GenerateSpeechResult(
            job_id=f"job-{source_path.stem}",
            audio_path=audio_path,
            job_dir=job_dir,
            segment_count=1,
            duration_seconds=1.0,
            message="Đã tạo audio.",
        )


class TestFileQueueStore(unittest.TestCase):
    def test_persists_status_and_rejects_duplicate_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source.txt"
            source.write_text("hello", encoding="utf-8")
            store = FileQueueStore(root / "queue.sqlite3")

            item, added = store.add(source, 5)
            duplicate, duplicate_added = store.add(source, 5)
            store.mark_running(item.item_id)
            store.mark_done(
                item.item_id,
                job_id="job-1",
                output_paths=[source],
                fingerprint="settings-1",
            )

            restored = FileQueueStore(root / "queue.sqlite3").get(item.item_id)
            self.assertTrue(added)
            self.assertFalse(duplicate_added)
            self.assertEqual(duplicate.item_id, item.item_id)
            self.assertEqual(restored.status, FileQueueStatus.DONE)
            self.assertEqual(restored.attempt_count, 1)
            self.assertEqual(restored.job_id, "job-1")

    def test_add_many_adds_batch_and_counts_duplicates(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            existing = root / "existing.txt"
            second = root / "second.txt"
            third = root / "third.txt"
            for path in (existing, second, third):
                path.write_text(path.stem, encoding="utf-8")
            store = FileQueueStore(root / "queue.sqlite3")
            store.add(existing, 8)

            added, duplicates = store.add_many(
                [
                    (existing, 8),
                    (second, 6),
                    (second, 6),
                    (third, 5),
                ]
            )

            self.assertEqual(duplicates, 2)
            self.assertEqual([item.source_path.name for item in added], ["second.txt", "third.txt"])
            self.assertEqual(
                [item.source_path.name for item in store.list_items()],
                ["existing.txt", "second.txt", "third.txt"],
            )

    def test_persists_output_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source.txt"
            split_dir = root / "source"
            source.write_text("hello", encoding="utf-8")
            split_dir.mkdir()
            split_audio = split_dir / "source_001.wav"
            merged_audio = split_dir / "source.wav"
            srt_path = split_dir / "source.srt"
            for path in (split_audio, merged_audio, srt_path):
                path.write_bytes(b"out")
            store = FileQueueStore(root / "queue.sqlite3")
            item, _ = store.add(source, 5)
            manifest = FileQueueOutputManifest(
                split_output_dirs=(split_dir,),
                split_audio_paths=(split_audio,),
                merged_audio_path=merged_audio,
                srt_paths=(srt_path,),
                job_dir=root / "job",
            )

            store.mark_done(
                item.item_id,
                job_id="job-1",
                output_paths=[split_audio, merged_audio, srt_path],
                fingerprint="settings-1",
                output_manifest=manifest,
            )

            restored = FileQueueStore(root / "queue.sqlite3").get(item.item_id)
            self.assertEqual(restored.output_manifest.split_output_dirs, (split_dir,))
            self.assertEqual(restored.output_manifest.split_audio_paths, (split_audio,))
            self.assertEqual(restored.output_manifest.merged_audio_path, merged_audio)
            self.assertEqual(restored.output_manifest.srt_paths, (srt_path,))

    def test_manifest_can_infer_legacy_flat_paths(self) -> None:
        root = Path("C:/out/story")
        split_one = root / "story_001.wav"
        split_two = root / "story_002.wav"
        merged = root / "story.wav"
        srt_path = root / "story.srt"

        manifest = FileQueueOutputManifest.from_flat_paths(
            [split_one, split_two, merged, srt_path]
        )

        self.assertEqual(manifest.split_output_dirs, (root,))
        self.assertEqual(manifest.split_audio_paths, (split_one, split_two))
        self.assertEqual(manifest.merged_audio_path, merged)
        self.assertEqual(manifest.srt_paths, (srt_path,))

    def test_result_output_manifest_keeps_split_folder_merged_audio_and_srt(self) -> None:
        root = Path("C:/out/story")
        result = GenerateSpeechResult(
            job_id="job-1",
            audio_path=root / "story.wav",
            srt_path=root / "story.srt",
            job_dir=root / "job",
            segment_count=2,
            duration_seconds=1.0,
            message="done",
            item_audio_paths=[root / "story_001.wav", root / "story_002.wav"],
        )

        manifest = _result_output_manifest(result)

        self.assertEqual(manifest.paths_for("all"), (root, root / "story.wav", root / "story.srt"))
        self.assertEqual(manifest.paths_for("split_audio"), tuple(result.item_audio_paths))

    def test_recovers_running_and_marks_missing_output_outdated(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            first_source = root / "first.txt"
            second_source = root / "second.txt"
            first_source.write_text("one", encoding="utf-8")
            second_source.write_text("two", encoding="utf-8")
            store = FileQueueStore(root / "queue.sqlite3")
            running, _ = store.add(first_source, 3)
            completed, _ = store.add(second_source, 3)
            store.mark_running(running.item_id)
            store.mark_running(completed.item_id)
            store.mark_done(
                completed.item_id,
                job_id="job-2",
                output_paths=[root / "missing.wav"],
                fingerprint="settings-1",
            )

            store.recover_and_validate()

            self.assertEqual(store.get(running.item_id).status, FileQueueStatus.INTERRUPTED)
            self.assertEqual(store.get(completed.item_id).status, FileQueueStatus.OUTDATED)

    def test_settings_fingerprint_marks_completed_items_outdated(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source.txt"
            output = root / "source.wav"
            source.write_text("hello", encoding="utf-8")
            output.write_bytes(b"wav")
            store = FileQueueStore(root / "queue.sqlite3")
            item, _ = store.add(source, 5)
            store.mark_running(item.item_id)
            old_fingerprint = settings_fingerprint({"model": "old"})
            store.mark_done(
                item.item_id,
                job_id="job-3",
                output_paths=[output],
                fingerprint=old_fingerprint,
            )

            changed = store.mark_settings_outdated(settings_fingerprint({"model": "new"}))

            self.assertEqual(changed, 1)
            self.assertEqual(store.get(item.item_id).status, FileQueueStatus.OUTDATED)


class TestFileBatchController(unittest.TestCase):
    def test_batch_continues_after_one_file_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            good_one = root / "good-one.txt"
            bad = root / "bad.txt"
            good_two = root / "good-two.txt"
            for path in (good_one, bad, good_two):
                path.write_text(path.stem, encoding="utf-8")
            controller = TkinterController(service=_FakeService(root))
            controller.validate_license_for_model = lambda _model_id: None
            events = []

            outcomes = controller.generate_files(
                [
                    ("one", good_one),
                    ("bad", bad),
                    ("two", good_two),
                ],
                UiSettings(),
                file_event_callback=events.append,
            )

            self.assertEqual(
                [outcome.status for outcome in outcomes],
                [
                    FileQueueStatus.DONE,
                    FileQueueStatus.FAILED,
                    FileQueueStatus.DONE,
                ],
            )
            self.assertTrue((root / "job-good-one" / "result.json").exists())
            self.assertTrue((root / "job-good-two" / "result.json").exists())
            self.assertTrue(
                any(
                    event.item_id == "bad" and event.status == FileQueueStatus.FAILED
                    for event in events
                )
            )


if __name__ == "__main__":
    unittest.main()
