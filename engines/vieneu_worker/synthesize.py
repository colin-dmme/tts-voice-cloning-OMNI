from __future__ import annotations

import argparse
import json
from pathlib import Path


STANDARD_CLONE_CODEC_REPO = "neuphonic/distill-neucodec"
STANDARD_CLONE_CODEC_DEVICE = "cpu"


def main() -> None:
    try:
        args = parse_args()
        payload = json.loads(args.request.read_text(encoding="utf-8-sig"))
        output_path = Path(payload["output_path"])
        output_path.parent.mkdir(parents=True, exist_ok=True)

        from vieneu import Vieneu

        tts = create_tts(Vieneu, payload)
        apply_runtime_overrides(tts, payload)
        audio = synthesize(tts, payload)
        tts.save(audio, str(output_path))
    except Exception as exc:
        raise SystemExit(f"VieNeu worker lỗi: {exc}") from exc


def create_tts(vieneu_factory, payload: dict):
    mode = payload.get("mode", "standard")
    if mode != "standard":
        kwargs = _vieneu_kwargs(
            payload,
            [
                "backbone_repo",
                "backbone_filename",
                "decoder_repo",
                "decoder_filename",
                "encoder_repo",
                "encoder_filename",
                "device",
            ],
        )
        return vieneu_factory(mode=mode, **kwargs)

    kwargs = {"emotion": payload.get("emotion", "natural")}
    kwargs.update(
        _vieneu_kwargs(
            payload,
            [
                "backbone_repo",
                "gguf_filename",
                "codec_repo",
                "codec_device",
                "backbone_device",
            ],
        )
    )
    if payload.get("ref_audio"):
        kwargs.update({
            "codec_repo": payload.get("clone_codec_repo") or payload.get("codec_repo") or STANDARD_CLONE_CODEC_REPO,
            "codec_device": payload.get("clone_codec_device") or STANDARD_CLONE_CODEC_DEVICE,
            "backbone_device": payload.get("backbone_device") or "cpu",
        })
    return vieneu_factory(**kwargs)


def _vieneu_kwargs(payload: dict, keys: list[str]) -> dict:
    return {key: payload[key] for key in keys if payload.get(key)}


def apply_runtime_overrides(tts, payload: dict) -> None:
    if payload.get("legacy_chat_format") and hasattr(tts, "use_chat_format"):
        tts.use_chat_format = True


def _infer_kwargs(payload: dict) -> dict:
    kwargs = {}
    if payload.get("temperature") is not None:
        kwargs["temperature"] = float(payload["temperature"])
    if payload.get("top_k") is not None:
        kwargs["top_k"] = int(payload["top_k"])
    if payload.get("disable_emotion_tag"):
        kwargs["emotion_tag"] = None
    return kwargs


def synthesize(tts, payload: dict):
    text = payload["text"]
    ref_audio = payload.get("ref_audio")
    ref_text = payload.get("ref_text")
    voice_name = payload.get("voice_name")
    mode = payload.get("mode", "standard")
    if payload.get("prompt_format") == "speech_token_gguf" and not ref_audio:
        return synthesize_speech_token_gguf(tts, payload)
    if ref_audio and mode == "turbo":
        voice = tts.encode_reference(ref_audio)
        return tts.infer(text=text, voice=voice, **_infer_kwargs(payload))
    if ref_audio and mode == "standard":
        try:
            return tts.infer(text=text, ref_audio=ref_audio, ref_text=ref_text, **_infer_kwargs(payload))
        except AttributeError as exc:
            if "encode_code" not in str(exc):
                raise
            raise RuntimeError(
                "VieNeu Standard cần backend codec có encode_code để clone giọng. "
                "Hãy chạy install_vieneu_worker.bat để cài neucodec."
            ) from exc
    if ref_audio:
        return tts.infer(text=text, ref_audio=ref_audio, ref_text=ref_text, **_infer_kwargs(payload))
    if voice_name:
        voice = tts.get_preset_voice(voice_name)
        return tts.infer(text=text, voice=voice, **_infer_kwargs(payload))
    return tts.infer(text=text, **_infer_kwargs(payload))


def synthesize_speech_token_gguf(tts, payload: dict):
    from transformers import AutoTokenizer
    from vieneu_utils.phonemize_text import phonemize_with_dict

    speech_offset = int(payload.get("speech_offset") or 151671)
    speech_end = int(payload.get("speech_end") or 151670)
    speech_max = int(payload.get("speech_max") or 65535)
    repo = payload["backbone_repo"]
    voice = tts.get_preset_voice(payload.get("voice_name"))
    ref_codes = _flatten_codes(voice["codes"])
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
    speech_ids = []
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


def _flatten_codes(codes):
    try:
        import torch
        if isinstance(codes, torch.Tensor):
            return codes.detach().cpu().numpy().reshape(-1)
    except Exception:
        pass
    import numpy as np

    return np.asarray(codes).reshape(-1)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", type=Path, required=True)
    return parser.parse_args()


if __name__ == "__main__":
    main()
