from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from omni_tts_core.generation_history import (
    GenerationHistoryStore,
    HistoryStatus,
)
from omni_tts_shared.schemas import GenerateSpeechResult


class GenerationHistoryStoreTest(unittest.TestCase):
    def test_records_result_metadata_and_paths_independently_from_queue(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            audio = root / "story.wav"
            srt = root / "story.srt"
            audio.write_bytes(b"wav")
            srt.write_text("1", encoding="utf-8")
            result = GenerateSpeechResult(
                job_id="job-1",
                audio_path=audio,
                srt_path=srt,
                job_dir=root / "job-1",
                segment_count=2,
                duration_seconds=65.4,
                message="done",
            )
            store = GenerationHistoryStore(root / "history.sqlite3")

            created = store.record(
                mode="file",
                source_label="story.txt",
                source_path=root / "story.txt",
                char_count=1234,
                model_id="piper-test",
                provider_id="piper",
                status=HistoryStatus.DONE,
                result=result,
                settings_snapshot={"model_id": "piper-test", "speed": 1.15},
            )
            restored = GenerationHistoryStore(root / "history.sqlite3").list_entries()

            self.assertEqual(len(restored), 1)
            self.assertEqual(restored[0].history_id, created.history_id)
            self.assertEqual(restored[0].char_count, 1234)
            self.assertAlmostEqual(restored[0].duration_seconds, 65.4)
            self.assertEqual(restored[0].output_manifest.preferred_audio_path(), audio)
            self.assertEqual(restored[0].output_manifest.preferred_srt_path(), srt)
            self.assertEqual(restored[0].settings_snapshot["speed"], 1.15)

    def test_failure_is_saved_without_output_and_history_can_be_deleted(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = GenerationHistoryStore(Path(temp) / "history.sqlite3")
            entry = store.record(
                mode="text",
                source_label="Văn bản trực tiếp",
                char_count=10,
                model_id="model",
                provider_id="provider",
                status=HistoryStatus.FAILED,
                settings_snapshot={"model_id": "model"},
                source_text="Văn bản đã nhập",
                error="worker failed",
            )

            restored = store.list_entries()[0]
            self.assertEqual(restored.status, HistoryStatus.FAILED)
            self.assertEqual(restored.error, "worker failed")
            self.assertEqual(restored.source_text, "Văn bản đã nhập")
            self.assertTrue(restored.output_manifest.is_empty())
            self.assertEqual(store.delete([entry.history_id]), 1)
            self.assertEqual(store.list_entries(), [])

    def test_migrates_legacy_database_without_losing_old_entries(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "history.sqlite3"
            connection = sqlite3.connect(path)
            connection.execute(
                """
                CREATE TABLE generation_history (
                    history_id TEXT PRIMARY KEY, mode TEXT NOT NULL,
                    source_label TEXT NOT NULL, source_path TEXT NOT NULL DEFAULT '',
                    char_count INTEGER NOT NULL DEFAULT 0,
                    model_id TEXT NOT NULL DEFAULT '', provider_id TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL, duration_seconds REAL NOT NULL DEFAULT 0,
                    output_manifest_json TEXT NOT NULL DEFAULT '{}',
                    error TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                INSERT INTO generation_history VALUES
                ('old-1', 'file', 'old.txt', '', 10, 'piper', 'piper',
                 'done', 1.0, '{}', '', '2026-07-28T10:00:00')
                """
            )
            connection.commit()
            connection.close()

            restored = GenerationHistoryStore(path).list_entries()

            self.assertEqual(len(restored), 1)
            self.assertEqual(restored[0].history_id, "old-1")
            self.assertEqual(restored[0].settings_snapshot, {})
            self.assertEqual(restored[0].source_text, "")


if __name__ == "__main__":
    unittest.main()
