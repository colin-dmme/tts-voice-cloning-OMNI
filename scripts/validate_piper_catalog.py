from __future__ import annotations

import argparse
import os
import tempfile
import time
from pathlib import Path

from omni_tts_core.engines.base import TtsEngineRequest
from omni_tts_core.engines.piper_engine import PiperSubprocessEngine
from omni_tts_core.model_registry import ModelRegistry
from omni_tts_core.model_storage import ModelStorage


REPRESENTATIVE_MODELS = (
    "piper_viet_thao_3886",
    "piper_vais1000_medium",
    "piper_pretrained_vi_female",
    "piper_vivos_x_low",
)
VALIDATION_TEXT = (
    "Xin chào, đây là bài kiểm tra tải model, sinh giọng nói, gỡ model "
    "và tải lại bằng catalog Piper tiếng Việt."
)


def main() -> None:
    args = _parse_args()
    model_ids = tuple(args.models or REPRESENTATIVE_MODELS)
    previous_models_root = os.environ.get("COLIN_TTS_MODELS_ROOT")
    previous_cache_root = os.environ.get("COLIN_TTS_HF_CACHE_ROOT")
    try:
        with tempfile.TemporaryDirectory(prefix="omni-piper-validation-") as temp_dir:
            root = Path(temp_dir).resolve()
            models_root = root / "models"
            os.environ["COLIN_TTS_MODELS_ROOT"] = str(models_root)
            os.environ["COLIN_TTS_HF_CACHE_ROOT"] = str(root / "hf-cache")
            registry = ModelRegistry()
            storage = ModelStorage(registry)

            for model_id in model_ids:
                status = storage.download(model_id)
                spec = registry.get(model_id)
                _assert_under(spec.local_path, models_root)
                speaker_id = (
                    max(spec.voice_presets, key=int)
                    if len(spec.voice_presets) > 1
                    else spec.default_voice_preset
                )
                request = TtsEngineRequest(
                    text=VALIDATION_TEXT,
                    language="vi",
                    reference_audio_path=None,
                    reference_text=None,
                    speaker_id=speaker_id,
                    speed=1.0,
                    pitch_shift=0.0,
                )
                started = time.perf_counter()
                result = PiperSubprocessEngine(spec).generate(request)
                elapsed = time.perf_counter() - started
                duration = len(result.audio) / result.sample_rate
                print(
                    f"{model_id}: installed={status.installed}, "
                    f"speaker_id={speaker_id}, "
                    f"sample_rate={result.sample_rate}, duration={duration:.3f}s, "
                    f"elapsed={elapsed:.3f}s"
                )

            lifecycle_id = model_ids[0]
            lifecycle_path = registry.get(lifecycle_id).local_path
            preview = storage.removal_preview(lifecycle_id)
            if "tải lại" not in preview or "xóa vĩnh viễn" not in preview:
                raise RuntimeError(f"Thông báo gỡ Piper chưa đúng: {preview}")
            storage.remove(lifecycle_id)
            if lifecycle_path.exists():
                raise RuntimeError(f"Gỡ Piper chưa xóa package: {lifecycle_path}")
            restored = storage.download(lifecycle_id)
            if not restored.installed:
                raise RuntimeError(f"Không tải lại được {lifecycle_id}")
            print(f"{lifecycle_id}: remove=True, redownload=True")
            print(f"temporary_root_cleaned_on_exit={root}")
    finally:
        _restore_env("COLIN_TTS_MODELS_ROOT", previous_models_root)
        _restore_env("COLIN_TTS_HF_CACHE_ROOT", previous_cache_root)


def _assert_under(path: Path, root: Path) -> None:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError as exc:
        raise RuntimeError(f"Model test nằm ngoài thư mục tạm: {path}") from exc


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Kiểm tra tải, sinh audio, gỡ và tải lại package Piper."
    )
    parser.add_argument("models", nargs="*", help="Model ID; bỏ trống để test bốn nguồn mẫu.")
    return parser.parse_args()


def _restore_env(name: str, value: str | None) -> None:
    if value is None:
        os.environ.pop(name, None)
    else:
        os.environ[name] = value


if __name__ == "__main__":
    main()
