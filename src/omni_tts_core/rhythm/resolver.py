"""Resolve which side owns each pause layer for the chosen model and job.

Exactly one owner per layer, by priority: model token, library parameter, app
split, app stretch. The plan carries plain-language explanations so Qt and MCP
show the same thing.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Literal

from omni_tts_core.rhythm.capabilities import (
    LayerCapability,
    Mechanism,
    PauseProfile,
    RhythmSwitch,
    pause_profile_for,
)
from omni_tts_core.rhythm.layers import LAYERS, LayerSpec, layer_range
from omni_tts_shared.narrative_pacing import NarrativePacingOptions

State = Literal["model", "app", "model_app_topup", "limited", "not_applicable", "off"]

STATE_LABELS: dict[str, str] = {
    "model": "MODEL",
    "app": "APP",
    "model_app_topup": "MODEL TỰ LO + APP BÙ",
    "limited": "GIỚI HẠN",
    "not_applicable": "KHÔNG ÁP DỤNG",
    "off": "TẮT",
}
_MECHANISM_NOTES: dict[str, str] = {
    "native_token": "Chèn token nghỉ vào văn bản cho model tự nghỉ.",
    "library_param": "Truyền mức nghỉ vào tham số `{param}` của thư viện model.",
    "library_fixed": "Model tự chèn khoảng {fixed}s (không chỉnh được); app chỉ bù phần còn thiếu.",
    "app_split": "App cắt câu tại dấu này, đọc từng phần rồi chèn lặng cho đủ.",
    "app_stretch": "Model đọc liền; app giãn khoảng lặng có sẵn cho đủ sau khi ghép.",
    "none": "",
}
# Old controls replaced by Nhịp đọc when it owns every layer.
_OLD_PAUSE_CONTROLS = ("punctuation_pause_enabled", "paragraph_pause")
_SPLIT_LOCKED_LAYERS = {"in_sentence", "sentence_end"}


@dataclass(frozen=True)
class RhythmContext:
    """What the job looks like; everything that is not the user's values."""

    provider_id: str
    model_id: str = ""
    provider_label: str = ""
    model_label: str = ""
    runtime: Mapping[str, Any] = field(default_factory=dict)
    controls: frozenset[str] = frozenset()
    output_mode: Literal["merged", "split"] = "merged"
    source_kind: Literal["text", "epub"] = "text"
    # Effective chunk join (see chunk_join.EffectiveChunkJoin).
    chunk_join: str = "native"
    device_kind: Literal["local", "remote"] = "local"
    text_has_tokens: bool = False


@dataclass(frozen=True)
class LayerResolution:
    layer: str
    group: str
    label: str
    state: State
    mechanism: Mechanism
    value_ms: tuple[int, int] | None
    note: str
    reason: str = ""
    param: str | None = None

    @property
    def state_label(self) -> str:
        return STATE_LABELS[self.state]

    def as_dict(self) -> dict[str, Any]:
        return {
            "layer": self.layer, "group": self.group, "label": self.label,
            "state": self.state, "state_label": self.state_label,
            "mechanism": self.mechanism,
            "value_ms": list(self.value_ms) if self.value_ms else None,
            "note": self.note, "reason": self.reason, "param": self.param,
        }


@dataclass(frozen=True)
class SwitchState:
    switch: RhythmSwitch
    value: str
    active: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "key": self.switch.key, "label": self.switch.label, "value": self.value,
            "default": self.switch.default, "active": self.active,
            "choices": [{"value": v, "label": label} for v, label in self.switch.choices],
            "help": self.switch.help,
        }


@dataclass(frozen=True)
class RhythmPlan:
    enabled: bool
    scope: str
    provider_label: str
    model_label: str
    layers: tuple[LayerResolution, ...] = ()
    switches: tuple[SwitchState, ...] = ()
    locked_controls: tuple[str, ...] = ()
    summary: str = ""

    def layer(self, layer: str) -> LayerResolution | None:
        return next((item for item in self.layers if item.layer == layer), None)

    def owned_by(self, *mechanisms: str) -> tuple[str, ...]:
        return tuple(item.layer for item in self.layers
                     if item.mechanism in mechanisms and item.state not in {"not_applicable", "off"})

    def switch_value(self, key: str) -> str | None:
        return next((s.value for s in self.switches if s.switch.key == key and s.active), None)

    def as_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled, "scope": self.scope,
            "provider": self.provider_label, "model": self.model_label,
            "summary": self.summary,
            "layers": [item.as_dict() for item in self.layers],
            "switches": [item.as_dict() for item in self.switches],
            "locked_controls": list(self.locked_controls),
        }


