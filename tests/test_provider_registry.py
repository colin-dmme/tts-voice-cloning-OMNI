from __future__ import annotations

import unittest
import tempfile
from pathlib import Path

from omni_tts_core.model_storage import _move_to_trash
from omni_tts_core.provider_registry import provider_descriptor


class ProviderRegistryTest(unittest.TestCase):
    def test_piper_is_a_folder_worker_provider(self) -> None:
        descriptor = provider_descriptor("piper")

        self.assertIsNotNone(descriptor)
        self.assertEqual(descriptor.worker_name, "piper_worker")
        self.assertEqual(descriptor.storage_mode, "folder")
        self.assertIn("speed", descriptor.controls)
        self.assertEqual(descriptor.max_parallel_jobs, 2)

    def test_hf_cache_policy_is_declared_by_provider(self) -> None:
        self.assertEqual(provider_descriptor("vieneu").storage_mode, "hf_cache")
        self.assertEqual(provider_descriptor("valtec").storage_mode, "hf_cache")
        self.assertEqual(provider_descriptor("omnivoice").storage_mode, "folder")

    def test_removal_moves_payload_to_recoverable_trash(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            payload = root / "models" / "voice"
            payload.mkdir(parents=True)
            (payload / "voice.onnx").write_bytes(b"model")

            destination = _move_to_trash(
                payload,
                root / "models" / ".trash",
                allowed_roots=[root / "models"],
                label="voice-id",
            )

            self.assertFalse(payload.exists())
            self.assertTrue((destination / "voice.onnx").exists())
            self.assertIn(".trash", destination.parts)


if __name__ == "__main__":
    unittest.main()
