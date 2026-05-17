from __future__ import annotations

"""
Mode 'pytorch': load full float PyTorch weights (model.safetensors) thay vì GGUF.
Dành cho pnnbao-ump/VieNeu-TTS (0.6B) và pnnbao-ump/VieNeu-TTS-0.3B.
Voice selection tương tự standard mode.
"""

from typing import Any

from worker_utils import (
    STANDARD_CLONE_CODEC_DEVICE,
    STANDARD_CLONE_CODEC_REPO,
    infer_kwargs,
    run_generic_batch,
    vieneu_kwargs,
)


def create_pytorch_tts(vieneu_factory: Any, payload: dict) -> Any:
    # gguf_filename=None bắt buộc: VieNeuTTS default là "VieNeu-TTS-v2-Q4-K-M.gguf",
    # phải override tường minh để load PyTorch weights thay vì GGUF.
    kwargs: dict = {"emotion": payload.get("emotion", "natural"), "gguf_filename": None}
    kwargs.update(vieneu_kwargs(payload, ["backbone_repo", "codec_repo", "codec_device", "backbone_device"]))
    if payload.get("ref_audio"):
        kwargs.update({
            "codec_repo": payload.get("codec_repo") or STANDARD_CLONE_CODEC_REPO,
            "codec_device": payload.get("codec_device") or STANDARD_CLONE_CODEC_DEVICE,
            "backbone_device": payload.get("backbone_device") or "cpu",
        })
    return vieneu_factory(**kwargs)


def run_pytorch(tts: Any, payload: dict) -> Any:
    text = payload["text"]
    ref_audio = payload.get("ref_audio")
    ref_text = payload.get("ref_text")
    voice_name = payload.get("voice_name")

    if ref_audio:
        try:
            return tts.infer(text=text, ref_audio=ref_audio, ref_text=ref_text, **infer_kwargs(payload))
        except AttributeError as exc:
            if "encode_code" not in str(exc):
                raise
            raise RuntimeError(
                "VieNeu PyTorch mode cần neucodec để clone giọng. "
                "Hãy chạy install_vieneu_worker.bat."
            ) from exc

    if voice_name:
        voice = tts.get_preset_voice(voice_name)
        return tts.infer(text=text, voice=voice, **infer_kwargs(payload))

    return tts.infer(text=text, **infer_kwargs(payload))


def run_pytorch_batch(tts: Any, chunks: list[dict], base_payload: dict) -> None:
    run_generic_batch(tts, chunks, base_payload, run_pytorch)
