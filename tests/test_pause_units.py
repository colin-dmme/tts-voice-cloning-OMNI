from __future__ import annotations

import unittest

from omni_tts_core.ui_presenters import pause_units


class PauseUnitsTest(unittest.TestCase):
    def test_standard_defaults_are_presented_in_seconds(self) -> None:
        expected = {
            "sentence_pause_ms": 0.32,
            "comma_pause_ms": 0.09,
            "clause_pause_ms": 0.18,
            "ellipsis_pause_ms": 0.45,
            "chunk_pause_ms": 0.12,
            "paragraph_pause_ms": 0.60,
            "paragraph_pause_min_ms": 0.50,
            "paragraph_pause_max_ms": 0.70,
            "sentence_pause_min_ms": 0.26,
            "sentence_pause_max_ms": 0.38,
        }

        self.assertEqual(
            {field: pause_units.default_seconds(field) for field in expected},
            expected,
        )

    def test_millisecond_preferences_round_trip_without_precision_loss(self) -> None:
        for milliseconds in (0, 90, 321, 600, 3000):
            seconds = pause_units.milliseconds_to_seconds(milliseconds)
            self.assertEqual(
                pause_units.seconds_to_milliseconds(seconds), milliseconds
            )

    def test_seconds_limits_are_scaled_from_the_request_schema(self) -> None:
        punctuation = pause_units.seconds_limit("sentence_pause_ms")
        paragraph = pause_units.seconds_limit("paragraph_pause_ms")

        self.assertEqual((punctuation.minimum, punctuation.maximum), (0.0, 3.0))
        self.assertEqual(punctuation.step, 0.05)
        self.assertEqual((paragraph.minimum, paragraph.maximum), (0.0, 10.0))

    def test_non_pause_field_is_rejected(self) -> None:
        with self.assertRaises(KeyError):
            pause_units.seconds_limit("speed")


if __name__ == "__main__":
    unittest.main()
