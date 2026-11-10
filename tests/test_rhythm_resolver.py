from __future__ import annotations

import pytest

from omni_tts_core.model_registry import ModelRegistry
from omni_tts_core.provider_registry import PROVIDERS
from omni_tts_core.rhythm import (
    LAYERS,
    RhythmContext,
    context_for_model,
    diff_rhythm_plans,
    pause_profile_for,
    resolve_rhythm_plan,
)
from omni_tts_shared.narrative_pacing import NarrativePacingOptions

FULL = NarrativePacingOptions(enabled=True, scope="full")
FULL_MUSIC = NarrativePacingOptions(
    enabled=True, scope="full",
    music={"enabled": True, "theme_track_id": "mo-ket-van-nhan-thu-phong"},
)


def _context(provider_id: str, model_id: str = "", **kwargs) -> RhythmContext:
    descriptor = PROVIDERS.get(provider_id)
    controls = descriptor.controls if descriptor else frozenset()
    return RhythmContext(provider_id, model_id, controls=controls, **kwargs)


def _states(plan) -> dict[str, tuple[str, str]]:
    return {item.layer: (item.state, item.mechanism) for item in plan.layers}


def test_disabled_plan_is_empty_and_locks_nothing() -> None:
    plan = resolve_rhythm_plan(NarrativePacingOptions(), _context("zerotts"))
    assert not plan.enabled and plan.layers == () and plan.locked_controls == ()


@pytest.mark.parametrize("provider_id", [*PROVIDERS, "unknown_provider"])
@pytest.mark.parametrize("output_mode", ["merged", "split"])
@pytest.mark.parametrize("source_kind", ["text", "epub"])
@pytest.mark.parametrize("scope", ["pacing_only", "full"])
def test_every_layer_has_exactly_one_owner(provider_id, output_mode, source_kind, scope) -> None:
    profile = pause_profile_for(provider_id)
    switch_values = [{}] + [
        {switch.key: value} for switch in profile.switches for value, _ in switch.choices
    ]
    for switches in switch_values:
        options = NarrativePacingOptions(enabled=True, scope=scope, model_switches=switches,
                                         music={"enabled": True})
        plan = resolve_rhythm_plan(options, _context(provider_id, output_mode=output_mode,
                                                     source_kind=source_kind))
        assert [item.layer for item in plan.layers] == [spec.layer for spec in LAYERS]
        for item in plan.layers:
            if item.state in {"not_applicable", "off"}:
                assert item.mechanism == "none" and item.reason
            else:
                assert item.mechanism != "none" and item.note


def test_switching_model_never_changes_values() -> None:
    values = {
        provider: [item.value_ms for item in resolve_rhythm_plan(FULL, _context(provider)).layers]
        for provider in PROVIDERS
    }
    assert len({tuple(v) for v in values.values()}) == 1


def test_kokoro_library_mode_is_default_in_full_scope() -> None:
    plan = resolve_rhythm_plan(FULL, _context("kokoro_onnx"))
    states = _states(plan)
    assert states["comma"] == ("model", "library_param")
    assert plan.layer("comma").param == "clause_pause"
    assert states["sentence_end"] == ("model", "library_param")
    assert plan.layer("sentence_end").param == "sentence_pause"
    assert states["short_sentence"] == ("app", "app_stretch")
    assert states["paragraph"] == ("app", "app_stretch")
    assert plan.switch_value("kokoro_pause_mode") == "library"


def test_kokoro_app_split_switch() -> None:
    options = FULL.model_copy(update={"model_switches": {"kokoro_pause_mode": "app_split"}})
    states = _states(resolve_rhythm_plan(options, _context("kokoro_onnx")))
    assert states["comma"] == ("app", "app_split")
    # "?" is split with the sentence group, then topped up by the app.
    assert states["question_end"] == ("app", "app_stretch")


def test_kokoro_switch_is_inactive_in_pacing_only_scope() -> None:
    options = NarrativePacingOptions(enabled=True)
    plan = resolve_rhythm_plan(options, _context("kokoro_onnx"))
    assert plan.switch_value("kokoro_pause_mode") is None
    assert _states(plan)["comma"] == ("app", "app_stretch")
    assert plan.locked_controls == ()


def test_piper_splits_text_layers_in_full_scope() -> None:
    states = _states(resolve_rhythm_plan(FULL, _context("piper")))
    assert states["sentence_end"] == ("app", "app_split")
    assert states["connector"] == ("app", "app_stretch")


def test_zerotts_locks_segment_gap_and_flags_semicolon() -> None:
    plan = resolve_rhythm_plan(FULL, _context("zerotts"))
    states = _states(plan)
    assert states["sentence_end"] == ("model_app_topup", "library_fixed")
    assert states["clause"][0] == "limited"
    assert "segment_gap_seconds" in plan.locked_controls
    assert "punctuation_pause_enabled" in plan.locked_controls


