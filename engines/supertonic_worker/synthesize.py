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

    trim_split = bool(dict(payload.get("pause_options") or {}).get("split_total"))
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
            piece = np.asarray(audio, dtype=np.float32).reshape(-1)
            if trim_split and len(items) > 1:
                piece = _trim_edges(piece, int(tts.sample_rate), lead=index > 0, tail=index < len(items) - 1)
            parts.append(piece)
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


def _trim_edges(audio, sample_rate: int, *, lead: bool, tail: bool, threshold_db: float = -45.0):
    """Nhịp đọc: drop the silence a fragment carries where it meets another
    fragment, so the inserted pause_after_ms is the total pause heard."""
    import numpy as np

    hop = max(1, int(sample_rate * 0.005))
    usable = len(audio) // hop * hop
    if not usable or not (lead or tail):
        return audio
    frames = np.asarray(audio[:usable], dtype=np.float64).reshape(-1, hop)
    level = 20 * np.log10(np.sqrt((frames ** 2).mean(axis=1)) + 1e-9)
    loud = np.flatnonzero(level >= threshold_db)
    if not loud.size:
        return audio
    margin = int(sample_rate * 0.02)
    start = max(0, loud[0] * hop - margin) if lead else 0
    end = min(len(audio), (loud[-1] + 1) * hop + margin) if tail else len(audio)
    return audio[start:end]


if __name__ == "__main__":
    main()
