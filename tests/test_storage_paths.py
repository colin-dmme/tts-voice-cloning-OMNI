from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from omni_tts_core.model_registry import ModelRegistry, ModelSpec
from omni_tts_core.model_storage import ModelStorage
from omni_tts_core.storage_paths import hf_repo_cache_dirs, resolve_model_path
from omni_tts_shared.schemas import ModelCapabilities


class _Registry:
    def __init__(self, spec: ModelSpec) -> None:
        self.spec = spec

    def all(self) -> list[ModelSpec]:
        return [self.spec]

    def get(self, model_id: str) -> ModelSpec:
        if model_id != self.spec.model_id:
            raise KeyError(model_id)
        return self.spec


class StoragePathsTest(unittest.TestCase):
    def test_models_root_env_redirects_catalog_model_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            model_root = Path(temp) / "model-store"
            env = {"COLIN_TTS_MODELS_ROOT": str(model_root)}
            with patch.dict(os.environ, env, clear=False):
                path = resolve_model_path("models/omnivoice/demo")
                self.assertEqual(path, (model_root / "omnivoice" / "demo").resolve())

                spec = ModelRegistry().get("omnivoice_vietnamese")
                self.assertTrue(str(spec.local_path).startswith(str(model_root.resolve())))

    def test_storage_local_config_redirects_model_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            config = root / "storage.local.yaml"
            model_root = root / "models-on-d"
            config.write_text(
                "storage:\n"
                f"  models_root: \"{model_root.as_posix()}\"\n",
                encoding="utf-8",
            )
            env = {"COLIN_TTS_STORAGE_CONFIG": str(config)}
            with patch.dict(os.environ, env, clear=False):
                self.assertEqual(
                    resolve_model_path("models/qwen/demo"),
                    (model_root / "qwen" / "demo").resolve(),
                )

    def test_worker_model_remove_deletes_cache_without_touching_worker_venv(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            hf_cache = root / "hf-cache"
            worker_venv = root / "engines" / "vieneu_worker" / ".venv"
            worker_venv.mkdir(parents=True)
            (worker_venv / "keep.txt").write_text("worker", encoding="utf-8")

            env = {"COLIN_TTS_HF_CACHE_ROOT": str(hf_cache)}
            with patch.dict(os.environ, env, clear=False):
                cache_dir = hf_repo_cache_dirs("owner/model")[0]
                snapshot = cache_dir / "snapshots" / "abc"
                snapshot.mkdir(parents=True)
                (snapshot / "model.bin").write_bytes(b"model")

                spec = ModelSpec(
                    model_id="vieneu_test",
                    display_name="VieNeu Test",
                    provider="vieneu",
                    model_type="tts",
                    local_path=worker_venv,
                    hf_repo="owner/model",
                    language_priority="vi",
                    capabilities=ModelCapabilities(),
                )
                storage = ModelStorage(_Registry(spec))
                storage.remove("vieneu_test")

                self.assertTrue(worker_venv.exists())
                self.assertFalse(cache_dir.exists())


if __name__ == "__main__":
    unittest.main()
