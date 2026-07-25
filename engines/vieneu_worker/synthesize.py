from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from worker_utils import apply_runtime_overrides

_MODE_HANDLERS = {
    "standard": ("modes.standard", "create_standard_tts", "run_standard", "run_standard_batch"),
    "turbo":    ("modes.turbo",    "create_turbo_tts",    "run_turbo",    "run_turbo_batch"),
    "pytorch":  ("modes.pytorch_mode", "create_pytorch_tts", "run_pytorch", "run_pytorch_batch"),
    "lora":     ("modes.lora_mode",    "create_lora_tts",   "run_lora",    "run_lora_batch"),
    "v3turbo":  ("modes.v3turbo", "create_v3_turbo_tts", "run_v3_turbo", "run_v3_turbo_batch"),
}
_TTS_CACHE = {}


def main() -> None:
    try:
        args = _parse_args()
        from vieneu import Vieneu
        if args.serve:
            _serve(Vieneu)
            return
        payload = json.loads(args.request.read_text(encoding="utf-8-sig"))
        if payload.get("batch"):
            _run_batch(Vieneu, payload)
        else:
            _run_single(Vieneu, payload)
    except Exception as exc:
        raise SystemExit(f"VieNeu worker lỗi: {exc}") from exc


def _run_single(vieneu_factory: type, payload: dict) -> None:
    output_path = Path(payload["output_path"])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    create_fn, run_fn, _ = _resolve_handlers(payload)
    tts = _cached_tts(create_fn, vieneu_factory, payload)
    tts_obj = tts[0] if isinstance(tts, tuple) else tts
    apply_runtime_overrides(tts_obj, payload)
    audio = run_fn(tts, payload)
    _save(tts_obj, audio, output_path)


def _run_batch(vieneu_factory: type, payload: dict) -> None:
    chunks = payload.get("chunks") or []
    if not chunks:
        return
    create_fn, _, run_batch_fn = _resolve_handlers(payload)
    tts = _cached_tts(create_fn, vieneu_factory, payload)
    tts_obj = tts[0] if isinstance(tts, tuple) else tts
    apply_runtime_overrides(tts_obj, payload)
    run_batch_fn(tts, chunks, payload)


def _resolve_handlers(payload: dict):
    mode = payload.get("mode", "standard")
    entry = _MODE_HANDLERS.get(mode)
    if entry is None:
        raise ValueError(f"VieNeu mode không được hỗ trợ: '{mode}'. Các mode hợp lệ: {list(_MODE_HANDLERS)}")
    module_name, create_name, run_name, run_batch_name = entry
    import importlib
    mod = importlib.import_module(module_name)
    return getattr(mod, create_name), getattr(mod, run_name), getattr(mod, run_batch_name)


def _cached_tts(create_fn, vieneu_factory: type, payload: dict):
    constructor_keys = {
        "mode",
        "emotion",
        "backbone_repo",
        "backbone_filename",
        "gguf_filename",
        "decoder_repo",
        "decoder_filename",
        "encoder_repo",
        "encoder_filename",
        "codec_repo",
        "codec_device",
        "backbone_device",
        "device",
        "pytorch_device",
        "lora_repo",
        "lora_filename",
        "base_repo",
        "model_subfolder",
        "moss_tokenizer",
        "backend",
        "precision",
        "onnx_subfolder",
        "threads",
        "max_batch_size",
    }
    constructor_payload = {
        key: value for key, value in payload.items() if key in constructor_keys
    }
    cache_key = (
        f"{create_fn.__module__}.{create_fn.__name__}:"
        f"{json.dumps(constructor_payload, ensure_ascii=False, sort_keys=True)}"
    )
    if cache_key not in _TTS_CACHE:
        _TTS_CACHE.clear()
        _TTS_CACHE[cache_key] = create_fn(vieneu_factory, payload)
    return _TTS_CACHE[cache_key]


def _serve(vieneu_factory: type) -> None:
    for line in sys.stdin:
        try:
            payload = json.loads(line)
            if payload.get("batch"):
                _run_batch(vieneu_factory, payload)
            else:
                _run_single(vieneu_factory, payload)
            response = {"ok": True}
        except Exception as exc:
            response = {"ok": False, "error": str(exc)}
        sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
        sys.stdout.flush()


def _save(tts, audio, output_path: Path) -> None:
    tts.save(audio, str(output_path))


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", type=Path)
    parser.add_argument("--serve", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    main()
