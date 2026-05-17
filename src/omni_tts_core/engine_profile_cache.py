from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime
from pathlib import Path

from omni_tts_core.paths import ensure_dir


class EngineProfileCache:
    """
    Persistent cache for encoded voice representations.

    Structure:
        voices/cache/{profile_id}/{sample_id}/{provider}/{model_id}/
            voice_clone_prompt.pkl   (omnivoice, qwen)
            ref_codes.npy            (vieneu turbo, standard/gguf)
            meta.json                {"audio_hash", "transcript_hash", "created_at"}

    Cache is invalidated when audio file or transcript changes (hash mismatch).
    """

    def __init__(self, cache_root: Path | None = None) -> None:
        self.cache_root = cache_root or ensure_dir("voices/cache")

    def asset_dir(
        self,
        profile_id: str,
        sample_id: str,
        provider: str,
        model_id: str,
    ) -> Path:
        sample_key = sample_id or "primary"
        return self.cache_root / profile_id / sample_key / provider / model_id

    def is_valid(self, asset_dir: Path, audio_path: Path, transcript: str) -> bool:
        meta_path = asset_dir / "meta.json"
        if not meta_path.exists():
            return False
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:
            return False
        return (
            meta.get("audio_hash") == _file_hash(audio_path)
            and meta.get("transcript_hash") == _text_hash(transcript)
        )

    def write_meta(self, asset_dir: Path, audio_path: Path, transcript: str) -> None:
        asset_dir.mkdir(parents=True, exist_ok=True)
        meta = {
            "audio_hash": _file_hash(audio_path),
            "transcript_hash": _text_hash(transcript),
            "created_at": datetime.now().isoformat(timespec="seconds"),
        }
        (asset_dir / "meta.json").write_text(
            json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    def invalidate_profile(self, profile_id: str) -> None:
        profile_dir = self.cache_root / profile_id
        if profile_dir.exists():
            shutil.rmtree(profile_dir, ignore_errors=True)


def _file_hash(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()[:16]


def _text_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]
