from __future__ import annotations

import pickle
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from omni_tts_core.engines import omnivoice_engine as oe


class SavablePrompt:
    """Fake VoiceClonePrompt whose save() writes a marker file (like 0.2.1)."""

    def __init__(self, tag: str) -> None:
        self.tag = tag

    def save(self, path: str) -> None:
        Path(path).write_text(f"pt::{self.tag}", encoding="utf-8")


class LegacyPrompt:
    """Fake prompt without save() — exercises the pickle fallback."""

    def __init__(self, tag: str) -> None:
        self.tag = tag


class FakePromptCls:
    """Stands in for omnivoice.VoiceClonePrompt with a load() classmethod."""

    last_loaded: str | None = None

    @classmethod
    def load(cls, path: str) -> str:
        cls.last_loaded = Path(path).read_text(encoding="utf-8")
        return f"loaded::{cls.last_loaded}"


class FakeModel:
    def __init__(self, prompt) -> None:
        self._prompt = prompt
        self.build_calls = 0

    def create_voice_clone_prompt(self, audio_path, transcript):
        self.build_calls += 1
        return self._prompt


class OmnivoicePromptCacheTests(unittest.TestCase):
    def setUp(self) -> None:
        self._orig_cls = oe._voice_clone_prompt_cls
        FakePromptCls.last_loaded = None

    def tearDown(self) -> None:
        oe._voice_clone_prompt_cls = self._orig_cls

    def test_build_writes_pt_and_removes_legacy_pkl(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            asset = Path(tmp)
            (asset / "voice_clone_prompt.pkl").write_bytes(b"stale")
            model = FakeModel(SavablePrompt("abc"))

            result = oe._load_or_build_voice_prompt(
                model, asset, Path("ref.wav"), "hello"
            )

            self.assertIsInstance(result, SavablePrompt)
            self.assertEqual(model.build_calls, 1)
            self.assertTrue((asset / "voice_clone_prompt.pt").exists())
            self.assertFalse((asset / "voice_clone_prompt.pkl").exists())

    def test_pt_cache_hit_skips_rebuild(self) -> None:
        oe._voice_clone_prompt_cls = lambda: FakePromptCls
        with tempfile.TemporaryDirectory() as tmp:
            asset = Path(tmp)
            (asset / "voice_clone_prompt.pt").write_text("pt::cached", encoding="utf-8")
            model = FakeModel(SavablePrompt("new"))

            result = oe._load_or_build_voice_prompt(
                model, asset, Path("ref.wav"), "hi"
            )

            self.assertEqual(result, "loaded::pt::cached")
            self.assertEqual(model.build_calls, 0)

    def test_legacy_pkl_is_read_when_no_pt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            asset = Path(tmp)
            with (asset / "voice_clone_prompt.pkl").open("wb") as f:
                pickle.dump(LegacyPrompt("old"), f)
            model = FakeModel(SavablePrompt("new"))

            result = oe._load_or_build_voice_prompt(
                model, asset, Path("ref.wav"), "hi"
            )

            self.assertIsInstance(result, LegacyPrompt)
            self.assertEqual(model.build_calls, 0)

    def test_fallback_to_pickle_when_prompt_has_no_save(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            asset = Path(tmp)
            model = FakeModel(LegacyPrompt("xyz"))

            result = oe._load_or_build_voice_prompt(
                model, asset, Path("ref.wav"), "hi"
            )

            self.assertIsInstance(result, LegacyPrompt)
            self.assertTrue((asset / "voice_clone_prompt.pkl").exists())
            self.assertFalse((asset / "voice_clone_prompt.pt").exists())


if __name__ == "__main__":
    unittest.main()
