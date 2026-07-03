from __future__ import annotations

import argparse
import json
import random
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
        raise SystemExit(f"Chatterbox worker loi: {exc}") from exc


def _run_single(payload: dict) -> None:
    output_path = Path(payload["output_path"])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    model = _load_model(payload)
    _infer_to_file(model, payload, payload["text"], output_path)


def _run_batch(payload: dict) -> None:
    model = _load_model(payload)
    _prepare_conditionals(model, payload)
    seed = payload.get("seed")
    for index, chunk in enumerate(payload["chunks"]):
        output_path = Path(chunk["output_path"])
        output_path.parent.mkdir(parents=True, exist_ok=True)
        chunk_payload = dict(payload)
        if seed is not None:
            chunk_payload["seed"] = int(seed) + index
        _infer_to_file(model, chunk_payload, chunk["text"], output_path, conditionals_ready=True)


def _load_model(payload: dict):
    from chatterbox.tts_turbo import ChatterboxTurboTTS

    device = _device(payload)
    model_path = Path(str(payload.get("model_path") or ""))
    if model_path.exists() and any(model_path.iterdir()):
        return ChatterboxTurboTTS.from_local(model_path, device=device)
    return ChatterboxTurboTTS.from_pretrained(device=device)


def _infer_to_file(
    model,
    payload: dict,
    text: str,
    output_path: Path,
    *,
    conditionals_ready: bool = False,
) -> None:
    ref_audio = payload.get("ref_audio")
    if not ref_audio:
        raise RuntimeError("Chatterbox Turbo cần Profile giọng để clone voice.")

    _set_seed(payload.get("seed"))
    kwargs = {
        "text": text,
        "audio_prompt_path": None if conditionals_ready else ref_audio,
        "temperature": float(payload.get("temperature") or 0.8),
        "top_p": float(payload.get("top_p") or 0.95),
        "top_k": int(payload.get("top_k") or 1000),
        "repetition_penalty": float(payload.get("repetition_penalty") or 1.2),
        "norm_loudness": bool(payload.get("norm_loudness", True)),
    }
    wav = model.generate(**kwargs)
    _write_wav(output_path, wav, int(model.sr))


def _prepare_conditionals(model, payload: dict) -> None:
    ref_audio = payload.get("ref_audio")
    if not ref_audio:
        raise RuntimeError("Chatterbox Turbo cần Profile giọng để clone voice.")
    _set_seed(payload.get("seed"))
    model.prepare_conditionals(
        ref_audio,
        exaggeration=0.0,
        norm_loudness=bool(payload.get("norm_loudness", True)),
    )


def _write_wav(path: Path, wav, sample_rate: int) -> None:
    import soundfile as sf

    if hasattr(wav, "detach"):
        wav = wav.squeeze().detach().cpu().numpy()
    sf.write(str(path), wav, sample_rate)


def _set_seed(seed) -> None:
    if seed is None:
        return
    seed = int(seed)
    random.seed(seed)
    try:
        import numpy as np

        np.random.seed(seed % (2**32 - 1))
    except Exception:
        pass
    try:
        import torch

        torch.manual_seed(seed)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(seed)
    except Exception:
        pass


def _device(payload: dict) -> str:
    requested = str(payload.get("device") or "").strip().lower()
    if requested in {"cpu", "cuda"}:
        if requested == "cuda":
            _ensure_cuda()
        return requested
    try:
        import torch

        return "cuda" if torch.cuda.is_available() else "cpu"
    except Exception:
        return "cpu"


def _ensure_cuda() -> None:
    try:
        import torch
    except Exception as exc:
        raise RuntimeError("CUDA được yêu cầu nhưng Chatterbox worker thiếu torch.") from exc
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA được yêu cầu nhưng Chatterbox worker không thấy torch.cuda.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", type=Path, required=True)
    return parser.parse_args()


if __name__ == "__main__":
    main()
