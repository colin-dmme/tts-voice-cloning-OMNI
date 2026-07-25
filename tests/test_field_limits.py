from __future__ import annotations

import unittest

from omni_tts_core.ui_presenters import field_limits
from omni_tts_shared.schemas import GenerateSpeechRequest

# Every numeric control a GUI binds to a request field. If a GUI ever invents a
# range of its own again, the round-trip test below is what catches it.
BOUND_FIELDS = (
    "speed",
    "pitch_shift",
    "sentence_pause_ms",
    "paragraph_pause_ms",
    "max_chunk_chars",
    "temperature",
    "top_k",
    "f5_nfe_step",
    "f5_cfg_strength",
    "f5_sway_sampling_coef",
    "f5_cross_fade_duration",
    "f5_target_rms",
    "f5_fix_duration",
    "f5_seed",
    "chatterbox_temperature",
    "chatterbox_top_p",
    "chatterbox_top_k",
    "chatterbox_repetition_penalty",
    "chatterbox_seed",
    "gpu_start_temperature_c",
    "gpu_abort_temperature_c",
    "gpu_abort_temperature_sustain_seconds",
    "gpu_emergency_temperature_c",
    "gpu_cooldown_max_wait_seconds",
    "gpu_resume_temperature_c",
    "gpu_minimum_free_vram_mb",
    "gpu_runtime_minimum_free_vram_mb",
    "gpu_maximum_utilization_percent",
    "gpu_maximum_encoder_utilization_percent",
)


class BoundsTest(unittest.TestCase):
    def test_every_bound_field_has_real_limits(self) -> None:
        for field in BOUND_FIELDS:
            with self.subTest(field=field):
                limit = field_limits.limit(field)
                self.assertLess(limit.minimum, limit.maximum)
                self.assertGreater(limit.step, 0)

    def test_limits_match_the_request_schema(self) -> None:
        for field in BOUND_FIELDS:
            info = GenerateSpeechRequest.model_fields[field]
            expected = {}
            for constraint in info.metadata:
                if hasattr(constraint, "ge"):
                    expected["ge"] = float(constraint.ge)
                if hasattr(constraint, "le"):
                    expected["le"] = float(constraint.le)
            limit = field_limits.limit(field)
            with self.subTest(field=field):
                if "ge" in expected:
                    self.assertEqual(limit.minimum, expected["ge"])
                if "le" in expected:
                    self.assertEqual(limit.maximum, expected["le"])

    def test_extreme_widget_values_still_build_a_valid_request(self) -> None:
        """The whole point: a value taken from the edge of a widget range must
        never be rejected by the request model."""
        for field in BOUND_FIELDS:
            limit = field_limits.limit(field)
            for raw in (limit.widget_minimum, limit.maximum):
                value = limit.to_request_value(raw)
                with self.subTest(field=field, value=value):
                    GenerateSpeechRequest(text="xin chào", **{field: value})


class SentinelTest(unittest.TestCase):
    def test_seed_sentinel_is_below_the_schema_minimum(self) -> None:
        limit = field_limits.limit("f5_seed")
        self.assertEqual(limit.minimum, 0)
        self.assertEqual(limit.widget_minimum, -1)

    def test_sentinel_becomes_none_in_the_request(self) -> None:
        limit = field_limits.limit("chatterbox_seed")
        self.assertIsNone(limit.to_request_value(-1))
        self.assertEqual(limit.to_request_value(7), 7)

    def test_plain_field_has_no_sentinel(self) -> None:
        self.assertIsNone(field_limits.limit("top_k").sentinel)


class ClampTest(unittest.TestCase):
    def test_stored_value_outside_the_range_is_pulled_back(self) -> None:
        limit = field_limits.limit("top_k")
        self.assertEqual(limit.clamp(5000), 200)
        self.assertEqual(limit.clamp(0), 1)

    def test_integer_fields_report_no_decimals(self) -> None:
        self.assertTrue(field_limits.limit("top_k").is_integer)
        self.assertFalse(field_limits.limit("speed").is_integer)

    def test_ints_returns_widget_minimum(self) -> None:
        self.assertEqual(field_limits.limit("f5_seed").ints()[0], -1)

    def test_default_of_reads_the_schema_default(self) -> None:
        self.assertEqual(field_limits.default_of("sentence_pause_ms"), 320)
        self.assertIsNone(field_limits.default_of("top_k"))


if __name__ == "__main__":
    unittest.main()
