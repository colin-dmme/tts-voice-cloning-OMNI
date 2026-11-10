from __future__ import annotations

import random
from types import SimpleNamespace

import numpy as np
import pytest

from omni_tts_core.narrative_pacing.audio_analysis import PacingUnit, SilenceMap
from omni_tts_core.narrative_pacing.merged_output_pacing import stretch_sentence_pauses
from omni_tts_core.narrative_pacing.pacing_renderer import apply_narrative_pacing
from omni_tts_core.narrative_pacing.sentence_pause_aligner import plan_sentence_pauses
from omni_tts_core.rhythm.execution import prepare_rhythm
from omni_tts_core.rhythm.layers import layer_range
from omni_tts_core.rhythm.presets import apply_rhythm_preset, rhythm_from_legacy
from omni_tts_core.rhythm.silence_tools import tidy_silences, trim_edges
from omni_tts_shared.narrative_pacing import NarrativePacingOptions
from omni_tts_shared.schemas import GenerateSpeechRequest

RATE = 24000
TEXT = "Câu thứ nhất khá dài để đọc. Câu thứ hai, có dấu phẩy, cũng dài như vậy. Câu ba ở đây."


def spec(provider: str, model_id: str = "m", **runtime):
    return SimpleNamespace(provider=provider, model_id=model_id, display_name=model_id, runtime=runtime)


def request(scope: str = "full", **kwargs) -> GenerateSpeechRequest:
    pacing = NarrativePacingOptions(enabled=True, scope=scope, **kwargs.pop("pacing", {}))
    return GenerateSpeechRequest(text=TEXT, model_id="m", output_mode="merged",
                                 narrative_pacing=pacing, paragraph_pause_ms=280, **kwargs)


def tone(seconds: float) -> np.ndarray:
    t = np.arange(int(seconds * RATE)) / RATE
    return (0.3 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)


def speech_with_gaps(gaps: list[float], speech: float = 1.5) -> np.ndarray:
    parts = [tone(speech)]
    for gap in gaps:
        parts += [np.zeros(int(gap * RATE), dtype=np.float32), tone(speech)]
    return np.concatenate(parts)


# ---- settings (phase 2) -------------------------------------------------

def test_layer_ranges_validate_and_read() -> None:
    options = NarrativePacingOptions(layer_ranges={"sentence_end": [450, 600]})
    assert layer_range(options, "sentence_end") == (450, 600)
    assert layer_range(options, "comma") == (200, 200)
    with pytest.raises(ValueError):
        NarrativePacingOptions(layer_ranges={"sentence_end": [700, 600]})
    with pytest.raises(ValueError):
        NarrativePacingOptions(layer_ranges={"music_short": [1, 2]})


def test_preset_keeps_switches_and_scope() -> None:
    options = NarrativePacingOptions(enabled=True, scope="full", model_switches={"kokoro_pause_mode": "app_split"})
    slow = apply_rhythm_preset(options, "audiobook")
    assert slow.scope == "full" and slow.model_switches == {"kokoro_pause_mode": "app_split"}
    assert layer_range(slow, "sentence_end") == (650, 750)
    assert layer_range(slow, "paragraph")[0] > layer_range(options, "paragraph")[0]
    assert layer_range(apply_rhythm_preset(slow, "podcast"), "sentence_end") == (520, 520)


def test_legacy_conversion_adds_natural_pause() -> None:
    ranges = rhythm_from_legacy({
        "punctuation_pause_enabled": True, "sentence_pause_ms": 320, "comma_pause_ms": 90,
        "clause_pause_ms": 180, "ellipsis_pause_ms": 450,
        "paragraph_pause_random_enabled": True, "paragraph_pause_min_ms": 500, "paragraph_pause_max_ms": 700,
    })
    assert ranges["sentence_end"] == [620, 620]
    assert ranges["comma"] == [240, 240]
    assert ranges["paragraph"] == [500, 700]
    assert "comma" not in rhythm_from_legacy({"punctuation_pause_enabled": False})


# ---- execution (phase 3) ------------------------------------------------

def test_disabled_rhythm_leaves_request_untouched() -> None:
    plain = GenerateSpeechRequest(text=TEXT, model_id="m", provider_options={"segment_gap_seconds": 0.3})
    execution = prepare_rhythm(plain, spec("zerotts"))
    assert execution.request is plain and not execution.pacing_active and execution.engine_options == {}


def test_pacing_only_scope_keeps_old_settings() -> None:
    req = request("pacing_only", punctuation_pause_enabled=True, provider_options={"segment_gap_seconds": 0.3})
    execution = prepare_rhythm(req, spec("piper"))
    assert execution.request is req and execution.skip_layers == frozenset()


def test_piper_full_scope_drives_punctuation_split() -> None:
    req = request(pacing={"layer_ranges": {"sentence_end": [480, 560]}})
    execution = prepare_rhythm(req, spec("piper"))
    out = execution.request
    assert out.punctuation_pause_enabled
    assert (out.sentence_pause_random_enabled, out.sentence_pause_min_ms, out.sentence_pause_max_ms) == (True, 480, 560)
    assert out.comma_pause_ms == 200 and not out.comma_pause_random_enabled
    assert out.paragraph_pause_ms == 0 and not out.paragraph_pause_random_enabled
    assert {"sentence_end", "comma", "clause"} <= execution.skip_layers
    assert "question_end" not in execution.skip_layers


def test_zerotts_full_scope_drops_locked_setting_and_split() -> None:
    req = request(punctuation_pause_enabled=True,
                  provider_options={"segment_gap_seconds": 0.4, "normalize_vi_text": True})
    out = prepare_rhythm(req, spec("zerotts")).request
    assert out.provider_options == {"normalize_vi_text": True}
    assert not out.punctuation_pause_enabled


