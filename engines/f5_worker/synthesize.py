from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    try:
        args = parse_args()
        payload = json.loads(args.request.read_text(encoding="utf-8-sig"))
        if payload.get("batch"):
            _run_batch(payload)
        else:
            _run_single(payload)
    except Exception as exc:
        raise SystemExit(f"F5-TTS worker loi: {exc}") from exc


def _run_single(payload: dict) -> None:
    output_path = Path(payload["output_path"])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    model = _load_model(payload)
    _infer_to_file(model, payload, payload["text"], output_path)


def _run_batch(payload: dict) -> None:
    model = _load_model(payload)
    for chunk in payload["chunks"]:
        output_path = Path(chunk["output_path"])
        output_path.parent.mkdir(parents=True, exist_ok=True)
        _infer_to_file(model, payload, chunk["text"], output_path)


def _load_model(payload: dict):
    from f5_tts.api import F5TTS

    kwargs = {
        "model": payload.get("f5_model") or "F5TTS_v1_Base",
        "ode_method": payload.get("ode_method") or "euler",
        "use_ema": bool(payload.get("use_ema", True)),
        "hf_cache_dir": payload.get("hf_cache_dir") or None,
    }
    for key in ("ckpt_file", "vocab_file", "device"):
        if payload.get(key):
            kwargs[key] = payload[key]
    return F5TTS(**kwargs)


def _infer_to_file(model, payload: dict, text: str, output_path: Path) -> None:
    ref_audio = payload.get("ref_audio")
    ref_text = payload.get("ref_text") or ""
    if not ref_audio:
        raise RuntimeError("F5-TTS cần Profile giọng để clone voice.")
    if not ref_text.strip():
        raise RuntimeError("F5-TTS cần transcript của giọng mẫu để clone voice ổn định.")

    kwargs = {
        "ref_file": ref_audio,
        "ref_text": ref_text,
        "gen_text": text,
        "file_wave": str(output_path),
        "speed": float(payload.get("speed") or 1.0),
        "nfe_step": int(payload.get("nfe_step") or 32),
        "cfg_strength": float(payload.get("cfg_strength") or 2.0),
        "sway_sampling_coef": float(payload.get("sway_sampling_coef") or -1.0),
        "cross_fade_duration": float(payload.get("cross_fade_duration") or 0.15),
        "target_rms": float(payload.get("target_rms") or 0.1),
        "remove_silence": bool(payload.get("remove_silence", False)),
        "progress": None,
        "show_info": lambda *_args, **_kwargs: None,
    }
    if payload.get("seed") is not None:
        kwargs["seed"] = int(payload["seed"])
    if payload.get("fix_duration") is not None:
        kwargs["fix_duration"] = float(payload["fix_duration"])

    wav, sample_rate, _spectrogram = model.infer(**kwargs)
    if not output_path.exists():
        import soundfile as sf

        sf.write(str(output_path), wav, int(sample_rate))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", type=Path, required=True)
    return parser.parse_args()


if __name__ == "__main__":
    main()
