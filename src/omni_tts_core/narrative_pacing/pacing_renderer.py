"""Apply narrative pacing to an assembled narration and return a time remap."""

from __future__ import annotations

import bisect
import random
from dataclasses import dataclass, field

import numpy as np

from omni_tts_core.narrative_pacing.audio_analysis import PacingUnit, SilenceMap
from omni_tts_core.narrative_pacing.boundary_classifier import (
    boundary_kind,
    resolve_language,
    target_pause_ms,
)
from omni_tts_core.narrative_pacing.music_bridge_mixer import (
    BridgeMusic,
    bridge_keys,
    outro_keys,
    overlay,
    theme_bed_keys,
)
from omni_tts_core.narrative_pacing.section_planner import plan_structure
from omni_tts_core.narrative_pacing.sentence_pause_aligner import plan_sentence_pauses
from omni_tts_core.rhythm.layers import has_range, sample_ms
from omni_tts_shared.errors import ConfigError
from omni_tts_shared.narrative_pacing import NarrativePacingOptions

THEME_SOLO_SECONDS = 3.5


@dataclass
class _Insert:
    time: float
    seconds: float
    kind: str
    music: dict | None = None  # clip, r0, r1, track_id, kind (theme/short/long), unit, overlaps


@dataclass
class PacingResult:
    audio: np.ndarray
    sample_rate: int
    shift_times: list[float]
    shift_totals: list[float]
    report: dict = field(default_factory=dict)

    def remap(self, seconds: float) -> float:
        i = bisect.bisect_right(self.shift_times, seconds) - 1
        return seconds + (self.shift_totals[i] if i >= 0 else 0.0)


def _length_factor(prev_text: str) -> float:
    """Readers pause longer after long paragraphs (about 0.9x short .. 1.15x long)."""
    return 0.9 + 0.25 * min(1.0, max(0.0, (len(prev_text) - 150) / 450))


def _music_insert(music: BridgeMusic, opts, plan, b: int, r0: float, r1: float, rate: int) -> dict:
    gap = r1 - r0
    if b == plan.intro_before:
        track_id = opts.theme_track_id
        return {"clip": music.clip(track_id), "track_id": track_id, "type": "theme", "solo": THEME_SOLO_SECONDS,
                "in": opts.overlap_in_ms / 1000, "out": opts.overlap_out_ms / 1000}
    pinned = opts.bridge_tracks.get(b + 1)
    if b in plan.majors_before:
        track_id, clip = ((pinned, music.clip(pinned)) if pinned
                          else music.major_bridge(f"major:{b}", closing=b == plan.closing))
        o_in, o_out = opts.major_overlap_in_ms / 1000, opts.major_overlap_out_ms / 1000
        room = len(clip) / rate - o_in - o_out - gap
        solo = max(min(opts.major_solo_ms / 1000, room), opts.min_solo_ms / 1000)
        return {"clip": clip, "track_id": track_id, "type": "long", "solo": solo, "in": o_in, "out": o_out}
    track_id, clip = (pinned, music.clip(pinned)) if pinned else music.next_bridge(f"bridge:{b}")
    o_in, o_out = opts.overlap_in_ms / 1000, opts.overlap_out_ms / 1000
    room = len(clip) / rate - o_in - o_out - gap
    solo = min(max(room, opts.min_solo_ms / 1000), max(opts.max_solo_ms, opts.min_solo_ms) / 1000)
    return {"clip": clip, "track_id": track_id, "type": "short", "solo": solo, "in": o_in, "out": o_out}


