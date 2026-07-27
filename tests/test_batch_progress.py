from __future__ import annotations

import tempfile
import unittest
import wave
from pathlib import Path

from omni_tts_core.engines.batch_progress import audio_file_ready, report_ready_chunks


def _write_wav(path: Path, frames: int = 1600) -> None:
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(16000)
        handle.writeframes(b"\x00\x00" * frames)


class AudioFileReadyTest(unittest.TestCase):
    def test_missing_file_is_not_ready(self) -> None:
        self.assertFalse(audio_file_ready(Path("nope.wav")))

    def test_written_file_is_ready_once_old_enough(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "a.wav"
            _write_wav(path)
            self.assertFalse(audio_file_ready(path, minimum_age_seconds=999))  # too fresh
            self.assertTrue(audio_file_ready(path, minimum_age_seconds=0.0))

    def test_empty_file_is_not_ready(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "empty.wav"
            path.write_bytes(b"")
            self.assertFalse(audio_file_ready(path, minimum_age_seconds=0.0))


class ReportReadyChunksTest(unittest.TestCase):
    def setUp(self) -> None:
        self.progress: list[tuple[int, int]] = []
        self.chunks_done: list[int] = []

    def _callbacks(self):
        return (
            lambda done, total: self.progress.append((done, total)),
            lambda index, path: self.chunks_done.append(index),
        )

    def test_reports_incrementally_as_files_appear(self) -> None:
        """This is the behaviour that keeps a long batch from looking frozen."""
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            chunks = [{"output_path": str(root / f"c{i}.wav")} for i in range(3)]
            reported: set[int] = set()
            progress_cb, chunk_cb = self._callbacks()

            report_ready_chunks(chunks, reported, progress_cb, chunk_cb, force=True)
            self.assertEqual(self.progress, [])  # nothing written yet

            _write_wav(root / "c0.wav")
            report_ready_chunks(chunks, reported, progress_cb, chunk_cb, force=True)
            self.assertEqual(self.progress[-1], (1, 3))

            _write_wav(root / "c1.wav")
            report_ready_chunks(chunks, reported, progress_cb, chunk_cb, force=True)
            self.assertEqual(self.progress[-1], (2, 3))
            self.assertEqual(self.chunks_done, [0, 1])

    def test_never_reports_the_same_chunk_twice(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            chunks = [{"output_path": str(root / "c0.wav")}]
            _write_wav(root / "c0.wav")
            reported: set[int] = set()
            progress_cb, chunk_cb = self._callbacks()
            for _ in range(3):
                report_ready_chunks(chunks, reported, progress_cb, chunk_cb, force=True)
            self.assertEqual(self.chunks_done, [0])
            self.assertEqual(self.progress, [(1, 1)])

    def test_force_sweep_catches_a_just_written_final_chunk(self) -> None:
        """Without force the last chunk can stay unreported at N-1."""
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            chunks = [{"output_path": str(root / "c0.wav")}]
            _write_wav(root / "c0.wav")  # brand new, fails the age check
            reported: set[int] = set()
            progress_cb, chunk_cb = self._callbacks()

            report_ready_chunks(chunks, reported, progress_cb, chunk_cb)
            self.assertEqual(self.progress, [])

            report_ready_chunks(chunks, reported, progress_cb, chunk_cb, force=True)
            self.assertEqual(self.progress, [(1, 1)])


if __name__ == "__main__":
    unittest.main()
