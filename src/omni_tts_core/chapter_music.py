"""Private local music library and sample-exact, faded chapter-break cues.

No provider calls or credentials are needed when reading a book. Library media
stays in the user's ignored runtime directory, never in the distributable app.
"""

from __future__ import annotations

import hashlib
import json
import random
import re
import tempfile
from dataclasses import asdict, dataclass, field, replace
from functools import lru_cache
from pathlib import Path
from uuid import uuid4

import numpy as np
from filelock import FileLock

from omni_tts_core.audio.wav_tools import read_audio_mono, save_wav
from omni_tts_core.paths import PROJECT_ROOT
from omni_tts_shared.epub import (
    ChapterMusicOptions,
    MusicDurationMode,
    MusicPoolSelection,
)
from omni_tts_shared.errors import ConfigError

MUSIC_THEME_LABELS = {
    "tam-quoc": "Tam Quốc",
    "kiem-hiep": "Kiếm hiệp / Võ lâm",
    "tien-hiep": "Tiên hiệp",
    "huyen-huyen": "Huyền huyễn",
    "ngon-tinh": "Ngôn tình",
    "co-phong": "Cổ phong",
    "co-trang": "Cổ trang",
    "su-thi": "Sử thi",
    "huyen-bi": "Huyền bí",
    "trung-tinh": "Trung tính",
}


def music_theme_label(theme: str) -> str:
    return MUSIC_THEME_LABELS.get(theme, theme)


def music_duration_note(mode: MusicDurationMode) -> str:
    if mode == "full_track":
        return "Phát trọn bản nhạc trong thư viện; chỗ có nhạc nghỉ theo độ dài bài, SRT tự cập nhật. Nhịp 0 vẫn tắt nhạc."
    return "Tự cắt và fade cho vừa nhịp nghỉ; thời lượng audio và SRT giữ nguyên."


@dataclass(frozen=True)
class MusicTrack:
    track_id: str
    name: str
    file: str
    duration_seconds: float
    sha256: str
    tags: list[str] = field(default_factory=list)
    provenance: dict = field(default_factory=dict)
    description: str = ""
    themes: list[str] = field(default_factory=list)


def default_music_root() -> Path:
    return PROJECT_ROOT / "music_library"


