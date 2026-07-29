from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from omni_tts_core.pause_presets import PunctuationPausePresetStore
from omni_tts_shared.errors import OmniTtsError


class PunctuationPausePresetStoreTest(unittest.TestCase):
    def test_save_replace_reload_and_delete(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "presets.json"
            store = PunctuationPausePresetStore(path)
            store.save(
                "Kể chuyện",
                {
                    "sentence_pause_random_enabled": True,
                    "sentence_pause_min_ms": 280,
                    "sentence_pause_max_ms": 410,
                    "paragraph_pause_random_enabled": True,
                    "paragraph_pause_min_ms": 250,
                    "paragraph_pause_max_ms": 350,
                },
            )
            first = store.list_presets()[0]
            self.assertTrue(first.values["paragraph_pause_random_enabled"])
            self.assertEqual(first.values["paragraph_pause_min_ms"], 250)
            self.assertEqual(first.values["paragraph_pause_max_ms"], 350)
            store.save("kể CHUYỆN", {"sentence_pause_ms": 333})
            presets = PunctuationPausePresetStore(path).list_presets()
            self.assertEqual(len(presets), 1)
            self.assertEqual(presets[0].name, "kể CHUYỆN")
            self.assertEqual(presets[0].values["sentence_pause_ms"], 333)
            self.assertFalse(presets[0].values["sentence_pause_random_enabled"])
            self.assertTrue(store.delete("KỂ chuyện"))
            self.assertEqual(store.list_presets(), [])

    def test_rejects_invalid_range(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = PunctuationPausePresetStore(Path(temp) / "presets.json")
            with self.assertRaisesRegex(OmniTtsError, "Min"):
                store.save(
                    "Sai",
                    {
                        "comma_pause_min_ms": 200,
                        "comma_pause_max_ms": 100,
                    },
                )


if __name__ == "__main__":
    unittest.main()
