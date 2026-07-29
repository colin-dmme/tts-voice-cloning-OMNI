from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from omni_tts_core.authoring.key_store import AuthoringKeyStore
from omni_tts_core.authoring.schemas import AuthoringBrief
from omni_tts_core.authoring.stores import AuthoringStateStore
from omni_tts_core.authoring.voice_context import VoiceContextResolver
from omni_tts_shared.schemas import VoiceProfile


class AuthoringKeyStoreTest(unittest.TestCase):
    def test_import_deduplicates_and_never_exposes_raw_keys(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "external.json"
            source.write_text(
                json.dumps(
                    {
                        "gemini": {
                            "models": ["gemini-test"],
                            "keys": [
                                {"name": "one", "key": "fake-key-value-one", "status": "active"},
                                {
                                    "name": "two",
                                    "key": "fake-key-value-two",
                                    "status": "quota_exceeded",
                                },
                            ],
                        }
                    }
                ),
                encoding="utf-8",
            )
            store = AuthoringKeyStore(root / "keys.json")
            report = store.import_file(source)
            second = store.import_file(source)

            self.assertEqual(report.added, 2)
            self.assertEqual(second.duplicates, 2)
            self.assertEqual(store.active_key_count("gemini"), 2)
            self.assertEqual(store.models("gemini"), ["gemini-test"])
            safe = store.safe_keys("gemini")
            self.assertNotIn("key", safe[0])
            self.assertNotIn("fake-key-value-one", json.dumps(safe))


class AuthoringStateStoreTest(unittest.TestCase):
    def test_preset_and_voice_context_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            store = AuthoringStateStore(Path(folder) / "state.json")
            brief = AuthoringBrief(platform="short_video", candidate_count=3)
            store.save_last_brief(brief)
            preset = store.save_preset(
                "Science Female",
                brief,
                voice_profile_id="voice-1",
                dialect_id="higgs_v1",
            )
            resolver = VoiceContextResolver(store)
            profile = VoiceProfile(
                profile_id="voice-1",
                name="Narrator",
                audio_path=Path("voice.wav"),
                language="en",
                notes="Ấm và rõ.",
            )
            saved = resolver.resolve(
                profile=profile,
                presentation="female",
                description="Giọng nữ trưởng thành.",
                remember=True,
            )
            restored = resolver.resolve(profile=profile)

            self.assertEqual(store.last_brief(), brief)
            self.assertEqual(store.presets()[0].preset_id, preset.preset_id)
            self.assertEqual(restored.presentation, "female")
            self.assertEqual(restored.description, saved.description)


if __name__ == "__main__":
    unittest.main()
