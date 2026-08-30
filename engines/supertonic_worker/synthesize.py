from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


_MODEL = None
_MODEL_ROOT: str | None = None


def _load_model(model_root: Path):
    global _MODEL, _MODEL_ROOT
    from supertonic import TTS

    key = str(model_root.resolve())
    if _MODEL is None or _MODEL_ROOT != key:
        _MODEL = TTS(
            model="supertonic-3",
            model_dir=model_root,
            auto_download=False,
        )
        _MODEL_ROOT = key
    return _MODEL


def _synthesize(payload: dict) -> None:
    import numpy as np
    import soundfile as sf

    model_root = Path(payload["model_root"])
    tts = _load_model(model_root)
    voice = str(payload.get("speaker_id") or "").strip()
    if not voice:
        raise ValueError("Chưa chọn voice style Supertonic 3.")
    style = tts.get_voice_style(voice_name=voice)
    language = str(payload.get("language") or "na")
    speed = float(payload.get("speed") or 1.0)
    options = dict(payload.get("options") or {})
    total_steps = int(options.get("total_steps", 8))

    for chunk in payload.get("chunks") or []:
        parts: list[np.ndarray] = []
        segments = chunk.get("segments")
        items = segments if isinstance(segments, list) and segments else [
            {"text": chunk.get("text") or "", "pause_after_ms": 0}
        ]
        for index, item in enumerate(items):
            text = str(item.get("text") or "").strip()
            if not text:
                continue
            audio, _duration = tts.synthesize(
                text,
                voice_style=style,
                total_steps=total_steps,
                speed=speed,
                max_chunk_length=max(300, len(text) + 1),
                silence_duration=0.0,
                lang=language,
                verbose=False,
            )
            parts.append(np.asarray(audio, dtype=np.float32).reshape(-1))
            pause_ms = int(item.get("pause_after_ms") or 0)
            if index < len(items) - 1 and pause_ms > 0:
                parts.append(
                    np.zeros(int(tts.sample_rate * pause_ms / 1000), dtype=np.float32)
                )
        if not parts:
            raise ValueError("Đoạn Supertonic không có nội dung hợp lệ.")
        output = Path(chunk["output_path"])
        output.parent.mkdir(parents=True, exist_ok=True)
        sf.write(
            str(output), np.concatenate(parts), int(tts.sample_rate), subtype="PCM_16"
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
