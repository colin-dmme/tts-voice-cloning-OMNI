from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from omni_tts_core.designed_voices import DesignedVoiceStore
from omni_tts_core.service import TtsService
from omni_tts_shared.schemas import GenerateSpeechRequest


class DesignSchemaTests(unittest.TestCase):
    def test_design_mode_keeps_designed_voice_and_clears_rest(self) -> None:
        req = GenerateSpeechRequest(
            text="hi",
            voice_source_mode="design",
            designed_voice_id="dv1",
            voice_profile_id="p1",
            speaker_id="Adam",
        )
        self.assertEqual(req.designed_voice_id, "dv1")
        self.assertIsNone(req.voice_profile_id)
        self.assertIsNone(req.speaker_id)

    def test_designed_voice_dropped_outside_design_mode(self) -> None:
        req = GenerateSpeechRequest(
            text="hi", voice_source_mode="profile", designed_voice_id="dv1", voice_profile_id="p1"
        )
        self.assertIsNone(req.designed_voice_id)
        self.assertEqual(req.voice_profile_id, "p1")


class ServiceGatingTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.service = TtsService()
        # Isolate the designed-voice store so the test never touches real data.
        self.service.designed_voices = DesignedVoiceStore(store_dir=Path(self._tmp.name))

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_voice_kinds_gated_by_capabilities(self) -> None:
        self.assertEqual(
            self.service.voice_kinds_for_model("omnivoice_base"), ("clone", "design")
        )
        vieneu = next(
            m.model_id for m in self.service.registry.tts_models() if "vieneu" in m.model_id
        )
        self.assertEqual(self.service.voice_kinds_for_model(vieneu), ("clone",))

    def test_resolve_instruct_only_for_design_capable(self) -> None:
        voice = self.service.save_designed_voice(name="X", instruct="female, warm")
        req = GenerateSpeechRequest(
            text="hi", voice_source_mode="design", designed_voice_id=voice.designed_voice_id
        )
        omni_spec = self.service.registry.get("omnivoice_base")
        self.assertEqual(self.service._resolve_instruct(req, omni_spec), "female, warm")
        vieneu_id = next(
            m.model_id for m in self.service.registry.tts_models() if "vieneu" in m.model_id
        )
        vieneu_spec = self.service.registry.get(vieneu_id)
        self.assertIsNone(self.service._resolve_instruct(req, vieneu_spec))

    def test_selectable_items_gated(self) -> None:
        self.service.save_designed_voice(name="D1", instruct="male, deep")
        design_items = self.service.selectable_voice_items("omnivoice_base")
        self.assertIn("design", {i.kind for i in design_items})
        vieneu_id = next(
            m.model_id for m in self.service.registry.tts_models() if "vieneu" in m.model_id
        )
        vieneu_items = self.service.selectable_voice_items(vieneu_id)
        self.assertNotIn("design", {i.kind for i in vieneu_items})


if __name__ == "__main__":
    unittest.main()
