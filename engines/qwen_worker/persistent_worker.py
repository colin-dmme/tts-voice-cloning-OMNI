"""
Persistent Qwen3-TTS worker process.

Stays alive and processes requests via JSON-lines protocol over stdin/stdout.
Model is loaded ONCE on the first request and kept in VRAM.
Voice clone prompts are cached and only rebuilt when reference audio changes.

Protocol:
  - Main process writes one JSON line per request to worker stdin.
  - Worker writes one JSON line per response to stdout.
  - Request types:
      {"action": "generate", "text": ..., "language": ..., "ref_audio": ..., ...}
      {"action": "shutdown"}
  - Response:
      {"ok": true, "output_path": "..."} or {"ok": false, "error": "..."}
"""
from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path

LANGUAGE_MAP = {
    "en": "English",
    "zh": "Chinese",
    "ja": "Japanese",
    "ko": "Korean",
    "de": "German",
    "fr": "French",
    "ru": "Russian",
    "pt": "Portuguese",
    "es": "Spanish",
    "it": "Italian",
}


class PersistentWorker:
    def __init__(self):
        self._model = None
        self._model_path: str = ""
        self._cached_prompt = None
        self._cached_ref_audio: str = ""

    def run(self) -> None:
        """Main loop: read JSON lines from stdin, process, write JSON to stdout."""
        # Signal ready
        _send({"status": "ready"})

        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                # Strip BOM and other stray chars
                line = line.lstrip("\ufeff")
                request = json.loads(line)
            except json.JSONDecodeError as e:
                _send({"ok": False, "error": f"Invalid JSON: {e}"})
                continue

            action = request.get("action", "generate")
            if action == "shutdown":
                _send({"ok": True, "message": "shutting down"})
                break

            try:
                result = self._handle_generate(request)
                _send(result)
            except Exception as e:
                _send({"ok": False, "error": str(e), "traceback": traceback.format_exc()})

    def _handle_generate(self, request: dict) -> dict:
        model = self._ensure_model(request)
        self._ensure_clone_prompt(model, request)

        text = request["text"]
        language = _language_name(request.get("language"))
        output_path = Path(request["output_path"])
        output_path.parent.mkdir(parents=True, exist_ok=True)

        wavs, sample_rate = model.generate_voice_clone(
            text=text,
            language=language,
            voice_clone_prompt=self._cached_prompt,
            max_new_tokens=_estimate_max_tokens(text),
            do_sample=True,
            top_k=50,
            top_p=1.0,
            temperature=0.9,
            repetition_penalty=1.05,
        )

        import soundfile as sf
        sf.write(str(output_path), wavs[0], int(sample_rate))
        return {"ok": True, "output_path": str(output_path)}

    def _ensure_model(self, request: dict):
        model_path = request.get("model_path") or request.get("hf_repo", "")
        if self._model is not None and self._model_path == model_path:
            return self._model

        # Load or switch model
        import torch
        from qwen_tts import Qwen3TTSModel

        device_map = request.get("device_map") or _device_map()
        dtype = _dtype(device_map)

        kwargs = {"device_map": device_map, "dtype": dtype}
        if device_map != "cpu":
            kwargs["attn_implementation"] = request.get("attn_implementation") or "sdpa"

        # Log to stderr (stdout is used for protocol)
        _log(f"Loading model: {model_path} (device={device_map})")
        self._model = Qwen3TTSModel.from_pretrained(model_path, **kwargs)
        self._model_path = model_path
        # Reset clone prompt cache when model changes
        self._cached_prompt = None
        self._cached_ref_audio = ""
        _log("Model loaded successfully")
        return self._model

    def _ensure_clone_prompt(self, model, request: dict) -> None:
        ref_audio = request.get("ref_audio", "")
        ref_text = request.get("ref_text", "")

        if not ref_audio:
            raise RuntimeError(
                "Qwen3-TTS Base cần Profile giọng. Hãy chọn Profile giọng trước."
            )

        if self._cached_prompt is not None and self._cached_ref_audio == ref_audio:
            return  # reuse

        _log(f"Creating voice clone prompt from: {ref_audio}")
        self._cached_prompt = model.create_voice_clone_prompt(
            ref_audio=ref_audio,
            ref_text=ref_text,
            x_vector_only_mode=True,
        )
        self._cached_ref_audio = ref_audio
        _log("Voice clone prompt cached")


def _device_map() -> str:
    try:
        import torch
    except Exception:
        return "cpu"
    if torch.cuda.is_available():
        return "cuda:0"
    return "cpu"


def _dtype(device_map: str):
    import torch
    if device_map == "cpu":
        return torch.float32
    major, _minor = torch.cuda.get_device_capability(0)
    if major >= 8:
        return torch.bfloat16
    return torch.float16


def _language_name(language: str | None) -> str:
    if not language:
        return "Auto"
    return LANGUAGE_MAP.get(language.lower(), "Auto")


def _estimate_max_tokens(text: str) -> int:
    estimated_tokens = max(256, int(len(text) * 3))
    return min(estimated_tokens, 2048)


def _send(data: dict) -> None:
    """Send a JSON line to stdout."""
    sys.stdout.write(json.dumps(data, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _log(message: str) -> None:
    """Log to stderr (doesn't interfere with JSON protocol on stdout)."""
    sys.stderr.write(f"[qwen-worker] {message}\n")
    sys.stderr.flush()


if __name__ == "__main__":
    PersistentWorker().run()
