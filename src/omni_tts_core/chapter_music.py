"""Private local music library and sample-exact, faded chapter-break cues.

No provider calls or credentials are needed when reading a book. Library media
stays in the user's ignored runtime directory, never in the distributable app.
"""

from __future__ import annotations

import hashlib
import json
import re
import tempfile
from dataclasses import asdict, dataclass, field
from functools import lru_cache
from pathlib import Path
from uuid import uuid4

import numpy as np
from filelock import FileLock

from omni_tts_core.audio.wav_tools import read_audio_mono, save_wav
from omni_tts_core.paths import PROJECT_ROOT
from omni_tts_shared.epub import ChapterMusicOptions
from omni_tts_shared.errors import ConfigError


@dataclass(frozen=True)
class MusicTrack:
    track_id: str
    name: str
    file: str
    duration_seconds: float
    sha256: str
    tags: list[str] = field(default_factory=list)
    provenance: dict = field(default_factory=dict)


def default_music_root() -> Path:
    return PROJECT_ROOT / "music_library"


class ChapterMusicLibrary:
    def __init__(self, root: Path | None = None):
        self.root = root or default_music_root()
        self.catalog = self.root / "library.json"

    def list_tracks(self) -> list[MusicTrack]:
        if not self.catalog.exists():
            return []
        try:
            data = json.loads(self.catalog.read_text(encoding="utf-8"))
            items = [MusicTrack(**item) for item in data["tracks"]]
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise ConfigError("Không đọc được thư viện nhạc chuyển chương.") from exc
        return items

    def resolve(self, track_id: str | None) -> tuple[MusicTrack, Path]:
        if not track_id:
            raise ConfigError(
                "Hãy chọn một bản nhạc trong thư viện nhạc chuyển chương."
            )
        track = next((t for t in self.list_tracks() if t.track_id == track_id), None)
        if track is None:
            raise ConfigError(
                "Bản nhạc đã chọn không còn trong thư viện. Hãy chọn lại nhạc."
            )
        path = (self.root / track.file).resolve()
        if not path.is_relative_to(self.root.resolve()) or not path.is_file():
            raise ConfigError(
                "File nhạc thư viện không tồn tại hoặc đường dẫn không hợp lệ."
            )
        return track, path

    def import_track(
        self,
        source: Path,
        name: str,
        *,
        track_id: str | None = None,
        tags: list[str] | None = None,
        provenance: dict | None = None,
    ) -> MusicTrack:
        source = Path(source)
        if not source.is_absolute() or not source.is_file():
            raise ConfigError("Nhạc nguồn phải là đường dẫn tuyệt đối tới file có sẵn.")
        if source.suffix.lower() not in {".wav", ".mp3", ".flac", ".ogg", ".m4a"}:
            raise ConfigError("Hỗ trợ nhạc WAV, MP3, FLAC, OGG hoặc M4A.")
        if source.stat().st_size > 100 * 1024 * 1024:
            raise ConfigError("File nhạc vượt giới hạn 100 MB.")
        name = name.strip()
        if not name or len(name) > 120:
            raise ConfigError("Tên nhạc cần có từ 1–120 ký tự.")
        track_id = track_id or f"music-{uuid4().hex[:12]}"
        if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,79}", track_id):
            raise ConfigError("ID nhạc không hợp lệ.")
        try:
            audio, rate = read_audio_mono(source, target_sample_rate=24000)
        except (OSError, RuntimeError, ValueError) as exc:
            raise ConfigError("Không đọc được audio nguồn.") from exc
        audio = prepare_master(audio[: rate * 30], rate)
        self.root.mkdir(parents=True, exist_ok=True)
        with FileLock(str(self.root / ".library.lock")):
            items = self.list_tracks()
            if any(t.track_id == track_id for t in items):
                raise ConfigError(
                    "ID nhạc đã có trong thư viện; dùng ID mới để giữ bản cũ."
                )
            target = self.root / f"{track_id}.wav"
            save_wav(target, audio, rate)
            track = MusicTrack(
                track_id,
                name,
                target.name,
                len(audio) / rate,
                hashlib.sha256(target.read_bytes()).hexdigest(),
                tags or [],
                provenance or {},
            )
            items.append(track)
            temp = self.catalog.with_suffix(".tmp")
            temp.write_text(
                json.dumps(
                    {"version": 1, "tracks": [asdict(t) for t in items]},
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            temp.replace(self.catalog)
        return track


def prepare_master(audio: np.ndarray, rate: int) -> np.ndarray:
    audio = np.asarray(audio, dtype=np.float32)
    if not audio.size or rate <= 0 or not np.isfinite(audio).all():
        raise ConfigError("File nhạc không có audio hợp lệ.")
    audio = audio - np.mean(audio)
    peak = float(np.max(np.abs(audio)))
    if peak < 1e-5:
        raise ConfigError("File nhạc chỉ có im lặng.")
    # Trim silence, retain a small margin around the real musical phrase.
    active = np.flatnonzero(np.abs(audio) > max(0.0001, peak * 0.008))
    first = max(0, int(active[0]) - int(rate * 0.02))
    last = min(len(audio), int(active[-1]) + int(rate * 0.08) + 1)
    audio = audio[first:last].copy()
    rms = float(np.sqrt(np.mean(audio**2)))
    gain = min(0.18 / max(rms, 1e-6), 0.85 / max(float(np.max(np.abs(audio))), 1e-6))
    audio *= gain
    return apply_fades(audio, rate, 10, 25)


def apply_fades(
    audio: np.ndarray, rate: int, fade_in_ms: int, fade_out_ms: int
) -> np.ndarray:
    audio = np.asarray(audio, dtype=np.float32).copy()
    head, tail = int(rate * fade_in_ms / 1000), int(rate * fade_out_ms / 1000)
    if head + tail > len(audio) and head + tail:
        ratio = len(audio) / (head + tail)
        head, tail = int(head * ratio), int(tail * ratio)
    if head:
        audio[:head] *= np.sin(np.linspace(0, np.pi / 2, head)) ** 2
    if tail:
        audio[-tail:] *= np.cos(np.linspace(0, np.pi / 2, tail)) ** 2
    return audio


@lru_cache(maxsize=12)
def _load_at_rate(path: str, modified_ns: int, size: int, rate: int) -> np.ndarray:
    audio, _ = read_audio_mono(Path(path), target_sample_rate=rate)
    return audio


class ChapterMusicRenderer:
    def __init__(
        self, options: ChapterMusicOptions, library: ChapterMusicLibrary | None = None
    ):
        self.options = options
        self.library = library or ChapterMusicLibrary()
        self.track, self.path = self.library.resolve(options.track_id)

    def fingerprint(self) -> str:
        return hashlib.sha256(self.path.read_bytes()).hexdigest()

    def render(self, duration_ms: int, rate: int) -> np.ndarray:
        size = int(rate * duration_ms / 1000)
        if size <= 0:
            return np.zeros(0, dtype=np.float32)
        stat = self.path.stat()
        source = _load_at_rate(str(self.path), stat.st_mtime_ns, stat.st_size, rate)
        # Trim, do not time-stretch the notes. Short masters are padded, not looped.
        result = np.zeros(size, dtype=np.float32)
        result[: min(size, len(source))] = source[:size]
        result = apply_fades(
            result, rate, self.options.fade_in_ms, self.options.fade_out_ms
        )
        result *= self.options.volume_percent / 100
        return result

    def for_boundary(self, kind: str, duration_ms: int, rate: int) -> np.ndarray | None:
        use = (kind == "chapter" and self.options.between_chapters) or (
            kind == "title" and self.options.after_title
        )
        return self.render(duration_ms, rate) if self.options.enabled and use else None


def preview_chapter_music(
    track_id: str,
    *,
    duration_ms: int = 2500,
    volume_percent: int = 30,
    fade_in_ms: int = 120,
    fade_out_ms: int = 350,
    library: ChapterMusicLibrary | None = None,
) -> Path:
    if not 1 <= duration_ms <= 10000:
        raise ConfigError("Chọn khoảng nghỉ lớn hơn 0 và tối đa 10 giây để nghe mẫu.")
    options = ChapterMusicOptions(
        enabled=True,
        track_id=track_id,
        volume_percent=volume_percent,
        fade_in_ms=fade_in_ms,
        fade_out_ms=fade_out_ms,
    )
    renderer = ChapterMusicRenderer(options, library)
    preview_root = renderer.library.root / "previews"
    preview_root.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        dir=preview_root, suffix=".wav", delete=False
    ) as f:
        path = Path(f.name)
    save_wav(path, renderer.render(duration_ms, 24000), 24000)
    return path