def context_for_model(
    spec: Any,
    *,
    output_mode: str = "merged",
    source_kind: str = "text",
    chunk_join_mode: str = "auto",
    runtime_target: str | None = None,
    text_has_tokens: bool = False,
) -> RhythmContext:
    """Build the context from a ModelSpec and the job settings."""
    from omni_tts_core.chunk_join import resolve_chunk_join_policy
    from omni_tts_core.provider_registry import provider_descriptor

    descriptor = provider_descriptor(spec.provider)
    join = resolve_chunk_join_policy(chunk_join_mode, descriptor)
    return RhythmContext(
        provider_id=spec.provider,
        model_id=spec.model_id,
        provider_label=descriptor.label if descriptor else spec.provider,
        model_label=getattr(spec, "display_name", "") or spec.model_id,
        runtime=dict(getattr(spec, "runtime", {}) or {}),
        controls=descriptor.controls if descriptor else frozenset(),
        output_mode="split" if output_mode == "split" else "merged",
        source_kind="epub" if source_kind == "epub" else "text",
        chunk_join=join.effective,
        device_kind="remote" if runtime_target == "remote" else "local",
        text_has_tokens=text_has_tokens,
    )


def resolve_rhythm_plan(options: NarrativePacingOptions, context: RhythmContext) -> RhythmPlan:
    provider = context.provider_label or context.provider_id
    model = context.model_label or context.model_id
    if not options.enabled:
        return RhythmPlan(False, options.scope, provider, model,
                          summary="Nhịp đọc đang tắt: dùng các cài đặt ngắt nghỉ cũ.")
    profile = pause_profile_for(context.provider_id)
    switches = _switch_states(profile, options)
    layers = tuple(
        _resolve_layer(spec, options, context, _capability(profile, spec.layer, context, switches))
        for spec in LAYERS
    )
    locked: tuple[str, ...] = ()
    if options.scope == "full":
        locked = (*_OLD_PAUSE_CONTROLS, *profile.locked_settings)
    return RhythmPlan(True, options.scope, provider, model, layers, switches, locked,
                      _summary(model or provider, layers))


def diff_rhythm_plans(old: RhythmPlan | None, new: RhythmPlan) -> list[str]:
    """Plain lines describing layers whose state or owner changed."""
    if old is None or not old.enabled or not new.enabled:
        return []
    before = {item.layer: item for item in old.layers}
    changes: dict[tuple[str, str, str], list[str]] = {}
    for item in new.layers:
        prev = before.get(item.layer)
        if prev is None or (prev.state, prev.mechanism) == (item.state, item.mechanism):
            continue
        key = (prev.state_label, item.state_label, item.reason or item.note)
        changes.setdefault(key, []).append(item.label)
    lines = []
    for (was, now, why), labels in changes.items():
        line = f"{' · '.join(labels)}: {was} → {now}"
        lines.append(f"{line} ({why})" if why and now != was else line)
    return lines


def _switch_states(profile: PauseProfile, options: NarrativePacingOptions) -> tuple[SwitchState, ...]:
    states = []
    for switch in profile.switches:
        allowed = {value for value, _ in switch.choices}
        value = options.model_switches.get(switch.key, switch.default)
        if value not in allowed:
            value = switch.default
        states.append(SwitchState(switch, value, options.scope in switch.scopes))
    return tuple(states)


def _capability(profile: PauseProfile, layer: str, context: RhythmContext,
                switches: tuple[SwitchState, ...]) -> LayerCapability:
    capability = profile.capability(layer, context.model_id, context.runtime)
    for state in switches:
        if state.active:
            capability = state.switch.effects.get(state.value, {}).get(layer, capability)
    return capability


def _off_reason(spec: LayerSpec, options: NarrativePacingOptions) -> str:
    music = options.music
    if spec.group == "music":
        if not music.enabled:
            return "Nhạc chuyển đang tắt."
        if spec.layer == "music_theme" and not music.theme_track_id:
            return "Chưa chọn nhạc mở / kết series."
        if spec.layer == "music_long" and not music.major_enabled:
            return "Nhạc chuyển dài đang tắt."
    if spec.layer == "section" and not options.sections_enabled:
        return "Tầng chuyển mục đang tắt."
    if spec.group in {"in_sentence", "sentence_end"} and not options.sentence_pauses_enabled:
        return "Nghỉ trong đoạn đang tắt."
    if spec.layer == "comma" and options.comma_min_pause_ms == 0:
        return "Dấu phẩy để 0: giữ nguyên nhịp model."
    return ""


