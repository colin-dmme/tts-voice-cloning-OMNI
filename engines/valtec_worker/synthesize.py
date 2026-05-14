from __future__ import annotations

import argparse
import inspect
import json
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable


DEFAULT_SPEAKER = "NF"
DEFAULT_SAMPLE_RATE = 24000
VENDOR_PATH = Path(__file__).parent / "vendor" / "valtec-tts"
if VENDOR_PATH.exists() and str(VENDOR_PATH) not in sys.path:
    sys.path.insert(0, str(VENDOR_PATH))


def main() -> None:
    try:
        args = parse_args()
        payload = json.loads(args.request.read_text(encoding="utf-8-sig"))
        output_path = Path(payload["output_path"])
        output_path.parent.mkdir(parents=True, exist_ok=True)

        synthesize(payload, output_path)
    except Exception as exc:
        raise SystemExit(f"Valtec worker loi: {exc}") from exc


def synthesize(payload: dict[str, Any], output_path: Path) -> None:
    ref_audio = _clean_text(payload.get("ref_audio"))
    if ref_audio:
        _clone_voice(payload, output_path, ref_audio)
        return
    _preset_voice(payload, output_path)


def _clone_voice(payload: dict[str, Any], output_path: Path, ref_audio: str) -> None:
    tts = _create_zeroshot_tts()
    prepared_ref = _prepare_reference_audio(ref_audio)
    clone_voice = getattr(tts, "clone_voice", None)
    if callable(clone_voice):
        _call_supported(
            clone_voice,
            text=payload["text"],
            reference_audio=prepared_ref,
            output_path=str(output_path),
            length_scale=payload.get("speed"),
        )
        if output_path.exists():
            return

    synthesize_fn = getattr(tts, "synthesize")
    result = _call_supported(
        synthesize_fn,
        text=payload["text"],
        reference_audio=prepared_ref,
        length_scale=payload.get("speed"),
    )
    _write_audio_result(result, output_path)


def _create_zeroshot_tts():
    from valtec_tts import ZeroShotTTS

    paths = _resolve_zeroshot_paths()
    if paths is not None:
        checkpoint_path, config_path = paths
        return ZeroShotTTS(
            checkpoint_path=str(checkpoint_path),
            config_path=str(config_path),
            device="cpu",
        )
    try:
        return ZeroShotTTS(device="cpu")
    except FileNotFoundError:
        paths = _resolve_zeroshot_paths()
        if paths is None:
            raise
        checkpoint_path, config_path = paths
        return ZeroShotTTS(
            checkpoint_path=str(checkpoint_path),
            config_path=str(config_path),
            device="cpu",
        )


def _resolve_zeroshot_paths() -> tuple[Path, Path] | None:
    import valtec_tts.zeroshot as zeroshot

    cache_dir = zeroshot._get_cache_dir()
    model_dir = cache_dir / zeroshot.DEFAULT_ZEROSHOT_MODEL_NAME
    candidates = [
        model_dir,
        model_dir / "pretrained" / "zeroshot",
        VENDOR_PATH / "pretrained" / "zeroshot",
    ]
    for candidate in candidates:
        config_path = candidate / "config.json"
        checkpoints = sorted(candidate.glob("G_*.pth"))
        if config_path.exists() and checkpoints:
            return checkpoints[-1], config_path
    return None


def _preset_voice(payload: dict[str, Any], output_path: Path) -> None:
    from valtec_tts import TTS

    tts = TTS(device="cpu")
    speaker = _clean_text(payload.get("speaker")) or DEFAULT_SPEAKER
    speak = getattr(tts, "speak", None)
    if callable(speak):
        _call_supported(
            speak,
            text=payload["text"],
            speaker=speaker,
            output_path=str(output_path),
            speed=payload.get("speed"),
        )
        if output_path.exists():
            return

    synthesize_fn = getattr(tts, "synthesize")
    result = _call_supported(
        synthesize_fn,
        text=payload["text"],
        speaker=speaker,
        speed=payload.get("speed"),
    )
    _write_audio_result(result, output_path)


def _prepare_reference_audio(audio_path: str) -> str:
    import librosa
    import soundfile as sf

    audio, _sample_rate = librosa.load(audio_path, sr=24000, mono=True)
    temp = tempfile.NamedTemporaryFile(prefix="valtec_ref_", suffix=".wav", delete=False)
    temp_path = temp.name
    temp.close()
    sf.write(temp_path, audio, 24000)
    return temp_path


def _call_supported(func: Callable[..., Any], **kwargs: Any) -> Any:
    signature = inspect.signature(func)
    accepts_kwargs = any(
        parameter.kind == inspect.Parameter.VAR_KEYWORD
        for parameter in signature.parameters.values()
    )
    if accepts_kwargs:
        filtered = {key: value for key, value in kwargs.items() if value is not None}
    else:
        filtered = {
            key: value
            for key, value in kwargs.items()
            if value is not None and key in signature.parameters
        }
    return func(**filtered)


def _write_audio_result(result: Any, output_path: Path) -> None:
    import numpy as np
    import soundfile as sf

    sample_rate = DEFAULT_SAMPLE_RATE
    audio = result
    if isinstance(result, tuple) and len(result) >= 2:
        audio, sample_rate = result[0], int(result[1])
    if hasattr(audio, "detach"):
        audio = audio.detach().cpu().numpy()
    audio_array = np.asarray(audio, dtype=np.float32)
    sf.write(str(output_path), audio_array, sample_rate)


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", type=Path, required=True)
    return parser.parse_args()


if __name__ == "__main__":
    main()
