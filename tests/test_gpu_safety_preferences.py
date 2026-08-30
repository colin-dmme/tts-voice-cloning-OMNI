from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from colin_studio_tts_mcp.contracts import TextGenerationInput
from omni_tts_core.gpu_safety_preferences import GpuSafetyPreferences
from omni_tts_ui_qt.preferences import QtPreferences


class GpuSafetyPreferencesTests(unittest.TestCase):
    def test_loads_legacy_qt_values_before_shared_file_exists(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            legacy_path = root / "ui_qt.json"
            legacy_path.write_text(
                json.dumps(
                    {
                        "gpu_minimum_free_vram_mb": 500,
                        "gpu_runtime_minimum_free_vram_mb": 200,
                    }
                ),
                encoding="utf-8",
            )
            preferences = GpuSafetyPreferences(
                root / "gpu_safety.json", (legacy_path,)
            )

            values = preferences.load()

            self.assertEqual(values["gpu_minimum_free_vram_mb"], 500)
            self.assertEqual(values["gpu_runtime_minimum_free_vram_mb"], 200)

    def test_qt_save_creates_and_then_reads_shared_gpu_preferences(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            ui_path = Path(directory) / "ui_qt.json"
            preferences = QtPreferences(ui_path)
            data = preferences.load()
            data["gpu_minimum_free_vram_mb"] = 3456
            data["gpu_runtime_minimum_free_vram_mb"] = 456

            preferences.save(data)
            ui_path.write_text("{}", encoding="utf-8")
            loaded = preferences.load()

            self.assertTrue(ui_path.with_name("gpu_safety.json").exists())
            self.assertEqual(loaded["gpu_minimum_free_vram_mb"], 3456)
            self.assertEqual(loaded["gpu_runtime_minimum_free_vram_mb"], 456)

    def test_mcp_inherits_shared_gpu_preferences(self) -> None:
        request = TextGenerationInput(
            text="Xin chào", model_id="omnivoice_vietnamese"
        )

        settings = request.to_settings(
            {
                "gpu_minimum_free_vram_mb": 500,
                "gpu_runtime_minimum_free_vram_mb": 200,
            }
        )

        self.assertEqual(settings.gpu_minimum_free_vram_mb, 500)
        self.assertEqual(settings.gpu_runtime_minimum_free_vram_mb, 200)

    def test_explicit_mcp_gpu_override_wins(self) -> None:
        request = TextGenerationInput(
            text="Xin chào",
            model_id="omnivoice_vietnamese",
            generation={
                "advanced": {
                    "gpu_minimum_free_vram_mb": 4000,
                    "gpu_runtime_minimum_free_vram_mb": 512,
                }
            },
        )

        settings = request.to_settings(
            {
                "gpu_minimum_free_vram_mb": 500,
                "gpu_runtime_minimum_free_vram_mb": 200,
            }
        )

        self.assertEqual(settings.gpu_minimum_free_vram_mb, 4000)
        self.assertEqual(settings.gpu_runtime_minimum_free_vram_mb, 512)


if __name__ == "__main__":
    unittest.main()