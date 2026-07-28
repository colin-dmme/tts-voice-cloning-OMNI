from __future__ import annotations

import unittest
from pathlib import Path

from omni_tts_core.ui_presenters import labels
from omni_tts_core.ui_presenters.settings_state import (
    DEFAULT_GENERATION_PREFERENCES,
    GenerationSettings,
)
from omni_tts_shared.schemas import ModelStatus


class LabelsTest(unittest.TestCase):
    def test_runtime_device_label_known_and_unknown(self) -> None:
        self.assertEqual(labels.runtime_device_label("auto-cuda"), "Auto → CUDA")
        self.assertEqual(labels.runtime_device_label("cpu"), "CPU")
        self.assertEqual(labels.runtime_device_label("weird"), "weird")
        self.assertEqual(labels.runtime_device_label(None), "Không rõ")

    def test_model_badges_prefers_origin_over_category(self) -> None:
        badges = labels.model_badges({"origin": "official", "category": "community", "risk": "test"})
        self.assertEqual(badges[0], "Official")
        self.assertIn("Test", badges)

    def test_setup_status_label(self) -> None:
        self.assertEqual(labels.setup_status_label("ok"), "OK")
        self.assertEqual(labels.setup_status_label("missing"), "Thiếu")

    def test_downloaded_non_worker_model_does_not_claim_runtime_ready(self) -> None:
        item = ModelStatus(
            model_id="omnivoice_test",
            display_name="OmniVoice Test",
            provider="omnivoice",
            model_type="folder",
            hf_repo="example/model",
            local_path=Path("models/example"),
            installed=True,
        )

        self.assertEqual(labels.model_status_label(item), "Model đã tải")

    def test_runtime_device_detail_strips_cuda_prefix(self) -> None:
        detail = labels.runtime_device_detail("cuda", "CUDA - RTX 5090")
        self.assertEqual(detail, " - RTX 5090")
        self.assertEqual(labels.runtime_device_detail("cpu", "Intel"), "")


class SettingsStateTest(unittest.TestCase):
    def test_defaults_round_trip_through_preferences(self) -> None:
        settings = GenerationSettings.from_preferences(dict(DEFAULT_GENERATION_PREFERENCES))
        payload = settings.to_preferences()
        for key, value in DEFAULT_GENERATION_PREFERENCES.items():
            self.assertEqual(payload[key], value, msg=key)

    def test_to_request_syncs_srt_padding_with_paragraph_pause(self) -> None:
        settings = GenerationSettings(paragraph_pause_ms=321)
        request = settings.to_request("xin chào")
        self.assertEqual(request.srt_file_padding_ms, 321)

    def test_split_output_maps_to_output_mode(self) -> None:
        self.assertEqual(GenerationSettings(split_output=True).to_request("a").output_mode, "split")
        self.assertEqual(GenerationSettings(split_output=False).to_request("a").output_mode, "merged")

    def test_output_dir_round_trips_as_path(self) -> None:
        settings = GenerationSettings.from_preferences({"output_dir": "C:/out"})
        self.assertEqual(settings.output_dir, Path("C:/out"))
        self.assertEqual(settings.to_preferences()["output_dir"], str(Path("C:/out")))
        empty = GenerationSettings.from_preferences({"output_dir": ""})
        self.assertIsNone(empty.output_dir)

    def test_punctuation_preferences_round_trip(self) -> None:
        settings = GenerationSettings.from_preferences(
            {
                "punctuation_pause_enabled": False,
                "sentence_pause_ms": 333,
                "sentence_pause_random_enabled": True,
                "sentence_pause_min_ms": 250,
                "sentence_pause_max_ms": 390,
                "comma_pause_ms": 88,
                "clause_pause_ms": 177,
                "ellipsis_pause_ms": 444,
                "chunk_pause_ms": 111,
            }
        )
        request = settings.to_request("xin chào")
        self.assertFalse(request.punctuation_pause_enabled)
        self.assertEqual(request.sentence_pause_ms, 333)
        self.assertTrue(request.sentence_pause_random_enabled)
        self.assertEqual(request.sentence_pause_min_ms, 250)
        self.assertEqual(request.sentence_pause_max_ms, 390)
        self.assertEqual(request.comma_pause_ms, 88)
        self.assertEqual(request.clause_pause_ms, 177)
        self.assertEqual(request.ellipsis_pause_ms, 444)
        self.assertEqual(request.chunk_pause_ms, 111)

    def test_old_sentence_pause_migrates_to_chunk_pause(self) -> None:
        settings = GenerationSettings.from_preferences({"sentence_pause_ms": 350})
        self.assertEqual(settings.sentence_pause_ms, 350)
        self.assertEqual(settings.chunk_pause_ms, 350)


if __name__ == "__main__":
    unittest.main()
