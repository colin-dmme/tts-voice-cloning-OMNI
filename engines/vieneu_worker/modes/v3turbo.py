from __future__ import annotations

from pathlib import Path
from typing import Any

from worker_utils import infer_kwargs, vieneu_kwargs


def create_v3_turbo_tts(vieneu_factory: Any, payload: dict) -> Any:
    kwargs = vieneu_kwargs(
        payload,
        [
            "backbone_repo",
            "model_subfolder",
            "moss_tokenizer",
            "device",
            "backend",
            "precision",
            "onnx_subfolder",
            "threads",
            "max_batch_size",
        ],
    )
    return vieneu_factory(mode="v3turbo", **kwargs)


def run_v3_turbo(tts: Any, payload: dict) -> Any:
    kwargs = _voice_kwargs(payload)
    kwargs.update(infer_kwargs(payload))
    if payload.get("style"):
        kwargs["style"] = payload["style"]
    return tts.infer(text=payload["text"], **kwargs)


def run_v3_turbo_batch(tts: Any, chunks: list[dict], base_payload: dict) -> None:
    kwargs = _voice_kwargs(base_payload)
    kwargs.update(infer_kwargs(base_payload))
    if base_payload.get("style"):
        kwargs["style"] = base_payload["style"]
    audio_items = tts.infer_batch(
        [str(chunk["text"]) for chunk in chunks],
        **kwargs,
    )
    if len(audio_items) != len(chunks):
        raise RuntimeError("VieNeu v3 Turbo trả về số audio không khớp batch.")
    for chunk, audio in zip(chunks, audio_items):
        output_path = Path(chunk["output_path"])
        output_path.parent.mkdir(parents=True, exist_ok=True)
        tts.save(audio, str(output_path))


def _voice_kwargs(payload: dict) -> dict:
    if payload.get("ref_audio"):
        return {"ref_audio": payload["ref_audio"]}
    if payload.get("voice_name"):
        return {"voice": payload["voice_name"]}
    return {}
