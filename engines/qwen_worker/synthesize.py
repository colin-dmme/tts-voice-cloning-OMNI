from __future__ import annotations

import argparse
import json
import os
import pickle
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
        if payload.get("batch"):
            _run_batch(payload)
        else:
            _run_single(payload)
    except Exception as exc:
        raise SystemExit(f"Qwen worker loi: {exc}") from exc


def _run_single(payload: dict) -> None:
    output_path = Path(payload["output_path"])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    audio, sample_rate = synthesize(payload)
    import soundfile as sf
    sf.write(str(output_path), audio, sample_rate)


def _run_batch(payload: dict) -> None:
    import soundfile as sf
    from qwen_tts import Qwen3TTSModel

    model_path = payload.get("model_path") or payload["hf_repo"]
    device_map = payload.get("device_map") or _device_map()
    dtype = _dtype(device_map)
    model_kwargs: dict = {"device_map": device_map, "dtype": dtype}
    if device_map != "cpu":
        model_kwargs["attn_implementation"] = payload.get("attn_implementation") or "sdpa"

    model = Qwen3TTSModel.from_pretrained(model_path, **model_kwargs)
    language = _language_name(payload.get("language"))
    ref_audio = payload.get("ref_audio")
    ref_text = payload.get("ref_text") or ""

    if not ref_audio:
        raise RuntimeError(
            "Qwen3-TTS Base trong app nay uu tien clone voice. Hay chon Profile giong truoc khi tao audio."
        )

    voice_prompt = _load_or_build_voice_prompt(model, payload, ref_audio, ref_text)

    for chunk in payload["chunks"]:
        out = Path(chunk["output_path"])
        out.parent.mkdir(parents=True, exist_ok=True)
        if voice_prompt is not None:
            wavs, sample_rate = model.generate_voice_clone(
                text=chunk["text"],
                language=language,
                voice_clone_prompt=voice_prompt,
            )
        else:
            wavs, sample_rate = model.generate_voice_clone(
                text=chunk["text"],
                language=language,
                ref_audio=ref_audio,
                ref_text=ref_text,
            )
        sf.write(str(out), wavs[0], int(sample_rate))


def synthesize(payload: dict):
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
    ref_text = payload.get("ref_text") or ""

    if not ref_audio:
        raise RuntimeError(
            "Qwen3-TTS Base trong app nay uu tien clone voice. Hay chon Profile giong truoc khi tao audio."
        )

    voice_prompt = _load_or_build_voice_prompt(model, payload, ref_audio, ref_text)
    if voice_prompt is not None:
        wavs, sample_rate = model.generate_voice_clone(
            text=text,
            language=language,
            voice_clone_prompt=voice_prompt,
        )
    else:
        wavs, sample_rate = model.generate_voice_clone(
            text=text,
            language=language,
            ref_audio=ref_audio,
            ref_text=ref_text,
        )
    return wavs[0], int(sample_rate)


def _load_or_build_voice_prompt(model, payload: dict, ref_audio: str, ref_text: str):
    """
    Try to load from cached pkl, or create via create_voice_clone_prompt and save.
    Returns None if API is unavailable; caller falls back to ref_audio + ref_text.
    """
    if not hasattr(model, "create_voice_clone_prompt"):
        return None

    cached_path = payload.get("cached_prompt_path")
    if cached_path:
        pkl_path = Path(cached_path) / "voice_clone_prompt.pkl"
        if pkl_path.exists():
            try:
                with pkl_path.open("rb") as f:
                    return pickle.load(f)
            except Exception:
                pkl_path.unlink(missing_ok=True)

    try:
        prompt = model.create_voice_clone_prompt(ref_audio, ref_text)
    except Exception:
        return None

    if cached_path:
        try:
            pkl_dir = Path(cached_path)
            pkl_dir.mkdir(parents=True, exist_ok=True)
            with (pkl_dir / "voice_clone_prompt.pkl").open("wb") as f:
                pickle.dump(prompt, f)
        except Exception:
            pass

    return prompt


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
    if device_map.startswith("cuda") and not torch.cuda.is_available():
        raise RuntimeError("CUDA được yêu cầu nhưng Qwen worker không thấy torch.cuda.")
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
