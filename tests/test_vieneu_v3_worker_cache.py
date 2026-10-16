from __future__ import annotations

import importlib.util
from pathlib import Path


def worker_module():
    spec = importlib.util.spec_from_file_location("v3_worker_test", Path(__file__).resolve().parents[1] / "engines/vieneu_v3_worker/synthesize.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeTts:
    def __init__(self, **kwargs):
        self.enrollments = []

    def encode_reference(self, path, denoise=True):
        self.enrollments.append((path, denoise))
        return [0.25], [[1, 2, 3]]


def test_reference_encoding_is_reused_but_denoise_setting_is_part_of_cache_key():
    module = worker_module()
    tts = FakeTts()
    payload = {"ref_audio": "sha.wav", "reference_cache_key": "a" * 64, "denoise_reference": True}
    first = module._infer_kwargs(payload, tts)
    second = module._infer_kwargs(payload, tts)
    assert first["voice"] is second["voice"]
    assert "ref_audio" not in second
    assert len(tts.enrollments) == 1
    module._infer_kwargs({**payload, "denoise_reference": False}, tts)
    assert len(tts.enrollments) == 2


def test_model_change_discards_cached_reference_embeddings():
    module = worker_module()
    tts = module._cached_tts(FakeTts, {"device": "cpu"})
    module._infer_kwargs({"ref_audio": "ref.wav", "reference_cache_key": "a" * 64}, tts)
    assert len(module._REFERENCE_CACHE) == 1
    module._cached_tts(FakeTts, {"device": "cuda"})
    assert len(module._REFERENCE_CACHE) == 0


def test_local_reference_path_without_cache_key_keeps_existing_behavior():
    module = worker_module()
    result = module._infer_kwargs({"ref_audio": "local.wav"}, FakeTts())
    assert result == {"ref_audio": "local.wav", "denoise": True}
