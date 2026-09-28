from __future__ import annotations

import argparse
import gc
import json
import sys
from pathlib import Path

UNCONDITIONED_VOICE_ID = "__unconditioned__"

_MODEL = None
_MODEL_KEY: tuple[str, int, int, bool] | None = None


def _model_settings(options: dict) -> tuple[int, int, bool]:
    threads = int(options.get("intra_op_num_threads", 4))
    codec_threads = int(options.get("codec_intra_op_num_threads", 0))
    warmup = bool(options.get("warmup", True))
    if threads < 1:
        raise ValueError("Số luồng ONNX cho model phải từ 1 trở lên.")
    if codec_threads < 0:
        raise ValueError("Số luồng ONNX cho codec không được âm.")
    return threads, codec_threads, warmup


def _load_model(model_root: Path, options: dict):
    global _MODEL, _MODEL_KEY
    from zerotts import ZeroTTS

    threads, codec_threads, warmup = _model_settings(options)
    key = (str(model_root.resolve()), threads, codec_threads, warmup)
    if _MODEL is None or _MODEL_KEY != key:
        _MODEL = None
        gc.collect()
        _MODEL = ZeroTTS(
            model_root,
            providers=["CPUExecutionProvider"],
            intra_op_num_threads=threads,
            codec_intra_op_num_threads=codec_threads or None,
            warmup=warmup,
        )
        _MODEL_KEY = key
    return _MODEL


def _prepare_segments(text: str, language: str, options: dict) -> list[str]:
    from zerotts.chunking import (
        chunk_text,
        clean_segment_punctuation,
        normalize_punctuation,
    )
    from zerotts.text_norm import normalize_vi_text

    prepared = text.strip()
    if language == "vi" and bool(options.get("normalize_vi_text", True)):
        prepared = normalize_vi_text(prepared)
    if bool(options.get("normalize_punctuation", True)):
        prepared = normalize_punctuation(prepared)
    segments = chunk_text(
        prepared,
        max_chunk_sec=float(options.get("max_chunk_sec", 15.0)),
    )
    if bool(options.get("clean_segment_punctuation", True)):
        segments = [clean_segment_punctuation(item) for item in segments]
    return [item for item in segments if item and item.strip()]


def _sampling_options(options: dict) -> dict:
    min_frames = int(options.get("min_frames", 4))
    max_frames = int(options.get("max_frames", 1500))
    if min_frames > max_frames:
        raise ValueError("Số frame tối thiểu không được lớn hơn số frame tối đa.")
    return {
        "cfg_scale": float(options.get("cfg_scale", 1.0)),
        "text_temperature": float(options.get("text_temperature", 1.0)),
        "text_topk": int(options.get("text_topk", 50)),
        "audio_temperature": float(options.get("audio_temperature", 0.8)),
        "audio_topk": int(options.get("audio_topk", 25)),
        "audio_topp": float(options.get("audio_topp", 0.95)),
        "audio_repetition_penalty": float(options.get("audio_repetition_penalty", 1.2)),
        "min_frames": min_frames,
        "max_frames": max_frames,
        "eoa_extra_frames": int(options.get("eoa_extra_frames", 1)),
    }


def _voice_value(speaker_id: str | None):
    voice = str(speaker_id or "").strip()
    if not voice:
        raise ValueError("Chưa chọn voice pack ZeroTTS.")
    return None if voice == UNCONDITIONED_VOICE_ID else voice


def _synthesize_segment(tts, text: str, voice, options: dict):
    import numpy as np

    sampling = _sampling_options(options)
    if voice is None:
        sampling["cfg_scale"] = 1.0
    if not bool(options.get("streaming_decoder", True)):
        return np.asarray(
            tts.synthesize(text, voice=voice, **sampling), dtype=np.float32
        ).reshape(-1)

    first_frames = int(options.get("first_chunk_frames", 1))
    max_chunk_frames = int(options.get("max_chunk_frames", 16))
    if first_frames > max_chunk_frames:
        raise ValueError(
            "Frame của chunk streaming đầu không được lớn hơn trần frame mỗi chunk."
        )
    chunks = [
        np.asarray(chunk, dtype=np.float32).reshape(-1)
        for chunk in tts.synthesize_stream(
            text,
            voice=voice,
            first_chunk_frames=first_frames,
            max_chunk_frames=max_chunk_frames,
            **sampling,
        )
    ]
    return np.concatenate(chunks) if chunks else np.zeros(0, dtype=np.float32)


def _synthesize(payload: dict) -> None:
    import numpy as np
    import soundfile as sf

    model_root = Path(payload["model_root"])
    options = dict(payload.get("options") or {})
    tts = _load_model(model_root, options)
    voice = _voice_value(payload.get("speaker_id"))
    language = str(payload.get("language") or "vi")
    seed = int(options.get("seed", -1))
    if seed >= 0:
        np.random.seed(seed)
    gap_seconds = float(options.get("segment_gap_seconds", 0.08))

    for chunk in payload.get("chunks") or []:
        segments = _prepare_segments(str(chunk.get("text") or ""), language, options)
        if not segments:
            raise ValueError("Đoạn ZeroTTS không có nội dung hợp lệ.")
        parts: list[np.ndarray] = []
        for index, segment in enumerate(segments):
            audio = _synthesize_segment(tts, segment, voice, options)
            if audio.size == 0:
                raise ValueError("ZeroTTS trả về audio rỗng.")
            parts.append(audio)
            if index < len(segments) - 1 and gap_seconds > 0:
                parts.append(
                    np.zeros(int(tts.sample_rate * gap_seconds), dtype=np.float32)
                )
        output = Path(chunk["output_path"])
        output.parent.mkdir(parents=True, exist_ok=True)
        sf.write(
            str(output),
            np.concatenate(parts),
            int(tts.sample_rate),
            subtype="PCM_16",
        )


def _serve() -> None:
    for line in sys.stdin:
        try:
            _synthesize(json.loads(line))
            response = {"ok": True}
        except Exception as exc:
            response = {"ok": False, "error": str(exc)}
        sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
        sys.stdout.flush()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", type=Path)
    parser.add_argument("--serve", action="store_true")
    args = parser.parse_args()
    if args.serve:
        _serve()
    elif args.request:
        _synthesize(json.loads(args.request.read_text(encoding="utf-8-sig")))
    else:
        parser.error("Cần --serve hoặc --request.")


if __name__ == "__main__":
    main()
