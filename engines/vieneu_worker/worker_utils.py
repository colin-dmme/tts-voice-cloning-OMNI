from __future__ import annotations

from pathlib import Path
from typing import Any, Callable


STANDARD_CLONE_CODEC_REPO = "neuphonic/distill-neucodec"
STANDARD_CLONE_CODEC_DEVICE = "cpu"


def vieneu_kwargs(payload: dict, keys: list[str]) -> dict[str, Any]:
    return {key: payload[key] for key in keys if payload.get(key)}


def infer_kwargs(payload: dict) -> dict[str, Any]:
    kwargs: dict[str, Any] = {}
    if payload.get("temperature") is not None:
        kwargs["temperature"] = float(payload["temperature"])
    if payload.get("top_k") is not None:
        kwargs["top_k"] = int(payload["top_k"])
    if payload.get("disable_emotion_tag"):
        kwargs["emotion_tag"] = None
    return kwargs


def apply_runtime_overrides(tts: Any, payload: dict) -> None:
    if payload.get("legacy_chat_format") and hasattr(tts, "use_chat_format"):
        tts.use_chat_format = True


def flatten_codes(codes: Any) -> Any:
    try:
        import torch
        if isinstance(codes, torch.Tensor):
            return codes.detach().cpu().numpy().reshape(-1)
    except Exception:
        pass
    import numpy as np
    return np.asarray(codes).reshape(-1)


def run_generic_batch(
    tts: Any,
    chunks: list[dict],
    base_payload: dict,
    synthesize_fn: Callable[[Any, dict], Any],
) -> None:
    for chunk in chunks:
        out = Path(chunk["output_path"])
        out.parent.mkdir(parents=True, exist_ok=True)
        chunk_payload = {**base_payload, "text": chunk["text"], "output_path": chunk["output_path"]}
        audio = synthesize_fn(tts, chunk_payload)
        tts.save(audio, str(out))
