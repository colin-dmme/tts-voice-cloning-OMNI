from __future__ import annotations

import re
from dataclasses import dataclass

from omni_tts_core.authoring.schemas import (
    AuthoringBrief,
    PerformanceDecision,
    PerformancePlan,
)
from omni_tts_core.higgs.authoring_catalog import (
    EMOTIONS,
    SOUND_EFFECTS,
    STYLES,
)
from omni_tts_core.higgs.script import validate_higgs_script

PACE_VALUES = {"default", "very_slow", "slow", "fast", "very_fast"}
PITCH_VALUES = {"default", "low", "high"}
EXPRESSIVENESS_VALUES = {"default", "low", "high"}
PAUSE_VALUES = {"none", "short", "long"}


@dataclass(frozen=True)
class SentenceSpan:
    index: int
    start: int
    end: int
    text: str


def sentence_spans(text: str) -> list[SentenceSpan]:
    """Split for annotation while retaining every original character."""

    if not text:
        return []
    ends = [match.end() for match in re.finditer(r"[.!?…]+(?=\s|$)", text)]
    if not ends or ends[-1] < len(text):
        ends.append(len(text))
    spans: list[SentenceSpan] = []
    start = 0
    for end in ends:
        chunk = text[start:end]
        if chunk.strip():
            spans.append(SentenceSpan(len(spans), start, end, chunk))
        elif spans:
            previous = spans[-1]
            spans[-1] = SentenceSpan(
                previous.index,
                previous.start,
                end,
                text[previous.start:end],
            )
        start = end
    return spans


class HiggsDialectAdapter:
    dialect_id = "higgs_v1"

    def render(
        self,
        source_text: str,
        plan: PerformancePlan,
        brief: AuthoringBrief,
    ) -> tuple[str, list[str]]:
        spans = sentence_spans(source_text)
        warnings: list[str] = []
        decision_map: dict[int, PerformanceDecision] = {}
        for decision in plan.decisions:
            if decision.sentence_index >= len(spans):
                warnings.append(
                    f"Bỏ chỉ dẫn cho câu {decision.sentence_index + 1}: ngoài phạm vi."
                )
                continue
            if decision.sentence_index in decision_map:
                warnings.append(
                    f"Câu {decision.sentence_index + 1} có nhiều chỉ dẫn; chỉ dùng bản đầu."
                )
                continue
            decision_map[decision.sentence_index] = decision

        pieces: list[str] = []
        cursor = 0
        for span in spans:
            pieces.append(source_text[cursor:span.start])
            pieces.append(
                self._render_span(
                    span.text,
                    decision_map.get(span.index),
                    brief,
                    warnings,
                )
            )
            cursor = span.end
        pieces.append(source_text[cursor:])
        rendered = "".join(pieces)
        analysis = validate_higgs_script(rendered)
        warnings.extend(issue.message for issue in analysis.issues)
        return rendered, list(dict.fromkeys(warnings))

    def _render_span(
        self,
        text: str,
        decision: PerformanceDecision | None,
        brief: AuthoringBrief,
        warnings: list[str],
    ) -> str:
        if decision is None:
            return text
        prefix: list[str] = []
        if decision.emotion:
            if decision.emotion in EMOTIONS:
                prefix.append(f"<|emotion:{decision.emotion}|>")
            else:
                warnings.append(f"Bỏ emotion không hỗ trợ: {decision.emotion}")
        if decision.style:
            if decision.style in STYLES:
                prefix.append(f"<|style:{decision.style}|>")
            else:
                warnings.append(f"Bỏ style không hỗ trợ: {decision.style}")
        if decision.pace in PACE_VALUES - {"default"}:
            prefix.append(f"<|prosody:speed_{decision.pace}|>")
        if decision.pitch in PITCH_VALUES - {"default"}:
            prefix.append(f"<|prosody:pitch_{decision.pitch}|>")
        if decision.expressiveness in EXPRESSIVENESS_VALUES - {"default"}:
            prefix.append(f"<|prosody:expressive_{decision.expressiveness}|>")

        leading = len(text) - len(text.lstrip())
        rendered = text[:leading] + "".join(prefix) + text[leading:]
        if decision.sfx_before:
            rendered = self._insert_sfx(
                rendered,
                decision,
                brief,
                warnings,
            )
        if decision.pause_after == "short":
            rendered += " <|prosody:pause|>"
        elif decision.pause_after == "long":
            rendered += " <|prosody:long_pause|>"
        elif decision.pause_after not in PAUSE_VALUES:
            warnings.append(f"Bỏ pause không hỗ trợ: {decision.pause_after}")
        return rendered

    @staticmethod
    def _insert_sfx(
        rendered: str,
        decision: PerformanceDecision,
        brief: AuthoringBrief,
        warnings: list[str],
    ) -> str:
        if not brief.allow_vocal_sfx:
            return rendered
        if decision.sfx_before not in SOUND_EFFECTS:
            warnings.append(f"Bỏ SFX không hỗ trợ: {decision.sfx_before}")
            return rendered
        cue = decision.sfx_cue
        if not cue:
            warnings.append("Bỏ SFX vì AI không chỉ ra từ tượng thanh có sẵn.")
            return rendered
        position = rendered.lower().find(cue.lower())
        if position < 0:
            warnings.append(f"Bỏ SFX vì không tìm thấy cue nguyên văn: {cue}")
            return rendered
        return (
            rendered[:position]
            + f"<|sfx:{decision.sfx_before}|>"
            + rendered[position:]
        )
