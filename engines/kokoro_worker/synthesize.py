from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


_MODEL = None
_MODEL_KEY: tuple[str, str] | None = None


def _runtime_path(model_root: Path, runtime: dict, key: str) -> Path:
    value = str(runtime.get(key) or "").strip()
    if not value:
        raise ValueError(f"Thiếu runtime.{key} trong catalog model.")
    return model_root / value


def _combined_voices(model_root: Path, runtime: dict) -> Path:
    import numpy as np

    voices_dir = _runtime_path(model_root, runtime, "voices_dir")
    target = _runtime_path(model_root, runtime, "combined_voices_file")
    source_files = sorted(
        path for path in voices_dir.glob("*.bin") if path.stem != "af"
    )
    if not source_files:
        raise FileNotFoundError(f"Không tìm thấy voice Kokoro trong {voices_dir}")
    newest_source = max(path.stat().st_mtime for path in source_files)
    if target.is_file() and target.stat().st_mtime >= newest_source:
        return target
    voices = {}
    for source in source_files:
        values = np.fromfile(source, dtype=np.float32)
        if values.size % 256:
            raise ValueError(f"Voice {source.name} có kích thước không hợp lệ.")
        voices[source.stem] = values.reshape(-1, 1, 256)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".tmp")
    with temporary.open("wb") as handle:
        np.savez(handle, **voices)
    temporary.replace(target)
    return target


def _load_model(model_root: Path, runtime: dict):
    global _MODEL, _MODEL_KEY
    from kokoro_onnx import Kokoro

    model_path = _runtime_path(model_root, runtime, "model_file")
    voices_path = _combined_voices(model_root, runtime)
    key = (str(model_path.resolve()), str(voices_path.resolve()))
    if _MODEL is None or _MODEL_KEY != key:
        _MODEL = Kokoro(str(model_path), str(voices_path))
        # kokoro-onnx 0.6.1 checks the singular output name ``duration`` while
        # this timestamped ONNX export names it ``durations``. The tensor
        # contract is otherwise identical and _infer reads output index 1.
        output_names = {item.name for item in _MODEL.sess.get_outputs()}
        if output_names.intersection({"duration", "durations"}):
            _MODEL.has_timings = True
        _MODEL_KEY = key
    return _MODEL


def _language(runtime: dict, code: str) -> str:
    mapping = runtime.get("language_map") or {}
    value = str(mapping.get(code) or "").strip()
    if not value:
        raise ValueError(f"Catalog Kokoro chưa ánh xạ ngôn ngữ '{code}'.")
    return value


def _synthesize(payload: dict) -> None:
    import numpy as np
    import soundfile as sf

    model_root = Path(payload["model_root"])
    runtime = dict(payload.get("runtime") or {})
    model = _load_model(model_root, runtime)
    voice = str(payload.get("speaker_id") or "").strip()
    if not voice:
        raise ValueError("Chưa chọn giọng Kokoro.")
    language = _language(runtime, str(payload.get("language") or "en"))
    speed = max(0.5, min(1.8, float(payload.get("speed") or 1.0)))
    options = dict(payload.get("options") or {})
    trim = bool(options.get("trim_silence", True))
    continuous = bool(options.get("continuous_prosody", False))

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
            audio, sample_rate = model.create(
                text,
                voice=voice,
                speed=speed,
                lang=language,
                trim=trim,
                sentence_pause=0.0,
                clause_pause=0.0,
                continuous=continuous,
            )
            parts.append(np.asarray(audio, dtype=np.float32).reshape(-1))
            pause_ms = int(item.get("pause_after_ms") or 0)
            if index < len(items) - 1 and pause_ms > 0:
                parts.append(np.zeros(int(sample_rate * pause_ms / 1000), dtype=np.float32))
        if not parts:
            raise ValueError("Đoạn Kokoro không có nội dung hợp lệ.")
        output = Path(chunk["output_path"])
        output.parent.mkdir(parents=True, exist_ok=True)
        sf.write(str(output), np.concatenate(parts), sample_rate, subtype="PCM_16")


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
