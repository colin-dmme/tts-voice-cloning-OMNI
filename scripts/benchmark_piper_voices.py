from __future__ import annotations

import argparse
import time
from pathlib import Path

import soundfile as sf

from omni_tts_core.engines.base import TtsEngineRequest
from omni_tts_core.engines.piper_engine import PiperSubprocessEngine
from omni_tts_core.model_registry import ModelRegistry
from omni_tts_core.model_storage import ModelStorage
from omni_tts_core.paths import PROJECT_ROOT


DEFAULT_MODELS = ("piper_ngoc_huyen", "piper_ngoc_huyen_new")
DEFAULT_TEXT = (
    "Xin chào, đây là đoạn văn dùng để so sánh các giọng Piper tiếng Việt "
    "trên cùng một nội dung và cùng tốc độ."
)


def main() -> None:
    args = _parse_args()
    registry = ModelRegistry()
    storage = ModelStorage(registry)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    for pass_number in range(1, args.passes + 1):
        print(f"\nLượt {pass_number}/{args.passes}")
        for model_id in args.models:
            spec = registry.get(model_id)
            if spec.provider != "piper":
                raise SystemExit(f"{model_id} không phải model Piper.")
            if not storage.is_installed(spec):
                if not args.download:
                    print(f"- {model_id}: chưa tải (thêm --download để tải tự động)")
                    continue
                storage.download(model_id)

            request = TtsEngineRequest(
                text=args.text,
                language="vi",
                reference_audio_path=None,
                reference_text=None,
                speaker_id=spec.default_voice_preset,
                speed=args.speed,
                pitch_shift=0.0,
            )
            started = time.perf_counter()
            result = PiperSubprocessEngine(spec).generate(request)
            elapsed = time.perf_counter() - started
            duration = len(result.audio) / result.sample_rate
            output_path = output_dir / f"{model_id}-pass-{pass_number}.wav"
            sf.write(output_path, result.audio, result.sample_rate)
            print(
                f"- {model_id}: {elapsed:.3f}s / audio {duration:.3f}s "
                f"(RTF {elapsed / duration:.3f}) -> {output_path}"
            )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Sinh cùng một câu qua nhiều giọng Piper để nghe và đo A/B."
    )
    parser.add_argument("models", nargs="*", default=list(DEFAULT_MODELS))
    parser.add_argument("--text", default=DEFAULT_TEXT)
    parser.add_argument("--speed", type=float, default=1.0)
    parser.add_argument("--passes", type=int, default=2)
    parser.add_argument("--download", action="store_true")
    parser.add_argument(
        "--output-dir",
        default=str(PROJECT_ROOT / "outputs" / "piper_ab"),
    )
    return parser.parse_args()


if __name__ == "__main__":
    main()
