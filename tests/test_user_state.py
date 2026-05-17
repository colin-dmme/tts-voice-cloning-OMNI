from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from omni_tts_core.user_state import export_user_state, restore_user_state
from omni_tts_core.voice_profiles import VoiceProfileManager


class UserStateTest(unittest.TestCase):
    def test_export_and_restore_profiles_with_portable_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            profiles_dir = root / "voices" / "profiles"
            samples_dir = root / "voices" / "samples"
            config_dir = root / "config"
            profiles_dir.mkdir(parents=True)
            samples_dir.mkdir(parents=True)
            config_dir.mkdir(parents=True)

            sample = samples_dir / "voice-123.wav"
            sample.write_bytes(b"fake wav")
            profile = {
                "profile_id": "voice-123",
                "name": "Voice",
                "audio_path": str(sample),
                "transcript": "hello",
                "language": "en",
                "created_at": "2026-05-17T00:00:00",
                "updated_at": "2026-05-17T00:00:00",
                "duration_seconds": 4.0,
                "sample_rate": 24000,
                "extra_samples": [],
            }
            (profiles_dir / "voice-123.json").write_text(
                json.dumps(profile, ensure_ascii=False), encoding="utf-8"
            )
            (config_dir / "ui_tkinter.json").write_text(
                json.dumps(
                    {
                        "model_id": "qwen3_tts_17b_base",
                        "voice_profile_id": "voice-123",
                        "window_geometry": "1800x900+20+20",
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            export_user_state(root)
            portable_profile = json.loads(
                (root / "user_state" / "voices" / "profiles" / "voice-123.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(portable_profile["audio_path"], "voices/samples/voice-123.wav")

            shutil_root = root / "new-machine"
            restore_user_state(shutil_root)
            self.assertFalse((shutil_root / "voices" / "profiles" / "voice-123.json").exists())

            (shutil_root / "user_state").mkdir(parents=True)
            _copy_tree(root / "user_state", shutil_root / "user_state")
            restore_user_state(shutil_root)

            restored_profile_path = shutil_root / "voices" / "profiles" / "voice-123.json"
            restored_profile = json.loads(restored_profile_path.read_text(encoding="utf-8"))
            self.assertEqual(
                restored_profile["audio_path"],
                str((shutil_root / "voices" / "samples" / "voice-123.wav").resolve()),
            )
            self.assertTrue((shutil_root / "voices" / "samples" / "voice-123.wav").exists())

            restored_settings = json.loads(
                (shutil_root / "config" / "ui_tkinter.json").read_text(encoding="utf-8")
            )
            self.assertEqual(restored_settings["model_id"], "qwen3_tts_17b_base")
            self.assertEqual(restored_settings["voice_profile_id"], "voice-123")
            self.assertNotIn("window_geometry", restored_settings)

    def test_voice_profile_manager_resolves_stale_absolute_sample_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            profiles_dir = root / "profiles"
            samples_dir = root / "samples"
            profiles_dir.mkdir()
            samples_dir.mkdir()
            (samples_dir / "voice-123.wav").write_bytes(b"fake wav")
            (profiles_dir / "voice-123.json").write_text(
                json.dumps(
                    {
                        "profile_id": "voice-123",
                        "name": "Voice",
                        "audio_path": "C:/old-machine/voices/samples/voice-123.wav",
                        "transcript": "hello",
                        "language": "en",
                        "duration_seconds": 4.0,
                        "sample_rate": 24000,
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            manager = VoiceProfileManager(profiles_dir=profiles_dir, samples_dir=samples_dir)
            profile = manager.get_profile("voice-123")
            self.assertEqual(profile.audio_path, samples_dir / "voice-123.wav")


def _copy_tree(source: Path, target: Path) -> None:
    for path in source.rglob("*"):
        relative = path.relative_to(source)
        destination = target / relative
        if path.is_dir():
            destination.mkdir(parents=True, exist_ok=True)
        else:
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(path.read_bytes())


if __name__ == "__main__":
    unittest.main()
