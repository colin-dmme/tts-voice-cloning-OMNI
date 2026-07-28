from __future__ import annotations

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
            )
            restored = GenerationHistoryStore(root / "history.sqlite3").list_entries()

            self.assertEqual(len(restored), 1)
            self.assertEqual(restored[0].history_id, created.history_id)
            self.assertEqual(restored[0].char_count, 1234)
            self.assertAlmostEqual(restored[0].duration_seconds, 65.4)
            self.assertEqual(restored[0].output_manifest.preferred_audio_path(), audio)
            self.assertEqual(restored[0].output_manifest.preferred_srt_path(), srt)

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
                error="worker failed",
            )

            restored = store.list_entries()[0]
            self.assertEqual(restored.status, HistoryStatus.FAILED)
            self.assertEqual(restored.error, "worker failed")
            self.assertTrue(restored.output_manifest.is_empty())
            self.assertEqual(store.delete([entry.history_id]), 1)
            self.assertEqual(store.list_entries(), [])


if __name__ == "__main__":
    unittest.main()