class ChapterMusicLibrary:
    def __init__(self, root: Path | None = None):
        self.root = root or default_music_root()
        self.catalog = self.root / "library.json"

    def list_tracks(
        self, *, theme: str | None = None, tag: str | None = None
    ) -> list[MusicTrack]:
        if not self.catalog.exists():
            return []
        try:
            data = json.loads(self.catalog.read_text(encoding="utf-8"))
            items = [MusicTrack(**item) for item in data["tracks"]]
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise ConfigError("Không đọc được thư viện nhạc chuyển chương.") from exc
        return [
            t
            for t in items
            if (not theme or theme in t.themes) and (not tag or tag in t.tags)
        ]

    def list_themes(self) -> list[dict]:
        counts: dict[str, int] = {}
        for track in self.list_tracks():
            for theme in set(track.themes):
                counts[theme] = counts.get(theme, 0) + 1
        return [
            {"theme": key, "name": music_theme_label(key), "count": counts[key]}
            for key in sorted(counts)
        ]

    def selection_tracks(self, selection: MusicPoolSelection) -> list[MusicTrack]:
        tracks = self.list_tracks()
        known_themes = {theme for t in tracks for theme in t.themes}
        missing = set(selection.theme_ids) - known_themes
        if missing:
            raise ConfigError("Nhóm chủ đề chưa có nhạc: " + ", ".join(sorted(missing)))
        known_ids = {t.track_id for t in tracks}
        if set(selection.track_ids) - known_ids:
            raise ConfigError(
                "Một bản nhạc đã tích không còn trong thư viện. Hãy chọn lại tập nhạc."
            )
        themes, explicit, excluded = (
            set(selection.theme_ids),
            set(selection.track_ids),
            set(selection.excluded_track_ids),
        )
        result = sorted(
            [
                t
                for t in tracks
                if (themes.intersection(t.themes) or t.track_id in explicit)
                and t.track_id not in excluded
            ],
            key=lambda t: t.track_id,
        )
        if not result:
            raise ConfigError(
                "Tập nhạc chưa có bản nào được tích chọn. Hãy chọn nhóm hoặc bản nhạc."
            )
        for track in result:
            self.track_path(track)
        return result

    def _save_catalog(self, items: list[MusicTrack]) -> None:
        # library.json is authoritative. Markdown is a readable companion for people/agents.
        self.root.mkdir(parents=True, exist_ok=True)
        temp = self.catalog.with_suffix(".tmp")
        temp.write_text(
            json.dumps(
                {"version": 2, "tracks": [asdict(t) for t in items]},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        temp.replace(self.catalog)
        lines = [
            "# Thư viện nhạc Colin TTS",
            "",
            "Dữ liệu cho AI: `library.json`. Mô tả là định hướng âm nhạc và tình huống sử dụng; agent nên nghe thử trước khi chọn.",
            "",
            "Random theo `themes`; `tags` mô tả tâm trạng, nhạc cụ và tình huống. Chưa phát nhạc nền dưới lời kể.",
            "",
        ]
        for track in items:
            lines.extend(
                [
                    f"## {track.name}",
                    "",
                    f"- ID: `{track.track_id}`",
                    f"- File: `{track.file}` ({track.duration_seconds:.3f} giây)",
                    f"- Chủ đề: {', '.join(track.themes) or 'chưa phân nhóm'}",
                    f"- Tag: {', '.join(track.tags) or 'chưa có'}",
                    f"- Mô tả: {track.description or 'Chưa có mô tả; nghe thử trước khi chọn.'}",
                    f"- Nguồn: {track.provenance.get('provider', 'user_import')}; gói tạo: {track.provenance.get('generated_plan', 'theo file nhập')}",
                    "",
                ]
            )
        note = self.root / "MUSIC_CATALOG.md"
        temporary = note.with_suffix(".tmp")
        temporary.write_text("\n".join(lines), encoding="utf-8")
        temporary.replace(note)

    @staticmethod
    def _metadata(description, themes, tags):
        if not isinstance(description, str) or len(description) > 2000:
            raise ConfigError("Mô tả nhạc tối đa 2.000 ký tự.")
        if (
            not isinstance(themes, list)
            or len(themes) > 30
            or any(
                not isinstance(x, str)
                or not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,79}", x)
                for x in themes
            )
        ):
            raise ConfigError(
                "Chủ đề nhạc cần dùng ID chữ thường không dấu, tối đa 30 chủ đề."
            )
        if (
            not isinstance(tags, list)
            or len(tags) > 60
            or any(not isinstance(x, str) or not x.strip() or len(x) > 80 for x in tags)
        ):
            raise ConfigError("Tag nhạc không hợp lệ.")
        return (
            description.strip(),
            list(dict.fromkeys(themes)),
            list(dict.fromkeys(tags)),
        )

    def update_metadata(
        self,
        track_id: str,
        *,
        name: str | None = None,
        description: str | None = None,
        themes: list[str] | None = None,
        tags: list[str] | None = None,
    ) -> MusicTrack:
        self.resolve(track_id)
        with FileLock(str(self.root / ".library.lock")):
            items = self.list_tracks()
            track, _ = self.resolve(track_id)
            text, groups, labels = self._metadata(
                track.description if description is None else description,
                track.themes if themes is None else themes,
                track.tags if tags is None else tags,
            )
            title = track.name if name is None else name.strip()
            if not title or len(title) > 120:
                raise ConfigError("Tên nhạc cần có từ 1–120 ký tự.")
            updated = replace(
                track, name=title, description=text, themes=groups, tags=labels
            )
            self._save_catalog(
                [updated if t.track_id == track_id else t for t in items]
            )
            return updated

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
        return track, self.track_path(track)

    def track_path(self, track: MusicTrack) -> Path:
        path = (self.root / track.file).resolve()
        if not path.is_relative_to(self.root.resolve()) or not path.is_file():
            raise ConfigError(
                "File nhạc thư viện không tồn tại hoặc đường dẫn không hợp lệ."
            )
        return path

    def import_track(
        self,
        source: Path,
        name: str,
        *,
        track_id: str | None = None,
        tags: list[str] | None = None,
        provenance: dict | None = None,
        description: str = "",
        themes: list[str] | None = None,
    ) -> MusicTrack:
        source = Path(source)
        if not source.is_absolute() or not source.is_file():
            raise ConfigError("Nhạc nguồn phải là đường dẫn tuyệt đối tới file có sẵn.")
        if source.suffix.lower() not in {".wav", ".mp3", ".flac", ".ogg", ".m4a"}:
            raise ConfigError("Hỗ trợ nhạc WAV, MP3, FLAC, OGG hoặc M4A.")
        if source.stat().st_size > 100 * 1024 * 1024:
            raise ConfigError("File nhạc vượt giới hạn 100 MB.")
        name = name.strip()
        description, themes, tags = self._metadata(
            description, themes or [], tags or []
        )
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
                description,
                themes,
            )
            items.append(track)
            self._save_catalog(items)
        return track


