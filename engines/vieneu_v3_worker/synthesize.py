from __future__ import annotations

import argparse
import gc
import inspect
import json
import sys
from importlib.metadata import PackageNotFoundError, version
from importlib.resources import files
from pathlib import Path
from typing import Any

_TTS: Any | None = None
_TTS_KEY = ""


def main() -> None:
    args = _parse_args()
    if args.describe:
        print(json.dumps(_describe(), ensure_ascii=False))
        return
    try:
        from vieneu import Vieneu

        if args.serve:
            _serve(Vieneu)
            return
        if args.request is None:
            raise ValueError("Thiếu --request cho VieNeu v3 worker.")
        payload = json.loads(args.request.read_text(encoding="utf-8-sig"))
        _run(Vieneu, payload)
    except Exception as exc:
        raise SystemExit(f"VieNeu v3 worker lỗi: {_friendly_error(exc)}") from exc


def _run(vieneu_factory: type, payload: dict) -> None:
    if str(payload.get("mode") or "v3turbo").lower() != "v3turbo":
        raise ValueError("Worker VieNeu v3 chỉ hỗ trợ mode v3turbo; model VieNeu v2 phải dùng worker VieNeu v2.")
    if payload.get("batch"):
        _run_batch(vieneu_factory, payload)
    else:
        _run_single(vieneu_factory, payload)


def _run_single(vieneu_factory: type, payload: dict) -> None:
    tts = _cached_tts(vieneu_factory, payload)
    output_path = Path(payload["output_path"])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    audio = tts.infer(text=str(payload["text"]), **_infer_kwargs(payload))
    tts.save(audio, str(output_path))


def _run_batch(vieneu_factory: type, payload: dict) -> None:
    chunks = list(payload.get("chunks") or [])
    if not chunks:
        return
    tts = _cached_tts(vieneu_factory, payload)
    audio_items = tts.infer_batch(
        [str(chunk["text"]) for chunk in chunks],
        **_infer_kwargs(payload),
    )
    if len(audio_items) != len(chunks):
        raise RuntimeError("VieNeu v3 trả về số audio không khớp số đoạn trong batch.")
    for chunk, audio in zip(chunks, audio_items):
        output_path = Path(chunk["output_path"])
        output_path.parent.mkdir(parents=True, exist_ok=True)
        tts.save(audio, str(output_path))


def _cached_tts(vieneu_factory: type, payload: dict) -> Any:
    global _TTS, _TTS_KEY
    constructor_keys = (
        "backbone_repo",
        "model_subfolder",
        "moss_tokenizer",
        "device",
        "dtype",
        "backend",
        "onnx_repo",
        "onnx_dir",
        "precision",
        "onnx_subfolder",
        "threads",
        "max_batch_size",
        "babble_retries",
    )
    constructor = {
        key: payload[key]
        for key in constructor_keys
        if payload.get(key) not in (None, "")
    }
    key = json.dumps(constructor, ensure_ascii=False, sort_keys=True)
    if _TTS is None or key != _TTS_KEY:
        _TTS = None
        gc.collect()
        _TTS = vieneu_factory(mode="v3turbo", **constructor)
        _TTS_KEY = key
    return _TTS


def _infer_kwargs(payload: dict) -> dict[str, Any]:
    kwargs: dict[str, Any] = {}
    if payload.get("ref_audio"):
        kwargs["ref_audio"] = str(payload["ref_audio"])
        kwargs["denoise"] = bool(payload.get("denoise_reference", True))
    elif payload.get("voice_name"):
        kwargs["voice"] = str(payload["voice_name"])
    if payload.get("temperature") is not None:
        kwargs["temperature"] = float(payload["temperature"])
    if payload.get("top_k") is not None:
        kwargs["top_k"] = int(payload["top_k"])
    if payload.get("repetition_window") is not None:
        kwargs["repetition_window"] = int(payload["repetition_window"])
    return kwargs


def _serve(vieneu_factory: type) -> None:
    for line in sys.stdin:
        try:
            payload = json.loads(line)
            if payload.get("command") == "describe":
                response = {"ok": True, "runtime": _describe()}
            else:
                _run(vieneu_factory, payload)
                response = {"ok": True}
        except Exception as exc:
            response = {"ok": False, "error": _friendly_error(exc)}
        sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
        sys.stdout.flush()


def _describe() -> dict[str, Any]:
    presets, default_voice = _preset_catalog()
    sdk_defaults = _sdk_v3_defaults()
    onnx_providers: list[str] = []
    try:
        import onnxruntime as ort

        onnx_providers = list(ort.get_available_providers())
    except Exception:
        pass
    torch_version = ""
    cuda_available = False
    cuda_device = ""
    try:
        import torch

        torch_version = str(getattr(torch, "__version__", ""))
        cuda_available = bool(torch.cuda.is_available())
        if cuda_available:
            cuda_device = str(torch.cuda.get_device_name(0))
    except Exception:
        pass
    return {
        "worker": "vieneu_v3_worker",
        "worker_label": "VieNeu v3",
        "sdk_version": _package_version("vieneu"),
        "sea_g2p_version": _package_version("sea-g2p"),
        "backend_default": sdk_defaults.get("backend", "auto"),
        "device_default": sdk_defaults.get("device", "auto"),
        "precision_default": sdk_defaults.get("precision", ""),
        "supported_precisions": ["fp32", "int8"],
        "onnx_providers": onnx_providers,
        "torch_version": torch_version,
        "cuda_available": cuda_available,
        "cuda_device": cuda_device,
        "default_voice": default_voice,
        "preset_count": len(presets),
        "presets": presets,
    }


def _sdk_v3_defaults() -> dict[str, Any]:
    try:
        from vieneu.v3turbo import V3TurboVieNeuTTS

        parameters = inspect.signature(V3TurboVieNeuTTS.__init__).parameters
        defaults: dict[str, Any] = {}
        for key in ("backend", "device", "precision", "babble_retries"):
            parameter = parameters.get(key)
            if parameter is None or parameter.default is inspect.Parameter.empty:
                continue
            defaults[key] = parameter.default
        return defaults
    except Exception:
        return {}


def _preset_catalog() -> tuple[dict[str, str], str]:
    try:
        asset = files("vieneu").joinpath("assets/voices_v3_turbo.json")
        data = json.loads(asset.read_text(encoding="utf-8"))
        presets = {
            str(name): str((detail or {}).get("description") or name)
            for name, detail in (data.get("presets") or {}).items()
        }
        return presets, str(data.get("default_voice") or "")
    except Exception:
        return {}, ""


def _package_version(distribution: str) -> str:
    try:
        return version(distribution)
    except PackageNotFoundError:
        return ""


def _friendly_error(exc: Exception) -> str:
    message = str(exc).strip() or exc.__class__.__name__
    lower = message.lower()
    if "kaldi_native_fbank" in lower:
        return "Thiếu kaldi-native-fbank; hãy cài lại worker VieNeu v3."
    if "sea_g2p" in lower or "sea-g2p" in lower:
        return "Thiếu hoặc sai phiên bản sea-g2p; hãy cài lại worker VieNeu v3."
    if "torch" in lower and ("required" in lower or "no module" in lower):
        return "Đã yêu cầu GPU PyTorch nhưng worker VieNeu v3 chưa có CUDA; hãy cài GPU/CUDA hoặc chọn CPU ONNX."
    return message


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", type=Path)
    parser.add_argument("--serve", action="store_true")
    parser.add_argument("--describe", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    main()
