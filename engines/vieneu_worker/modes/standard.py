from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from worker_utils import (
    STANDARD_CLONE_CODEC_REPO,
    STANDARD_CLONE_CODEC_DEVICE,
    flatten_codes,
    infer_kwargs,
    run_generic_batch,
    vieneu_kwargs,
)


def create_standard_tts(vieneu_factory: Any, payload: dict) -> Any:
    kwargs: dict = {"emotion": payload.get("emotion", "natural")}
    kwargs.update(vieneu_kwargs(payload, [
        "backbone_repo", "gguf_filename", "codec_repo", "codec_device", "backbone_device",
    ]))
    if payload.get("ref_audio"):
        kwargs.update({
            "codec_repo": (
                payload.get("clone_codec_repo")
                or payload.get("codec_repo")
                or STANDARD_CLONE_CODEC_REPO
            ),
            "codec_device": payload.get("clone_codec_device") or STANDARD_CLONE_CODEC_DEVICE,
            "backbone_device": payload.get("backbone_device") or "cpu",
        })
    return vieneu_factory(**kwargs)


def run_standard(tts: Any, payload: dict) -> Any:
    text = payload["text"]
    ref_audio = payload.get("ref_audio")
    ref_codes_path = payload.get("ref_codes_path")
    ref_text = payload.get("ref_text")
    voice_name = payload.get("voice_name")

    if payload.get("prompt_format") == "speech_token_gguf" and not ref_audio:
        return _run_speech_token_gguf(tts, payload)

    if ref_codes_path:
        ref_codes = np.load(str(Path(ref_codes_path)), allow_pickle=False)
        return tts.infer(text=text, ref_codes=ref_codes, ref_text=ref_text, **infer_kwargs(payload))

    if ref_audio:
        try:
            return tts.infer(text=text, ref_audio=ref_audio, ref_text=ref_text, **infer_kwargs(payload))
        except AttributeError as exc:
            if "encode_code" not in str(exc):
                raise
            raise RuntimeError(
                "VieNeu Standard cần backend codec có encode_code để clone giọng. "
                "Hãy chạy install_vieneu_worker.bat để cài neucodec."
            ) from exc

    if voice_name:
        voice = tts.get_preset_voice(voice_name)
        return tts.infer(text=text, voice=voice, **infer_kwargs(payload))

    return tts.infer(text=text, **infer_kwargs(payload))


def run_standard_batch(tts: Any, chunks: list[dict], base_payload: dict) -> None:
    run_generic_batch(tts, chunks, base_payload, run_standard)


def _run_speech_token_gguf(tts: Any, payload: dict) -> Any:
    from transformers import AutoTokenizer
    from vieneu_utils.phonemize_text import phonemize_with_dict

    speech_offset = int(payload.get("speech_offset") or 151671)
    speech_end = int(payload.get("speech_end") or 151670)
    speech_max = int(payload.get("speech_max") or 65535)
    repo = payload["backbone_repo"]

    voice = tts.get_preset_voice(payload.get("voice_name"))
    ref_codes = flatten_codes(voice["codes"])
    ref_text = voice.get("text", "")
    text = tts.normalizer.normalize(payload["text"])
    ref_phonemes = tts.get_ref_phonemes(ref_text)
    chunk_phonemes = phonemize_with_dict(text, skip_normalize=True)
    codes_str = "".join(f"<|speech_{int(code)}|>" for code in ref_codes)
    prompt = (
        "user: Convert the text to speech:"
        f"<|TEXT_PROMPT_START|>{ref_phonemes} {chunk_phonemes}<|TEXT_PROMPT_END|>\n"
        f"assistant:<|SPEECH_GENERATION_START|>{codes_str}"
    )
    tokenizer = AutoTokenizer.from_pretrained(repo)
    prompt_ids = tokenizer.encode(prompt, add_special_tokens=False)

    speech_ids: list[int] = []
    for token_id in tts.backbone.generate(prompt_ids, top_k=50, temp=1.0, reset=True):
        if token_id == speech_end and len(speech_ids) >= 50:
            break
        if speech_offset <= token_id <= speech_offset + speech_max:
            speech_ids.append(token_id)
        if len(speech_ids) >= 16000:
            break

    if not speech_ids:
        raise RuntimeError("Không nhận được speech token từ model GGUF audiobook.")

    decode_str = "".join(f"<|speech_{token_id - speech_offset}|>" for token_id in speech_ids)
    return tts._decode(decode_str)
