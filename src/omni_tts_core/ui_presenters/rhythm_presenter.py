"""What every frontend shows for Nhịp đọc: one row per pause layer.

Qt and MCP read the same view, so the badge a user sees and the plan an agent
receives always agree. Frontends never branch on provider ids.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from omni_tts_core.rhythm import (
    LAYER_GROUPS,
    RhythmPlan,
    context_for_model,
    diff_rhythm_plans,
    pause_profile_for,
    resolve_rhythm_plan,
)
from omni_tts_core.rhythm.presets import RHYTHM_PRESETS
from omni_tts_shared.narrative_pacing import NarrativePacingOptions

STATE_COLORS: dict[str, str] = {
    "model": "#4ade80",
    "app": "#60a5fa",
    "model_app_topup": "#facc15",
    "limited": "#fb923c",
    "not_applicable": "#9ca3af",
    "off": "#6b7280",
}
SCOPE_CHOICES: tuple[tuple[str, str], ...] = (
    ("Chỉ nhịp kể chuyện (giữ mục Ngắt nghỉ cũ)", "pacing_only"),
    ("Toàn bộ ngắt nghỉ (Nhịp đọc quản lý hết)", "full"),
)
PRESET_CHOICES: tuple[tuple[str, str], ...] = tuple(
    (label, preset_id) for preset_id, (label, _desc, _factory) in RHYTHM_PRESETS.items()
)
LOCK_TOOLTIP = (
    "Do Nhịp đọc quản lý (phạm vi Toàn bộ ngắt nghỉ). Tắt Nhịp đọc hoặc chọn "
    "phạm vi \"Chỉ nhịp kể chuyện\" để chỉnh lại mục này; giá trị cũ vẫn được giữ."
)
# Old Studio controls each lock name stands for.
OLD_CONTROL_LABELS: dict[str, str] = {
    "punctuation_pause_enabled": "Ngắt nghỉ theo dấu câu",
    "paragraph_pause": "Nghỉ giữa đoạn gốc",
}


@dataclass(frozen=True)
class RhythmRow:
    layer: str
    group: str
    group_label: str
    label: str
    state: str
    state_label: str
    color: str
    tooltip: str
    value_ms: tuple[int, int] | None
    # False for KHÔNG ÁP DỤNG / TẮT: the value is kept but greyed out.
    applies: bool


@dataclass(frozen=True)
class RhythmView:
    plan: RhythmPlan
    rows: tuple[RhythmRow, ...] = ()
    locked_settings: tuple[str, ...] = ()
    old_controls_locked: bool = False
    status_text: str = ""

    def row(self, layer: str) -> RhythmRow | None:
        return next((r for r in self.rows if r.layer == layer), None)

    def as_dict(self) -> dict[str, Any]:
        data = self.plan.as_dict()
        data["locked_provider_settings"] = list(self.locked_settings)
        data["status_text"] = self.status_text
        data["groups"] = dict(LAYER_GROUPS)
        return data


@dataclass
class RhythmTracker:
    """Remembers the last plan so a model switch can say what changed."""

    last: RhythmPlan | None = None
    last_model: str = ""

    def update(self, model_id: str, plan: RhythmPlan) -> list[str]:
        lines = diff_rhythm_plans(self.last, plan) if model_id != self.last_model else []
        self.last, self.last_model = plan, model_id
        return lines


def _options(pacing: NarrativePacingOptions | Mapping[str, Any] | None) -> NarrativePacingOptions:
    if isinstance(pacing, NarrativePacingOptions):
        return pacing
    try:
        return NarrativePacingOptions.model_validate(dict(pacing or {}))
    except ValueError:
        return NarrativePacingOptions()


def rhythm_view(
    pacing: NarrativePacingOptions | Mapping[str, Any] | None,
    spec: Any,
    *,
    output_mode: str = "merged",
    source_kind: str = "text",
    chunk_join_mode: str = "auto",
    runtime_target: str | None = None,
    text_has_tokens: bool = False,
) -> RhythmView:
    options = _options(pacing)
    context = context_for_model(
        spec, output_mode=output_mode, source_kind=source_kind,
        chunk_join_mode=chunk_join_mode, runtime_target=runtime_target,
        text_has_tokens=text_has_tokens,
    )
    plan = resolve_rhythm_plan(options, context)
    if not plan.enabled:
        return RhythmView(plan, status_text=plan.summary)
    rows = []
    for item in plan.layers:
        lines = [f"{item.state_label}: {item.note}".strip().rstrip(":")]
        if item.reason:
            lines.append(item.reason)
        if item.value_ms:
            low, high = item.value_ms
            lines.append(f"Mục tiêu: {_seconds(low)}s" if low == high
                         else f"Mục tiêu: {_seconds(low)}–{_seconds(high)}s")
        rows.append(RhythmRow(
            item.layer, item.group, LAYER_GROUPS[item.group], item.label, item.state,
            item.state_label, STATE_COLORS[item.state], "\n".join(lines), item.value_ms,
            item.state not in {"not_applicable", "off"},
        ))
    full = options.scope == "full"
    locked_settings = tuple(pause_profile_for(context.provider_id).locked_settings) if full else ()
    status = plan.summary
    if full:
        status += " Mục Ngắt nghỉ theo dấu câu và Nghỉ giữa đoạn gốc đang do Nhịp đọc quản lý."
    return RhythmView(plan, tuple(rows), locked_settings, full, status)


def _seconds(ms: int) -> str:
    return f"{ms / 1000:.2f}".rstrip("0").rstrip(".").replace(".", ",")
