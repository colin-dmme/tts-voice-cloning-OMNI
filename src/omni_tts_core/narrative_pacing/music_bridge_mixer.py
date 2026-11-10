"""Load library music at the narration's rate and mix it with dB envelopes."""

from __future__ import annotations

import hashlib

import numpy as np

from omni_tts_core.chapter_music import (
    ChapterMusicLibrary,
    ChapterMusicSelector,
    _load_at_rate,
    apply_fades,
)
from omni_tts_core.narrative_pacing.audio_analysis import active_level_db
from omni_tts_shared.epub import ChapterMusicOptions
from omni_tts_shared.errors import ConfigError
from omni_tts_shared.narrative_pacing import NarrativeMusicOptions

MUSIC_PEAK = 0.7
SILENT_DB = -45.0


class BridgeMusic:
    """Picks bridge tracks (fixed / random theme / selection / preset) and levels them."""

    def __init__(
        self,
        options: NarrativeMusicOptions,
        sample_rate: int,
        speech_db: float,
        *,
        context: str,
        library: ChapterMusicLibrary | None = None,
    ):
        self.options = options
        self.rate = sample_rate
        self.speech_db = speech_db
        self.library = library or ChapterMusicLibrary()
        selection = ChapterMusicOptions(
            enabled=True,
            selection_mode=options.selection_mode,
            track_id=options.track_id,
            preset_id=options.preset_id,
            theme=options.theme,
            random_seed=options.random_seed,
            theme_ids=options.theme_ids,
            track_ids=options.track_ids,
            excluded_track_ids=options.excluded_track_ids,
        )
        seed_context = hashlib.sha256(context.encode("utf-8")).hexdigest()[:16]
        self.seed_context = seed_context
        # Long-bridge pool, resolved up front so a missing track fails before rendering.
        if options.major_track_ids:
            self._major_pool = [self.library.resolve(t)[0] for t in options.major_track_ids]
        elif options.major_theme:
            self._major_pool = sorted(self.library.list_tracks(theme=options.major_theme), key=lambda t: t.track_id)
            if not self._major_pool:
                raise ConfigError(f"Nhóm nhạc '{options.major_theme}' chưa có nhạc cho nhạc chuyển dài.")
        else:
            self._major_pool = []
        for track_id in options.bridge_tracks.values():
            self.library.resolve(track_id)
        self._major_offset = int(seed_context, 16) % max(1, len(self._major_pool))
        self._major_count = 0
        self.selector = ChapterMusicSelector(selection, self.library, context=seed_context)
        if options.theme_track_id:
            self.library.resolve(options.theme_track_id)  # fail before rendering

    def clip(self, track_id: str) -> np.ndarray:
        _, path = self.library.resolve(track_id)
        stat = path.stat()
        audio = _load_at_rate(str(path), stat.st_mtime_ns, stat.st_size, self.rate).copy()
        gain_db = self.options.level_db + self.speech_db - active_level_db(audio, self.rate)
        audio *= 10 ** (gain_db / 20)
        peak = float(np.max(np.abs(audio))) if audio.size else 0.0
        if peak > MUSIC_PEAK:
            audio *= MUSIC_PEAK / peak
        return apply_fades(audio, self.rate, 120, 500)

    def next_bridge(self, key: str) -> tuple[str, np.ndarray]:
        track = self.selector.choose(key)
        return track.track_id, self.clip(track.track_id)

    def major_bridge(self, key: str, *, closing: bool = False) -> tuple[str, np.ndarray]:
        """Long bridge: rotate through the long pool without repeats; closing gets a "closing" track."""
        if self._major_pool:
            enders = [t for t in self._major_pool if "closing" in t.tags]
            others = [t for t in self._major_pool if "closing" not in t.tags] or self._major_pool
            if closing and enders:
                track = enders[0]
            else:
                track = others[(self._major_offset + self._major_count) % len(others)]
                self._major_count += 1
            return track.track_id, self.clip(track.track_id)
        if self.options.theme_track_id:
            return self.options.theme_track_id, self.clip(self.options.theme_track_id)
        return self.next_bridge(key)


def overlay(
    target: np.ndarray, clip: np.ndarray, start_seconds: float, rate: int,
    keys: list[tuple[float, float]],
) -> None:
    """Add clip into target at start_seconds, shaped by [(time_seconds, dB), ...]."""
    i0 = int(round(start_seconds * rate))
    if i0 < 0:
        clip, i0 = clip[-i0:], 0
    length = max(0, min(len(clip), len(target) - i0))
    if not length:
        return
    times = start_seconds + np.arange(length) / rate
    env = 10 ** (np.interp(times, [k[0] for k in keys], [k[1] for k in keys]) / 20)
    tail = min(length, int(0.08 * rate))
    if tail:
        env[-tail:] *= np.linspace(1.0, 0.0, tail)
    target[i0:i0 + length] += clip[:length] * env.astype(np.float32)


def bridge_keys(music_start: float, voice_end: float, voice_in: float, out_s: float) -> list[tuple[float, float]]:
    """Rise under the last words, full solo, sink under the next first words."""
    return [
        (music_start, -40.0), (voice_end, -15.0), (voice_end + 0.5, 0.0),
        (max(voice_end + 0.5, voice_in - 0.4), 0.0), (voice_in, -14.0), (voice_in + out_s, SILENT_DB),
    ]


def theme_bed_keys(music_start: float, voice_end: float, voice_in: float) -> list[tuple[float, float]]:
    """Series theme: solo after the hook, then a low bed under the introduction."""
    return [
        (music_start, -40.0), (voice_end, -15.0), (voice_end + 0.6, 0.0),
        (max(voice_end + 0.6, voice_in - 0.5), 0.0), (voice_in, -16.0),
        (voice_in + 6.0, -19.0), (voice_in + 11.0, -60.0),
    ]


def outro_keys(music_start: float, voice_end: float) -> list[tuple[float, float]]:
    return [(music_start, -40.0), (voice_end, -15.0), (voice_end + 0.7, 0.0), (voice_end + 600.0, 0.0)]