class ChapterMusicSelector:
    """Stable shuffle bags scoped to a book; explicit agent selections take precedence."""

    def __init__(
        self, options: ChapterMusicOptions, library=None, *, context: str = ""
    ):
        self.options = options
        self.library = library or ChapterMusicLibrary()
        self.preset = None
        if options.selection_mode == "preset":
            from omni_tts_core.music_presets import MusicPresetStore

            self.preset = MusicPresetStore(self.library).get(options.preset_id)
            self.pool = self.library.selection_tracks(self.preset)
        elif options.selection_mode == "random_selection":
            self.pool = self.library.selection_tracks(options)
        elif options.selection_mode == "random_theme":
            if not options.theme:
                raise ConfigError("Hãy chọn chủ đề để random nhạc.")
            self.pool = sorted(
                self.library.list_tracks(theme=options.theme), key=lambda t: t.track_id
            )
            if not self.pool:
                raise ConfigError(
                    f"Chủ đề '{options.theme}' chưa có nhạc; hãy thêm nhạc hoặc chọn nhóm khác."
                )
        else:
            self.pool = [self.library.resolve(options.track_id)[0]]
        # Fail before TTS if any selected source or explicit override has disappeared.
        for track in self.pool:
            self.library.track_path(track)
        for track_id in options.track_overrides.values():
            self.library.resolve(track_id)
        self.rng = random.Random(
            hashlib.sha256(f"{context}:{options.random_seed}".encode()).digest()
        )
        self.bag: list[MusicTrack] = []
        self.previous: str | None = None

    def choose(self, key: str) -> MusicTrack:
        override = self.options.track_overrides.get(key)
        if override:
            track = self.library.resolve(override)[0]
            self.bag = [t for t in self.bag if t.track_id != track.track_id]
        elif self.options.selection_mode == "fixed":
            track = self.pool[0]
        else:
            if not self.bag:
                self.bag = self.pool.copy()
                self.rng.shuffle(self.bag)
            if len(self.bag) > 1 and self.bag[-1].track_id == self.previous:
                self.bag[0], self.bag[-1] = self.bag[-1], self.bag[0]
            track = self.bag.pop()
        self.previous = track.track_id
        return track

    def fingerprint(self) -> str:
        # Metadata hashes are immutable for imported files. Cosmetic preset/track
        # edits do not invalidate a completed queue, while changed candidates do.
        return hashlib.sha256(
            json.dumps(
                [(t.track_id, t.sha256) for t in self.pool], sort_keys=True
            ).encode()
        ).hexdigest()


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
        self.selector = ChapterMusicSelector(options, self.library)
        self.track, self.path = self.library.resolve(self.selector.pool[0].track_id)

    def fingerprint(self) -> str:
        return hashlib.sha256(self.path.read_bytes()).hexdigest()

    def render(
        self, duration_ms: int, rate: int, *, track_id: str | None = None
    ) -> np.ndarray:
        full_track = self.options.duration_mode == "full_track"
        if not full_track and duration_ms <= 0:
            return np.zeros(0, dtype=np.float32)
        path = self.library.resolve(track_id)[1] if track_id else self.path
        stat = path.stat()
        source = _load_at_rate(str(path), stat.st_mtime_ns, stat.st_size, rate)
        size = len(source) if full_track else int(rate * duration_ms / 1000)
        # Trim, do not time-stretch the notes. Short masters are padded, not looped.
        result = np.zeros(size, dtype=np.float32)
        result[: min(size, len(source))] = source[:size]
        result = apply_fades(
            result, rate, self.options.fade_in_ms, self.options.fade_out_ms
        )
        result *= self.options.volume_percent / 100
        return result

    def for_boundary(
        self, kind: str, duration_ms: int, rate: int, *, track_id: str | None = None
    ) -> np.ndarray | None:
        use = (kind == "chapter" and self.options.between_chapters) or (
            kind == "title" and self.options.after_title
        )
        if not self.options.enabled or not use or duration_ms <= 0:
            return None
        selected = track_id or self.selector.choose(kind).track_id
        return self.render(duration_ms, rate, track_id=selected)


def preview_chapter_music(
    track_id: str,
    *,
    duration_ms: int = 2500,
    volume_percent: int = 30,
    fade_in_ms: int = 120,
    fade_out_ms: int = 350,
    duration_mode: MusicDurationMode = "fit_pause",
    library: ChapterMusicLibrary | None = None,
) -> Path:
    if duration_mode == "fit_pause" and not 1 <= duration_ms <= 10000:
        raise ConfigError("Chọn khoảng nghỉ lớn hơn 0 và tối đa 10 giây để nghe mẫu.")
    options = ChapterMusicOptions(
        enabled=True,
        track_id=track_id,
        volume_percent=volume_percent,
        fade_in_ms=fade_in_ms,
        fade_out_ms=fade_out_ms,
        duration_mode=duration_mode,
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