def test_kokoro_library_mode_sets_engine_pauses() -> None:
    req = request(pacing={"layer_ranges": {"sentence_end": [500, 700]}})
    execution = prepare_rhythm(req, spec("kokoro_onnx"))
    assert not execution.request.punctuation_pause_enabled
    # sentence_end 500–700, question 620, ellipsis 550 -> midpoint of 500..700
    assert execution.engine_options["sentence_pause"] == pytest.approx(0.6)
    # comma 200, clause 380 -> 0.29 s
    assert execution.engine_options["clause_pause"] == pytest.approx(0.29)
    assert execution.request.chunk_pause_ms == 600
    assert {"comma", "sentence_end", "question_end"} <= execution.skip_layers


def test_kokoro_app_split_mode() -> None:
    req = request(pacing={"model_switches": {"kokoro_pause_mode": "app_split"}})
    execution = prepare_rhythm(req, spec("kokoro_onnx"))
    assert execution.request.punctuation_pause_enabled
    assert "sentence_pause" not in execution.engine_options


@pytest.mark.parametrize("scope", ["pacing_only", "full"])
def test_omnivoice_keeps_long_silence_by_default(scope) -> None:
    execution = prepare_rhythm(request(scope), spec("omnivoice"))
    assert execution.engine_options == {"postprocess_output": False}
    off = request(scope, pacing={"model_switches": {"omnivoice_keep_long_silence": "off"}})
    assert prepare_rhythm(off, spec("omnivoice")).engine_options == {}


def test_epub_turns_off_sections_and_music() -> None:
    req = request(pacing={"music": {"enabled": True}})
    execution = prepare_rhythm(req, spec("piper"), source_kind="epub")
    assert not execution.pacing_options.music.enabled
    assert not execution.pacing_options.sections_enabled
    assert execution.plan.layer("paragraph").state == "app"


# ---- renderer behaviour -------------------------------------------------

def test_locked_boundary_is_left_alone() -> None:
    audio = speech_with_gaps([0.3, 0.3], speech=4.0)
    units = [PacingUnit(0.0, 4.0, "Một" + " chữ" * 40 + "."), PacingUnit(4.3, 8.3, "Hai" + " chữ" * 40 + "."),
             PacingUnit(8.6, 12.6, "Ba" + " chữ" * 40 + ".")]
    options = NarrativePacingOptions(enabled=True, sentence_pauses_enabled=False, sections_enabled=False)
    free = apply_narrative_pacing(audio, RATE, units, options)
    locked = [units[0], PacingUnit(4.3, 8.3, units[1].text, locked_after=True), units[2]]
    held = apply_narrative_pacing(audio, RATE, locked, options)
    assert held.report["boundary_kinds"]["locked"] == 1
    assert len(held.audio) < len(free.audio)


def test_skip_layers_and_ranges_in_sentence_pauses() -> None:
    audio = speech_with_gaps([0.15, 0.15])
    silence = SilenceMap(audio, RATE)
    unit = PacingUnit(0.0, len(audio) / RATE, "Một câu dài có chữ. Câu thứ hai cũng dài. Hết.")
    ranged = NarrativePacingOptions(layer_ranges={"sentence_end": [800, 900]}, short_sentence_pause_ms=0)
    inserts = plan_sentence_pauses(silence, unit, ranged, random.Random(3))
    assert inserts and all(0.8 - 0.15 - 0.01 <= extra <= 0.9 - 0.15 + 0.01 for _, extra in inserts)
    assert plan_sentence_pauses(silence, unit, ranged, random.Random(3), frozenset({"sentence_end"})) == []


def test_split_file_stretch_is_deterministic() -> None:
    audio = speech_with_gaps([0.15, 0.15])
    text = "Một câu dài có chữ. Câu thứ hai cũng dài. Hết."
    options = NarrativePacingOptions(enabled=True, scope="full")
    first = stretch_sentence_pauses(audio, RATE, text, options, seed=5)
    assert len(first) > len(audio)
    assert np.array_equal(first, stretch_sentence_pauses(audio, RATE, text, options, seed=5))


def test_tidy_silences_shortens_only_stalls() -> None:
    audio = np.concatenate([np.zeros(RATE), speech_with_gaps([0.8, 3.0]), np.zeros(RATE)])
    tidy = tidy_silences(audio, RATE)
    seconds = len(tidy) / RATE
    # 3 x 1.5 s speech + 0.8 s pause kept + stall cut to 0.9 s + 2 x 0.1 s edges
    assert seconds == pytest.approx(4.5 + 0.8 + 0.9 + 0.2, abs=0.05)


def test_trim_edges_only_on_joined_sides() -> None:
    piece = np.concatenate([np.zeros(RATE // 2), tone(1.0), np.zeros(RATE // 2)])
    both = trim_edges(piece, RATE, lead=True, tail=True)
    assert len(both) / RATE == pytest.approx(1.04, abs=0.02)
    tail_only = trim_edges(piece, RATE, lead=False, tail=True)
    assert len(tail_only) / RATE == pytest.approx(1.52, abs=0.02)


def test_mcp_job_result_carries_rhythm_plan(tmp_path) -> None:
    import json

    from colin_studio_tts_mcp.job_manager import _with_rhythm_plan

    report = tmp_path / "pacing_report.json"
    report.write_text(json.dumps({"rhythm_plan": {"scope": "full"}}), encoding="utf-8")
    assert _with_rhythm_plan({"pacing_report_path": str(report)})["rhythm_plan"] == {"scope": "full"}
    nested = _with_rhythm_plan({"result": {"pacing_report_path": str(report)}})
    assert nested["result"]["rhythm_plan"] == {"scope": "full"}
    assert "rhythm_plan" not in _with_rhythm_plan({"pacing_report_path": None})
