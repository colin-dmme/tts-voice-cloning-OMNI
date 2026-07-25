from __future__ import annotations

import unittest

from omni_tts_core.model_registry import ModelRegistry, effective_voice_input


class PiperCatalogTest(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = ModelRegistry()
        self.piper_models = [
            spec for spec in self.registry.tts_models() if spec.provider == "piper"
        ]

    def test_extra_piper_catalog_is_merged(self) -> None:
        ids = {spec.model_id for spec in self.piper_models}

        self.assertEqual(len(self.piper_models), 33)
        self.assertIn("piper_ngoc_huyen", ids)
        self.assertIn("piper_ngoc_huyen_new", ids)
        self.assertIn("piper_mai_linh_250626", ids)
        self.assertIn("piper_vais1000_medium", ids)
        self.assertIn("piper_25hours_single_low", ids)
        self.assertIn("piper_pretrained_vi_female", ids)
        self.assertIn("piper_my_tam_v1", ids)
        self.assertIn("piper_my_tam_2794", ids)
        self.assertIn("piper_duy_oryx_3175", ids)
        self.assertIn("piper_viet_thao_3886", ids)
        self.assertIn("piper_adam_1", ids)
        self.assertIn("piper_yan_new", ids)
        self.assertIn("piper_vivos_x_low", ids)

    def test_every_piper_voice_is_fixed_and_downloads_only_two_files(self) -> None:
        for spec in self.piper_models:
            with self.subTest(model_id=spec.model_id):
                voice_input = effective_voice_input(spec)
                self.assertEqual(voice_input.modes, ["fixed"])
                self.assertEqual(voice_input.default_mode, "fixed")
                self.assertFalse(spec.capabilities.supports_voice_profile)
                self.assertEqual(len(spec.runtime["download_allow_patterns"]), 2)

    def test_model_artifacts_are_not_duplicated_under_different_names(self) -> None:
        artifacts = [
            (spec.hf_repo, str(spec.runtime["model_file"]))
            for spec in self.piper_models
        ]

        self.assertEqual(len(artifacts), len(set(artifacts)))

    def test_ngoc_huyen_variants_use_different_weight_files(self) -> None:
        original = self.registry.get("piper_ngoc_huyen")
        newer = self.registry.get("piper_ngoc_huyen_new")

        self.assertNotEqual(
            (original.hf_repo, original.runtime["model_file"]),
            (newer.hf_repo, newer.runtime["model_file"]),
        )
        self.assertIn("v1", original.display_name)
        self.assertIn("NEW", newer.display_name)

    def test_adam_voice_has_verified_artifact_identity(self) -> None:
        adam = self.registry.get("piper_adam_1")

        self.assertEqual(adam.runtime["model_file"], "piper-tts/adam1.onnx")
        self.assertEqual(
            adam.runtime["model_sha256"],
            "90e73d171447825fa8442fea8bf39c54bcfb206958f05170361e0fa3ba5c48eb",
        )
        self.assertIn("nam viral", adam.display_name.lower())
        self.assertFalse(adam.capabilities.supports_voice_profile)

    def test_vivos_exposes_all_embedded_speakers(self) -> None:
        vivos = self.registry.get("piper_vivos_x_low")

        self.assertTrue(vivos.capabilities.supports_voice_presets)
        self.assertEqual(len(vivos.voice_presets), 65)
        self.assertEqual(vivos.voice_presets["0"], "VIVOSSPK13")
        self.assertEqual(vivos.voice_presets["64"], "VIVOSDEV19")
        self.assertEqual(vivos.default_voice_preset, "0")


if __name__ == "__main__":
    unittest.main()
