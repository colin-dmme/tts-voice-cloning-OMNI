from __future__ import annotations

import pickle
from pathlib import Path
from typing import Any

import numpy as np

from worker_utils import infer_kwargs, vieneu_kwargs


def create_turbo_tts(vieneu_factory: Any, payload: dict) -> Any:
    kwargs = vieneu_kwargs(payload, [
        "backbone_repo", "backbone_filename",
        "decoder_repo", "decoder_filename",
        "encoder_repo", "encoder_filename",
        "device",
    ])
    return vieneu_factory(mode="turbo", **kwargs)


def run_turbo(tts: Any, payload: dict) -> Any:
    text = payload["text"]
    ref_audio = payload.get("ref_audio")
    voice_name = payload.get("voice_name")

    if ref_audio:
        voice = _load_or_encode_reference(tts, ref_audio, payload.get("cached_prompt_path"))
        return tts.infer(text=text, voice=voice, **infer_kwargs(payload))

    if voice_name:
        voice = tts.get_preset_voice(voice_name)
        return tts.infer(text=text, voice=voice, **infer_kwargs(payload))

    return tts.infer(text=text, **infer_kwargs(payload))


def run_turbo_batch(tts: Any, chunks: list[dict], base_payload: dict) -> None:
    ref_audio = base_payload.get("ref_audio")
    if ref_audio:
        # Encode reference audio once; reused across all chunks
        ref_voice = _load_or_encode_reference(tts, ref_audio, base_payload.get("cached_prompt_path"))
    else:
        ref_voice = None

    for chunk in chunks:
        out = Path(chunk["output_path"])
        out.parent.mkdir(parents=True, exist_ok=True)
        if ref_voice is not None:
            audio = tts.infer(text=chunk["text"], voice=ref_voice, **infer_kwargs(base_payload))
        else:
            chunk_payload = {**base_payload, "text": chunk["text"]}
            audio = run_turbo(tts, chunk_payload)
        tts.save(audio, str(out))


def _load_or_encode_reference(tts: Any, ref_audio: str, cached_prompt_path: str | None) -> Any:
    """
    Load persisted ref_codes from cache, or encode and save for future calls.
    Falls back to plain encode_reference if cache path is absent or errors occur.
    """
    if cached_prompt_path:
        cache_dir = Path(cached_prompt_path)
        npy_path = cache_dir / "ref_codes.npy"
        pkl_path = cache_dir / "ref_codes.pkl"

        # Try npy first, then pkl
        for asset_path, loader in ((npy_path, _load_npy), (pkl_path, _load_pkl)):
            if asset_path.exists():
                result = loader(asset_path)
                if result is not None:
                    return result

    voice = tts.encode_reference(ref_audio)

    if cached_prompt_path:
        cache_dir = Path(cached_prompt_path)
        cache_dir.mkdir(parents=True, exist_ok=True)
        _try_save_voice(voice, cache_dir)

    return voice


def _load_npy(path: Path):
    try:
        return np.load(str(path), allow_pickle=True).item()
    except Exception:
        try:
            return np.load(str(path), allow_pickle=False)
        except Exception:
            return None


def _load_pkl(path: Path):
    try:
        with path.open("rb") as f:
            return pickle.load(f)
    except Exception:
        return None


def _try_save_voice(voice: Any, cache_dir: Path) -> None:
    # Try numpy first (preferred for arrays), fall back to pickle
    npy_path = cache_dir / "ref_codes.npy"
    try:
        if isinstance(voice, np.ndarray):
            np.save(str(npy_path), voice)
            return
        # dict of arrays (common in VieNeu)
        if isinstance(voice, dict):
            np.save(str(npy_path), voice)
            return
    except Exception:
        pass
    try:
        with (cache_dir / "ref_codes.pkl").open("wb") as f:
            pickle.dump(voice, f)
    except Exception:
        pass
