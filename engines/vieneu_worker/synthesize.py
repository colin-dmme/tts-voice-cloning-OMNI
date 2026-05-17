from __future__ import annotations

import argparse
import json
from pathlib import Path

from worker_utils import apply_runtime_overrides

_MODE_HANDLERS = {
    "standard": ("modes.standard", "create_standard_tts", "run_standard", "run_standard_batch"),
    "turbo":    ("modes.turbo",    "create_turbo_tts",    "run_turbo",    "run_turbo_batch"),
    "pytorch":  ("modes.pytorch_mode", "create_pytorch_tts", "run_pytorch", "run_pytorch_batch"),
    "lora":     ("modes.lora_mode",    "create_lora_tts",   "run_lora",    "run_lora_batch"),
}


def main() -> None:
    try:
        args = _parse_args()
        payload = json.loads(args.request.read_text(encoding="utf-8-sig"))
        from vieneu import Vieneu
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
    tts = create_fn(vieneu_factory, payload)
    tts_obj = tts[0] if isinstance(tts, tuple) else tts
    apply_runtime_overrides(tts_obj, payload)
    audio = run_fn(tts, payload)
    _save(tts_obj, audio, output_path)


def _run_batch(vieneu_factory: type, payload: dict) -> None:
    chunks = payload.get("chunks") or []
    if not chunks:
        return
    create_fn, _, run_batch_fn = _resolve_handlers(payload)
    tts = create_fn(vieneu_factory, payload)
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


def _save(tts, audio, output_path: Path) -> None:
    tts.save(audio, str(output_path))


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", type=Path, required=True)
    return parser.parse_args()


if __name__ == "__main__":
    main()
