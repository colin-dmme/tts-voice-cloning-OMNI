from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from omni_tts_core.file_queue import FileQueueOutputManifest
from omni_tts_core.media_player import MediaPlayerService, profile_preview_candidates
from omni_tts_shared.errors import OmniTtsError
from omni_tts_shared.schemas import AudioSampleMeta, GenerateSpeechResult, VoiceProfile


def _profile(root: Path, default_sample_id: str = "", extras: int = 0) -> VoiceProfile:
    main = root / "main.wav"
    main.write_bytes(b"main")
    samples = []
    for index in range(1, extras + 1):
        path = root / f"extra{index}.wav"
        path.write_bytes(b"extra")
        samples.append(
            AudioSampleMeta(sample_id=f"s{index}", role="neutral", audio_path=path)
        )
    return VoiceProfile(
        profile_id="p1",
        name="Giọng thử",
        audio_path=main,
        default_sample_id=default_sample_id,
        extra_samples=samples,
    )


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


class VoiceProfilePreviewTest(unittest.TestCase):
    def test_plays_main_sample_when_no_default_is_set(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            profile = _profile(root, extras=1)
            opened: list[Path] = []

            selected = MediaPlayerService(opened.append).play_profile(profile)

            self.assertEqual(selected, root / "main.wav")
            self.assertEqual(opened, [root / "main.wav"])

    def test_default_sample_wins_over_main_sample(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            profile = _profile(root, default_sample_id="s2", extras=2)
            opened: list[Path] = []

            selected = MediaPlayerService(opened.append).play_profile(profile)

            self.assertEqual(selected, root / "extra2.wav")
            self.assertEqual(opened, [root / "extra2.wav"])

    def test_requested_sample_id_is_played_exactly(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            profile = _profile(root, default_sample_id="s2", extras=2)
            opened: list[Path] = []

            selected = MediaPlayerService(opened.append).play_profile(profile, "s1")

            self.assertEqual(selected, root / "extra1.wav")
            self.assertEqual(opened, [root / "extra1.wav"])

    def test_unknown_sample_id_does_not_fall_back_to_another_take(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            profile = _profile(Path(temp), extras=1)

            with self.assertRaisesRegex(OmniTtsError, "Không tìm thấy mẫu phụ"):
                MediaPlayerService(lambda _path: None).play_profile(profile, "nope")

    def test_deleted_sample_file_has_profile_specific_error(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            profile = _profile(root)
            (root / "main.wav").unlink()

            with self.assertRaisesRegex(OmniTtsError, "audio mẫu của profile"):
                MediaPlayerService(lambda _path: None).play_profile(profile)

    def test_candidates_fall_back_from_missing_default_to_remaining_samples(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            profile = _profile(root, default_sample_id="gone", extras=2)

            candidates = profile_preview_candidates(profile)

            self.assertEqual(
                candidates,
                [root / "main.wav", root / "extra1.wav", root / "extra2.wav"],
            )


if __name__ == "__main__":
    unittest.main()