def apply_narrative_pacing(
    audio: np.ndarray, sample_rate: int, units: list[PacingUnit],
    options: NarrativePacingOptions, *, language: str = "vi", context: str = "", library=None,
    skip_layers: frozenset[str] = frozenset(),
) -> PacingResult:
    """Stretch pauses to their tier targets and mix music bridges.

    ``skip_layers``: pause layers owned elsewhere (see omni_tts_core.rhythm);
    units with ``locked_after`` keep their following boundary untouched.
    """
    if not units:
        raise ConfigError("Không có đoạn nào để xếp nhịp.")
    audio = np.asarray(audio, dtype=np.float32)
    silence = SilenceMap(audio, sample_rate)
    rng = random.Random(options.seed)
    music_opts = options.music
    language = resolve_language(language, " ".join(u.text for u in units[:40]))
    structure = plan_structure(units, options, language)
    plan, scores, sections = structure.music, structure.scores, set(structure.sections)
    music = BridgeMusic(music_opts, sample_rate, silence.speech_level_db(), context=context,
                        library=library) if music_opts.enabled else None
    inserts: list[_Insert] = []
    kinds: dict[str, int] = {}
    for b in range(1, len(units)):
        if units[b - 1].locked_after:
            kinds["locked"] = kinds.get("locked", 0) + 1
            continue
        r0, r1 = silence.boundary_gap(units[b - 1].end, units[b].start)
        cut = (r0 + r1) / 2
        if music is not None and (b == plan.intro_before or b in plan.bridges_before):
            spec = _music_insert(music, music_opts, plan, b, r0, r1, sample_rate)
            spec.update(r0=r0, r1=r1, unit=b)
            kind = "theme" if spec["type"] == "theme" else f"music_{spec['type']}"
            inserts.append(_Insert(cut, spec["solo"], kind, spec))
        else:
            kind = "section" if b in sections else boundary_kind(units[b - 1].text, units[b].text, language)
            ranged = has_range(options, kind)
            target = (sample_ms(options, kind, rng) if ranged else target_pause_ms(kind, options)) / 1000
            if options.paragraph_length_scaling and kind != "section":
                target *= _length_factor(units[b - 1].text)
            if kind != "connector" and options.jitter_ms and not ranged:
                target += rng.uniform(-options.jitter_ms, options.jitter_ms) / 1000
            extra = target - (r1 - r0)
            if extra > 0.01 and kind not in skip_layers:
                inserts.append(_Insert(cut, extra, kind))
        kinds[kind] = kinds.get(kind, 0) + 1
    if options.sentence_pauses_enabled:
        for unit in units:
            inserts += [_Insert(t, s, "sentence")
                        for t, s in plan_sentence_pauses(silence, unit, options, rng, skip_layers)]
    inserts.sort(key=lambda item: item.time)

    pieces, pos, shift = [], 0, 0.0
    shift_times, shift_totals, placed = [], [], []
    for item in inserts:
        cut = int(round(item.time * sample_rate))
        if cut < pos:
            continue
        pieces.append(audio[pos:cut])
        pos = cut
        before = shift
        samples = int(round(item.seconds * sample_rate))
        pieces.append(np.zeros(samples, dtype=np.float32))
        shift += samples / sample_rate
        shift_times.append(item.time)
        shift_totals.append(shift)
        if item.music:
            placed.append((item, before, shift))
    pieces.append(audio[pos:])
    body = np.concatenate(pieces)

    outro = None
    last_end = units[-1].end + shift
    if music is not None and music_opts.theme_track_id and music_opts.outro_enabled:
        outro = music.clip(music_opts.theme_track_id)
    pad = (len(outro) / sample_rate + 1.0) if outro is not None else 0.0
    total = np.concatenate([body, np.zeros(int(pad * sample_rate), dtype=np.float32)])

    bridges = []
    for item, before, after in placed:
        spec = item.music
        voice_end, voice_in = spec["r0"] + before, spec["r1"] + after
        start = voice_end - spec["in"]
        is_theme = spec["type"] == "theme"
        keys = (theme_bed_keys(start, voice_end, voice_in) if is_theme
                else bridge_keys(start, voice_end, voice_in, spec["out"]))
        overlay(total, spec["clip"], start, sample_rate, keys)
        heard = voice_in + (0.0 if is_theme else spec["out"]) - start
        bridges.append({"kind": "theme" if is_theme else "bridge", "length": spec["type"],
                        "before_unit": spec["unit"] + 1, "track_id": spec["track_id"],
                        "music_start_seconds": round(max(0.0, start), 3),
                        "voice_in_seconds": round(voice_in, 3), "heard_seconds": round(heard, 2),
                        "text": units[spec["unit"]].text[:80]})
    if outro is not None:
        start = last_end - music_opts.overlap_in_ms / 1000
        overlay(total, outro, start, sample_rate, outro_keys(start, last_end))
        total = total[: int((start + len(outro) / sample_rate + 0.6) * sample_rate)]
        bridges.append({"kind": "outro", "track_id": music_opts.theme_track_id,
                        "music_start_seconds": round(start, 3)})
    def remap_at(seconds: float) -> float:
        i = bisect.bisect_right(shift_times, seconds) - 1
        return seconds + (shift_totals[i] if i >= 0 else 0.0)

    peak = float(np.max(np.abs(total))) if total.size else 0.0
    if peak > 0.98:
        total *= 0.98 / peak
    report = {
        "source_seconds": round(len(audio) / sample_rate, 3),
        "paced_seconds": round(len(total) / sample_rate, 3),
        "boundary_kinds": kinds,
        "sentence_pauses_lengthened": sum(1 for i in inserts if i.kind == "sentence"),
        "sections": [
            {"before_unit": b + 1, "voice_in_seconds": round(remap_at(units[b].start), 3),
             "score": scores[b], "text": units[b].text[:80]}
            for b in sorted(sections)
        ],
        "topic_scores": scores[1:],
        "music": bridges,
    }
    return PacingResult(total, sample_rate, shift_times, shift_totals, report)
