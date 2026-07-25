from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from omni_tts_core.file_queue import FileQueueOutputManifest
from omni_tts_core.media_player import MediaPlayerService
from omni_tts_shared.errors import OmniTtsError
from omni_tts_shared.schemas import GenerateSpeechResult


class MediaPlayerServiceTest(unittest.TestCase):
    def test_play_result_opens_generated_audio_with_default_app(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            audio = root / "file có khoảng trắng.mp3"
            audio.write_bytes(b"audio")
            opened: list[Path] = []
            service = MediaPlayerService(opened.append)
            result = GenerateSpeechResult(
                job_id="job",
                audio_path=audio,
                job_dir=root,
                segment_count=1,
                duration_seconds=1.0,
                message="done",
            )

            selected = service.play_result(result)

            self.assertEqual(selected, audio)
            self.assertEqual(opened, [audio])

    def test_play_manifest_prefers_merged_audio(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            merged = root / "merged.wav"
            split = root / "split.wav"
            merged.write_bytes(b"merged")
            split.write_bytes(b"split")
            opened: list[Path] = []
            service = MediaPlayerService(opened.append)
            manifest = FileQueueOutputManifest(
                merged_audio_path=merged,
                split_audio_paths=(split,),
            )

            selected = service.play_manifest(manifest)

            self.assertEqual(selected, merged)
            self.assertEqual(opened, [merged])

    def test_play_manifest_falls_back_to_first_existing_split_audio(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            existing = root / "part 002.wav"
            existing.write_bytes(b"split")
            opened: list[Path] = []
            service = MediaPlayerService(opened.append)
            manifest = FileQueueOutputManifest(
                merged_audio_path=root / "missing.wav",
                split_audio_paths=(root / "part 001.wav", existing),
            )

            selected = service.play_manifest(manifest)

            self.assertEqual(selected, existing)
            self.assertEqual(opened, [existing])

    def test_missing_audio_has_user_facing_error(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            service = MediaPlayerService(lambda _path: None)
            manifest = FileQueueOutputManifest(
                merged_audio_path=Path(temp) / "missing.mp3"
            )

            with self.assertRaisesRegex(OmniTtsError, "Không tìm thấy file audio"):
                service.play_manifest(manifest)

    def test_default_app_failure_is_wrapped(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            audio = Path(temp) / "audio.wav"
            audio.write_bytes(b"audio")

            def fail(_path: Path) -> None:
                raise OSError("no association")

            with self.assertRaisesRegex(OmniTtsError, "ứng dụng mặc định"):
                MediaPlayerService(fail).play_first_available([audio])


if __name__ == "__main__":
    unittest.main()