def _not_applicable_reason(spec: LayerSpec, context: RhythmContext) -> str:
    if context.output_mode == "split" and spec.group in {"between_paragraphs", "music"}:
        return "Xuất tách từng đoạn: không có chỗ nối giữa các đoạn."
    if context.source_kind == "epub" and (spec.layer == "section" or spec.group == "music"):
        return "Chương, cảnh và nhạc chương do mục EPUB quản lý."
    return ""


def _pick(capability: LayerCapability, spec: LayerSpec, context: RhythmContext,
          scope: str) -> Mechanism:
    for mechanism in capability.mechanisms:
        if mechanism == "native_token" and not context.text_has_tokens:
            continue
        if mechanism == "library_param" and (
            scope != "full" or (context.device_kind == "remote" and not capability.remote_ok)
        ):
            continue
        if mechanism == "app_split" and (
            scope != "full" or "punctuation_pauses" not in context.controls
            or spec.group not in _SPLIT_LOCKED_LAYERS
            or (context.device_kind == "remote" and not capability.remote_ok)
        ):
            continue
        return mechanism
    return "app_stretch"


def _resolve_layer(spec: LayerSpec, options: NarrativePacingOptions, context: RhythmContext,
                   capability: LayerCapability) -> LayerResolution:
    value = layer_range(options, spec.layer)

    def make(state: State, mechanism: Mechanism, note: str, reason: str = "",
             param: str | None = None) -> LayerResolution:
        return LayerResolution(spec.layer, spec.group, spec.label, state, mechanism,
                               value, note, reason, param)

    if reason := _not_applicable_reason(spec, context):
        return make("not_applicable", "none", "", reason)
    if reason := _off_reason(spec, options):
        return make("off", "none", "", reason)
    if spec.group == "music":
        return make("app", "app_stretch", "App mở khoảng lặng rồi trộn nhạc giao thoa vào.")
    mechanism = _pick(capability, spec, context, options.scope)
    note = _MECHANISM_NOTES[mechanism].format(
        param=capability.param or "", fixed=_seconds(capability.fixed_ms or 0),
    )
    # A profile note describes its preferred mechanism; skip it on fallback.
    if capability.note and mechanism == capability.mechanisms[0]:
        note = f"{note} {capability.note}"
    if options.scope == "pacing_only" and spec.group in _SPLIT_LOCKED_LAYERS:
        note = f"{note} Cộng sau mục Ngắt nghỉ theo dấu câu (phạm vi chỉ nhịp kể chuyện)."
    reason = _limit_reason(spec, capability, context, value)
    if reason:
        return make("limited", mechanism, note, reason, capability.param)
    if mechanism in {"native_token", "library_param"}:
        return make("model", mechanism, note, param=capability.param)
    if mechanism == "library_fixed":
        return make("model_app_topup", mechanism, note)
    return make("app", mechanism, note)


def _limit_reason(spec: LayerSpec, capability: LayerCapability, context: RhythmContext,
                  value: tuple[int, int] | None) -> str:
    reasons = []
    if capability.limit and (
        capability.limit_max_ms is None or (value is not None and value[1] > capability.limit_max_ms)
    ):
        reasons.append(capability.limit)
    if (spec.group in _SPLIT_LOCKED_LAYERS and spec.layer != "comma"
            and context.chunk_join in {"crossfade", "direct"}):
        reasons.append("Điểm nối chunk kiểu crossfade/nối thẳng không có khoảng lặng; "
                       "app chỉ giãn được chỗ model tự ngắt.")
    if (capability.fixed_ms and value is not None and value[1] < capability.fixed_ms
            and "library_fixed" in capability.mechanisms):
        reasons.append(f"Model luôn nghỉ khoảng {_seconds(capability.fixed_ms)}s; "
                       "app không rút ngắn được.")
    return " ".join(reasons)


def _summary(name: str, layers: tuple[LayerResolution, ...]) -> str:
    counts: dict[str, int] = {}
    for item in layers:
        counts[item.state] = counts.get(item.state, 0) + 1
    order = ("model", "model_app_topup", "app", "limited", "not_applicable", "off")
    parts = [f"{counts[s]} {STATE_LABELS[s]}" for s in order if counts.get(s)]
    return f"{name}: " + ", ".join(parts) + "."


def _seconds(ms: int) -> str:
    return f"{ms / 1000:.2f}".rstrip("0").rstrip(".").replace(".", ",")
