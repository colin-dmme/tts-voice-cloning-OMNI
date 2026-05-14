from __future__ import annotations

import argparse
import json
import os
from pathlib import Path


LANGUAGE_MAP = {
    "en": "English",
    "zh": "Chinese",
    "ja": "Japanese",
    "ko": "Korean",
    "de": "German",
    "fr": "French",
    "ru": "Russian",
    "pt": "Portuguese",
    "es": "Spanish",
    "it": "Italian",
}


def main() -> None:
    try:
        args = parse_args()
        payload = json.loads(args.request.read_text(encoding="utf-8-sig"))
        output_path = Path(payload["output_path"])
        output_path.parent.mkdir(parents=True, exist_ok=True)

        audio, sample_rate = synthesize(payload)

        import soundfile as sf

        sf.write(str(output_path), audio, sample_rate)
    except Exception as exc:
        raise SystemExit(f"Qwen worker loi: {exc}") from exc


def synthesize(payload: dict):
    import torch
    from qwen_tts import Qwen3TTSModel

    model_path = payload.get("model_path") or payload["hf_repo"]
    device_map = payload.get("device_map") or _device_map()
    dtype = _dtype(device_map)
    model_kwargs = {
        "device_map": device_map,
        "dtype": dtype,
    }
    if device_map != "cpu":
        model_kwargs["attn_implementation"] = payload.get("attn_implementation") or "sdpa"

    model = Qwen3TTSModel.from_pretrained(model_path, **model_kwargs)
    language = _language_name(payload.get("language"))
    text = payload["text"]
    ref_audio = payload.get("ref_audio")
    ref_text = payload.get("ref_text")

    if ref_audio:
        wavs, sample_rate = model.generate_voice_clone(
            text=text,
            language=language,
            ref_audio=ref_audio,
            ref_text=ref_text or "",
        )
    else:
        raise RuntimeError(
            "Qwen3-TTS Base trong app nay uu tien clone voice. Hay chon Profile giong truoc khi tao audio."
        )
    return wavs[0], int(sample_rate)


def _device_map() -> str:
    try:
        import torch
    except Exception:
        return "cpu"
    if torch.cuda.is_available():
        return "cuda:0"
    return "cpu"


def _dtype(device_map: str):
    import torch

    if device_map == "cpu":
        return torch.float32
    major, _minor = torch.cuda.get_device_capability(0)
    if major >= 8:
        return torch.bfloat16
    return torch.float16


def _language_name(language: str | None) -> str:
    if not language:
        return "Auto"
    return LANGUAGE_MAP.get(language.lower(), "Auto")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", type=Path, required=True)
    return parser.parse_args()


if __name__ == "__main__":
    main()
