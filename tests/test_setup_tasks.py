from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from omni_tts_core.setup_tasks import SetupService


class SetupTasksTest(unittest.TestCase):
    def test_qwen_model_reports_worker_and_gpu_actions(self) -> None:
        service = SetupService()

        tasks = service.model_setup_statuses("qwen3_tts_06b_base")
        by_scope = {item.scope: item for item in tasks}

        self.assertIn("worker", by_scope)
        self.assertEqual(by_scope["worker"].script_name, "install_qwen_worker.bat")
        self.assertEqual(by_scope["worker"].action_label, "Cài worker")
        self.assertIn("gpu", by_scope)
        self.assertIn(by_scope["gpu"].script_name, {"install_qwen_worker.bat", "install_qwen_worker_blackwell.bat"})
        self.assertEqual(by_scope["gpu"].action_label, "Cài GPU/CUDA")

    def test_vieneu_cuda_variant_marks_gpu_as_required(self) -> None:
        service = SetupService()

        tasks = service.model_setup_statuses("vieneu_v2_turbo_cuda")
        gpu = next(item for item in tasks if item.scope == "gpu")

        self.assertTrue(gpu.required)
        self.assertEqual(gpu.script_name, "install_vieneu_worker_cuda.bat")

    def test_install_base_runtime_delegates_to_core_provider_action(self) -> None:
        service = SetupService()

        with patch("omni_tts_core.setup_tasks.install_base_runtime", return_value="ok") as install:
            message = service.install_base_for_model("f5tts_v1_base_swivid")

        self.assertEqual(message, "ok")
        install.assert_called_once_with("f5tts")


if __name__ == "__main__":
    unittest.main()
