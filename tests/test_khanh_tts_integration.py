from __future__ import annotations

import unittest
from pathlib import Path

from omni_tts_core.model_registry import ModelRegistry, ModelSpec
from omni_tts_core.voice_profile_policy import VoiceProfilePolicy
from omni_tts_shared.schemas import AudioSampleMeta, ModelCapabilities, RefAudioHints, VoiceProfile


class _SingleModelRegistry:
    def __init__(self, spec: ModelSpec) -> None:
        self.spec = spec

    def get(self, model_id: str) -> ModelSpec:
        return self.spec


class KhanhTtsIntegrationTest(unittest.TestCase):
    def test_khanh_tts_is_declared_as_omnivoice_ab_test_model(self) -> None:
        spec = ModelRegistry().get("khanh_tts_omnivoice")

        self.assertEqual(spec.provider, "omnivoice")
        self.assertEqual(spec.hf_repo, "kjanh/KhanhTTS-OmniVoice")
        self.assertFalse(spec.required)
        self.assertEqual(spec.language_priority, "vi-en")
        self.assertIn("vi", spec.capabilities.supported_languages)
        self.assertIn("en", spec.capabilities.supported_languages)
        self.assertTrue(spec.capabilities.supports_voice_profile)
        self.assertTrue(spec.capabilities.supports_speed)
        self.assertEqual(spec.catalog_info.get("risk"), "test")

    def test_omnivoice_policy_keeps_optional_profile_transcript(self) -> None:
        spec = ModelSpec(
            model_id="khanh_tts_omnivoice",
            display_name="KhanhTTS OmniVoice",
            provider="omnivoice",
            model_type="tts",
            local_path=Path("model"),
            hf_repo="kjanh/KhanhTTS-OmniVoice",
            language_priority="vi-en",
            capabilities=ModelCapabilities(supported_languages=["vi", "en"]),
            ref_audio_hints=RefAudioHints(needs_transcript=False),
        )
        policy = VoiceProfilePolicy(_SingleModelRegistry(spec))
        profile = VoiceProfile(
            profile_id="voice-1",
            name="Voice 1",
            audio_path=Path("voice.wav"),
            transcript="Reference transcript.",
            duration_seconds=5.0,
        )

        self.assertEqual(
            policy.resolve_transcript(profile, "khanh_tts_omnivoice"),
            "Reference transcript.",
        )
        self.assertEqual(policy.check_compatibility(profile, "khanh_tts_omnivoice").status, "ok")

    def test_selected_profile_sample_supplies_its_own_transcript(self) -> None:
        spec = ModelSpec(
            model_id="khanh_tts_omnivoice",
            display_name="KhanhTTS OmniVoice",
            provider="omnivoice",
            model_type="tts",
            local_path=Path("model"),
            hf_repo="kjanh/KhanhTTS-OmniVoice",
            language_priority="vi-en",
            capabilities=ModelCapabilities(supported_languages=["vi", "en"]),
            ref_audio_hints=RefAudioHints(needs_transcript=False),
        )
        policy = VoiceProfilePolicy(_SingleModelRegistry(spec))
        profile = VoiceProfile(
            profile_id="voice-1",
            name="Voice 1",
            audio_path=Path("main.wav"),
            transcript="Main transcript.",
            duration_seconds=5.0,
            default_sample_id="sample-2",
            extra_samples=[
                AudioSampleMeta(
                    sample_id="sample-2",
                    audio_path=Path("sample.wav"),
                    transcript="Sample transcript.",
                    duration_seconds=4.0,
                )
            ],
        )

        self.assertEqual(policy.resolve_audio_path(profile, "khanh_tts_omnivoice"), Path("sample.wav"))
        self.assertEqual(policy.resolve_transcript(profile, "khanh_tts_omnivoice"), "Sample transcript.")


if __name__ == "__main__":
    unittest.main()
