from __future__ import annotations

"""
Mode 'lora' legacy/experimental: sử dụng voice preset từ LoRA repo's
voices.json với GGUF backbone.

Lý do thiết kế:
  LoRA adapter pnnbao-ump/VieNeu-TTS-0.3B-lora-ngoc-huyen được train trên
  backbone có hidden_size=512, nhưng pnnbao-ump/VieNeu-TTS-0.3B hiện đã được
  cập nhật lên kiến trúc Qwen3 với hidden_size=768 → PEFT load_lora_adapter()
  không thể dùng được (dimension mismatch ở toàn bộ layers).

  Legacy workaround: LoRA repo chứa voices.json với voice preset codes
  (NgocHuyen) cùng format với standard mode. Ta dùng GGUF backbone
  (VieNeu-TTS-0.3B-q4-gguf) và inject voice dict từ LoRA repo's voices.json.
  Không load PEFT adapter weights. Đường chạy chính cho Ngọc Huyền nên là
  pnnbao-ump/VieNeu-TTS-0.3B-ngoc-huyen hoặc bản GGUF riêng.

Luồng:
  1. Khởi tạo Vieneu với GGUF backbone (backbone_repo + gguf_filename)
  2. Đọc voices.json từ lora_repo qua HF cache → lấy voice preset {codes, text}
  3. tts.infer(text=text, voice=voice_dict)
     - text trong voice dict bắt buộc để model align ref_codes với ref_phonemes

Vấn đề tạp âm (codes/syllable mismatch):
  LoRA voice codes được tạo bởi LoRA-adapted model với code density khác base GGUF.
  Base GGUF model chỉ nhận ra ~11/17 syllables từ 227 codes của NgocHuyen → model
  tự sinh 6 syllable còn lại ("tính chiến đấu, tính định hướng") thành noise ở đầu
  mỗi chunk trước khi sang chunk text.

  Decoded audio analysis (227 codes → 4.52s):
    0.0-1.8s: "Tác phẩm dự thi bảo đảm tính khoa học"  (silence gap tại 1.8s)
    2.0-2.4s: "tính đảng,"                              (near-silence tại 2.4s)
    2.6-3.4s: "tính chiến đấu,"                         (silence gap tại 3.4s)
    3.6-4.5s: "tính định hướng."

  Fix: trim mỗi voice preset về đến boundary im lặng tự nhiên với text khớp
  (xem _LORA_VOICE_TRIM). 120 codes ≈ 2.4s, 11 syllables → 10.9 codes/syl
  (cùng dải với preset Binh: 11.1 codes/syl, Vinh: 12.3 codes/syl).
"""

import json
import sys
from pathlib import Path
from typing import Any

from worker_utils import (
    STANDARD_CLONE_CODEC_DEVICE,
    STANDARD_CLONE_CODEC_REPO,
    infer_kwargs,
    vieneu_kwargs,
)

# Per-voice trim config: trim codes+text to a natural silence boundary so that
# the base GGUF model's codes/syllable expectation matches the reference.
# Each entry: {"codes_end": int, "text": str}
_LORA_VOICE_TRIM: dict[str, dict] = {
    # 227 codes full → model only recognises ~11 syl → 6-syl noise at chunk start.
    # Trim to code 120 (2.4s, near-silence after "đảng,"), 11 syl → 10.9 codes/syl.
    "NgocHuyen": {
        "codes_end": 120,
        "text": "Tác phẩm dự thi bảo đảm tính khoa học, tính đảng",
    },
}


def create_lora_tts(vieneu_factory: Any, payload: dict) -> Any:
    kwargs: dict = {"emotion": payload.get("emotion", "natural")}
    kwargs.update(vieneu_kwargs(payload, ["backbone_repo", "gguf_filename", "codec_repo", "codec_device", "backbone_device"]))
    if "codec_repo" not in kwargs:
        kwargs["codec_repo"] = STANDARD_CLONE_CODEC_REPO
    if "codec_device" not in kwargs:
        kwargs["codec_device"] = STANDARD_CLONE_CODEC_DEVICE
    return vieneu_factory(**kwargs)


def _load_lora_voice(lora_repo: str, voice_name: str | None = None) -> dict | None:
    """Đọc voice dict {codes, text} từ voices.json của LoRA repo trong HF cache."""
    if not lora_repo:
        return None
    try:
        from huggingface_hub import hf_hub_download
        voices_file = hf_hub_download(
            repo_id=lora_repo,
            filename="voices.json",
            local_files_only=True,
        )
        data = json.loads(Path(voices_file).read_text(encoding="utf-8"))
        presets = data.get("presets", {})
        name = voice_name or data.get("default_voice") or next(iter(presets), None)
        if name and name in presets:
            voice = dict(presets[name])
            trim = _LORA_VOICE_TRIM.get(name)
            if trim:
                voice["codes"] = voice["codes"][: trim["codes_end"]]
                voice["text"] = trim["text"]
            return voice
    except Exception as exc:
        print(f"[lora_mode] Không đọc được voice từ {lora_repo}: {exc}", file=sys.stderr)
    return None


def _default_voice_name(lora_repo: str) -> str | None:
    """Đọc default_voice name từ voices.json của LoRA repo."""
    if not lora_repo:
        return None
    try:
        from huggingface_hub import hf_hub_download
        voices_file = hf_hub_download(
            repo_id=lora_repo,
            filename="voices.json",
            local_files_only=True,
        )
        data = json.loads(Path(voices_file).read_text(encoding="utf-8"))
        return data.get("default_voice") or next(iter(data.get("presets", {})), None)
    except Exception as exc:
        print(f"[lora_mode] Không đọc được default voice từ {lora_repo}: {exc}", file=sys.stderr)
    return None


def run_lora(tts: Any, payload: dict) -> Any:
    text = payload["text"]
    lora_repo = payload.get("lora_repo")
    voice_name = payload.get("voice_name") or _default_voice_name(lora_repo)
    voice = _load_lora_voice(lora_repo, voice_name) if lora_repo else None

    if voice:
        return tts.infer(text=text, voice=voice, **infer_kwargs(payload))

    print(
        "[lora_mode] Cảnh báo: không tải được voice từ LoRA repo. Thử infer không có voice.",
        file=sys.stderr,
    )
    return tts.infer(text=text, **infer_kwargs(payload))


def run_lora_batch(tts: Any, chunks: list[dict], base_payload: dict) -> None:
    lora_repo = base_payload.get("lora_repo")
    voice_name = base_payload.get("voice_name") or _default_voice_name(lora_repo)
    voice = _load_lora_voice(lora_repo, voice_name) if lora_repo else None

    for chunk in chunks:
        out = Path(chunk["output_path"])
        out.parent.mkdir(parents=True, exist_ok=True)
        if voice is not None:
            audio = tts.infer(text=chunk["text"], voice=voice, **infer_kwargs(base_payload))
        else:
            audio = tts.infer(text=chunk["text"], **infer_kwargs(base_payload))
        tts.save(audio, str(out))
