from __future__ import annotations

import unittest
import json
import tempfile
from pathlib import Path

from omni_tts_core.generation_form import GenerationFormPresenter
from omni_tts_core.model_registry import ModelSpec
from omni_tts_shared.schemas import (
    GenerateSpeechRequest,
    ModelCapabilities,
    VoiceInputConfig,
)
from omni_tts_ui_tkinter.preferences import TkinterPreferences


class _Registry:
    def __init__(self, spec: ModelSpec) -> None:
        self.spec = spec

    def get(self, _model_id: str) -> ModelSpec:
        return self.spec


class GenerationFormTest(unittest.TestCase):
    def test_fixed_only_model_never_shows_profile(self) -> None:
        spec = ModelSpec(
            model_id="fixed",
            display_name="Fixed",
            provider="piper",
            model_type="tts",
            local_path=Path("model"),
            hf_repo="owner/repo",
            language_priority="vi",
            capabilities=ModelCapabilities(
                supported_languages=["vi"],
                supports_voice_profile=False,
            ),
            voice_input=VoiceInputConfig(modes=["fixed"], default_mode="fixed"),
        )

        descriptor = GenerationFormPresenter(_Registry(spec)).describe(
            "fixed", preferred_mode="profile"
        )

        self.assertEqual(descriptor.selected_voice_mode, "fixed")
        self.assertFalse(descriptor.show_voice_mode_selector)
        self.assertFalse(descriptor.show_profile)
        self.assertIn("không dùng Profile", descriptor.status_text)

    def test_hybrid_model_exposes_explicit_modes_and_fixed_voices(self) -> None:
        spec = ModelSpec(
            model_id="hybrid",
            display_name="Hybrid",
            provider="vieneu",
            model_type="tts",
            local_path=Path("worker"),
            hf_repo="owner/repo",
            language_priority="vi",
            voice_presets={"lan": "Ngọc Lan", "an": "Bình An"},
            default_voice_preset="lan",
            capabilities=ModelCapabilities(
                supported_languages=["vi"],
                supports_voice_profile=True,
                supports_voice_presets=True,
            ),
            voice_input=VoiceInputConfig(
                modes=["fixed", "profile"],
                default_mode="fixed",
            ),
        )
        presenter = GenerationFormPresenter(_Registry(spec))

        fixed = presenter.describe("hybrid")
        profile = presenter.describe("hybrid", "profile")

        self.assertTrue(fixed.show_voice_mode_selector)
        self.assertTrue(fixed.show_fixed_voice)
        self.assertFalse(fixed.show_profile)
        self.assertEqual(fixed.default_fixed_voice_id, "lan")
        self.assertEqual([item.voice_id for item in fixed.fixed_voices], ["lan", "an"])
        self.assertTrue(profile.show_profile)
        self.assertFalse(profile.show_fixed_voice)

    def test_request_normalization_prevents_mixed_voice_sources(self) -> None:
        fixed = GenerateSpeechRequest(
            text="Xin chào",
            voice_source_mode="fixed",
            speaker_id="lan",
            voice_profile_id="profile-1",
            reference_audio_path=Path("ref.wav"),
            reference_text="Mẫu",
        )
        profile = GenerateSpeechRequest(
            text="Xin chào",
            voice_source_mode="profile",
            speaker_id="lan",
            voice_profile_id="profile-1",
            reference_audio_path=Path("ref.wav"),
        )

        self.assertIsNone(fixed.voice_profile_id)
        self.assertIsNone(fixed.reference_audio_path)
        self.assertIsNone(fixed.reference_text)
        self.assertIsNone(profile.speaker_id)

    def test_legacy_preference_with_profile_migrates_to_profile_mode(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "ui.json"
            path.write_text(
                json.dumps({"voice_profile_id": "profile-1"}),
                encoding="utf-8",
            )

            settings = TkinterPreferences(path).load()

            self.assertEqual(settings["voice_source_mode"], "profile")


if __name__ == "__main__":
    unittest.main()