def test_vieneu_v3_has_fixed_gaps_but_v2_does_not() -> None:
    v3 = resolve_rhythm_plan(FULL, _context("vieneu", "vieneu_v3_turbo",
                                            runtime={"vieneu_mode": "v3turbo"}))
    v2 = resolve_rhythm_plan(FULL, _context("vieneu", "vieneu_v2_turbo",
                                            runtime={"vieneu_mode": "turbo"}))
    assert _states(v3)["sentence_end"] == ("model_app_topup", "library_fixed")
    assert _states(v3)["comma"] == ("app", "app_stretch")
    assert _states(v2)["sentence_end"] == ("app", "app_stretch")
    # A sentence target below the 500 ms the model always leaves is flagged.
    short = FULL.model_copy(update={"sentence_end_pause_ms": 400})
    low = resolve_rhythm_plan(short, _context("vieneu", "vieneu_v3_turbo",
                                              runtime={"vieneu_mode": "v3turbo"}))
    assert low.layer("sentence_end").state == "limited"


def test_omnivoice_keep_long_silence_default_on_and_off_limits() -> None:
    on = resolve_rhythm_plan(FULL, _context("omnivoice"))
    off = resolve_rhythm_plan(
        FULL.model_copy(update={"model_switches": {"omnivoice_keep_long_silence": "off"}}),
        _context("omnivoice"),
    )
    assert on.switch_value("omnivoice_keep_long_silence") == "on"
    assert on.layer("sentence_end").state == "app"
    # Comma (200 ms) stays under the ~1 s clamp; targets above it are limited.
    assert off.layer("comma").state == "app"
    assert off.layer("short_sentence").state == "app"
    high = FULL.model_copy(update={"model_switches": {"omnivoice_keep_long_silence": "off"},
                                   "sentence_end_pause_ms": 1200})
    assert resolve_rhythm_plan(high, _context("omnivoice")).layer("sentence_end").state == "limited"


def test_higgs_uses_tokens_only_when_text_has_them() -> None:
    plain = resolve_rhythm_plan(FULL, _context("higgs_remote"))
    authored = resolve_rhythm_plan(FULL, _context("higgs_remote", text_has_tokens=True))
    assert _states(plain)["sentence_end"] == ("app", "app_stretch")
    assert _states(authored)["sentence_end"] == ("model", "native_token")
    assert _states(authored)["paragraph"] == ("model", "native_token")


def test_remote_workers_fall_back_to_stretching() -> None:
    plan = resolve_rhythm_plan(FULL, _context("kokoro_onnx", device_kind="remote"))
    # Remote workers take neither library params nor trimmed splits.
    assert _states(plan)["comma"] == ("app", "app_stretch")


def test_split_output_and_epub_rules() -> None:
    split = resolve_rhythm_plan(FULL_MUSIC, _context("piper", output_mode="split"))
    assert split.layer("paragraph").state == "not_applicable"
    assert split.layer("sentence_end").state == "app"
    epub = resolve_rhythm_plan(FULL_MUSIC, _context("piper", source_kind="epub"))
    assert epub.layer("section").state == "not_applicable"
    assert epub.layer("music_short").state == "not_applicable"
    assert epub.layer("paragraph").state == "app"


def test_crossfade_join_limits_sentence_layers() -> None:
    plan = resolve_rhythm_plan(FULL, _context("f5tts", chunk_join="crossfade"))
    assert plan.layer("sentence_end").state == "limited"
    assert plan.layer("comma").state == "app"


def test_user_toggles_show_as_off() -> None:
    options = FULL.model_copy(update={"sections_enabled": False})
    plan = resolve_rhythm_plan(options, _context("piper"))
    assert plan.layer("section").state == "off"
    assert plan.layer("music_short").state == "off"


def test_diff_lists_changed_layers() -> None:
    kokoro = resolve_rhythm_plan(FULL, _context("kokoro_onnx"))
    omni = resolve_rhythm_plan(FULL, _context("omnivoice"))
    lines = diff_rhythm_plans(kokoro, omni)
    assert any("Dấu phẩy" in line and "MODEL → APP" in line for line in lines)
    assert not any("Đoạn thường" in line for line in lines)
    assert diff_rhythm_plans(omni, omni) == []


def test_plan_serialises_for_mcp() -> None:
    data = resolve_rhythm_plan(FULL, _context("kokoro_onnx")).as_dict()
    assert data["switches"][0]["key"] == "kokoro_pause_mode"
    assert data["layers"][0]["state_label"] == "MODEL"


def test_context_for_every_installed_model() -> None:
    for spec in ModelRegistry().tts_models():
        plan = resolve_rhythm_plan(FULL, context_for_model(spec))
        assert plan.summary.startswith(plan.model_label)
