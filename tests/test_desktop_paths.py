from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from omni_tts_core.desktop_paths import DesktopPathService
from omni_tts_core.file_queue import FileQueueOutputManifest
from omni_tts_shared.errors import OmniTtsError


class DesktopPathServiceTest(unittest.TestCase):
    def test_source_file_and_folder_use_distinct_actions(self) -> None:
        opened: list[Path] = []
        revealed: list[Path] = []
        service = DesktopPathService(opened.append, revealed.append)
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "story.txt"
            source.write_text("text", encoding="utf-8")
            self.assertEqual(service.open_source_file(source), source.resolve())
            self.assertEqual(service.open_source_folder(source), source.parent.resolve())
        self.assertEqual(opened, [source.resolve()])
        self.assertEqual(revealed, [source.resolve()])

    def test_result_folder_reveals_audio_instead_of_opening_audio(self) -> None:
        opened: list[Path] = []
        revealed: list[Path] = []
        service = DesktopPathService(opened.append, revealed.append)
        with tempfile.TemporaryDirectory() as temp:
            audio = Path(temp) / "result.wav"
            audio.touch()
            manifest = FileQueueOutputManifest(merged_audio_path=audio)
            self.assertEqual(service.open_result_folder(manifest), audio.parent.resolve())
        self.assertEqual(opened, [])
        self.assertEqual(revealed, [audio.resolve()])

    def test_result_folder_falls_back_to_existing_job_directory(self) -> None:
        opened: list[Path] = []
        service = DesktopPathService(opened.append, lambda _path: None)
        with tempfile.TemporaryDirectory() as temp:
            job_dir = Path(temp)
            manifest = FileQueueOutputManifest(job_dir=job_dir)
            self.assertEqual(service.open_result_folder(manifest), job_dir.resolve())
        self.assertEqual(opened, [job_dir.resolve()])

    def test_result_folder_can_open_parent_after_output_was_removed(self) -> None:
        opened: list[Path] = []
        service = DesktopPathService(opened.append, lambda _path: None)
        with tempfile.TemporaryDirectory() as temp:
            missing_audio = Path(temp) / "removed.wav"
            manifest = FileQueueOutputManifest(merged_audio_path=missing_audio)
            self.assertEqual(service.open_result_folder(manifest), Path(temp).resolve())
        self.assertEqual(opened, [Path(temp).resolve()])

    def test_missing_source_reports_a_clear_error(self) -> None:
        service = DesktopPathService(lambda _path: None, lambda _path: None)
        with self.assertRaisesRegex(OmniTtsError, "File nguồn không còn tồn tại"):
            service.open_source_file(Path("missing.txt"))


if __name__ == "__main__":
    unittest.main()
