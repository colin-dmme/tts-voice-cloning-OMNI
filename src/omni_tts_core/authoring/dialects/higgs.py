from __future__ import annotations

import re
from dataclasses import dataclass

from omni_tts_core.authoring.catalog import (
    AuthoringFeatureDescriptor,
    AuthoringFeatureValue,
    AuthoringScopePreset,
)
from omni_tts_core.authoring.schemas import (
    AuthoringBrief,
    AuthoringControlScope,
    AuthoringFeatureSelection,
    PerformanceDecision,
    PerformancePlan,
)
from omni_tts_core.higgs.authoring_catalog import (
    EMOTIONS,
    HIGGS_TAG_GROUPS,
    SOUND_EFFECTS,
    STYLES,
)
from omni_tts_core.higgs.script import validate_higgs_script

PACE_VALUES = {"default", "very_slow", "slow", "fast", "very_fast"}
PITCH_VALUES = {"default", "low", "high"}
EXPRESSIVENESS_VALUES = {"default", "low", "high"}
PAUSE_VALUES = {"none", "short", "long"}
_HIGGS_MARKUP_RE = re.compile(r"<\|(?:emotion|style|prosody|sfx):[^|]+\|>")


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

    def feature_descriptors(self) -> tuple[AuthoringFeatureDescriptor, ...]:
        option_lookup = {
            (option.category, option.value): option
            for group in HIGGS_TAG_GROUPS
            for option in group.options
        }

        def values(
            items: tuple[tuple[str, str, str], ...],
        ) -> tuple[AuthoringFeatureValue, ...]:
            result: list[AuthoringFeatureValue] = []
            for neutral_value, category, provider_value in items:
                option = option_lookup[(category, provider_value)]
                result.append(
                    AuthoringFeatureValue(
                        value=neutral_value,
                        label=option.label,
                        tooltip=option.tooltip,
                    )
                )
            return tuple(result)

        return (
            AuthoringFeatureDescriptor(
                "emotion",
                "Cảm xúc",
                "AI chỉ được dùng những sắc thái cảm xúc được bật.",
                values(tuple((value, "emotion", value) for value in EMOTIONS)),
            ),
            AuthoringFeatureDescriptor(
                "style",
                "Phong cách phát giọng",
                "Các cách phát giọng đặc biệt; nên dùng rất có chọn lọc.",
                values(tuple((value, "style", value) for value in STYLES)),
            ),
            AuthoringFeatureDescriptor(
                "pace",
                "Tốc độ",
                "Cho phép AI điều chỉnh tốc độ ở câu phù hợp.",
                values(
                    (
                        ("very_slow", "prosody", "speed_very_slow"),
                        ("slow", "prosody", "speed_slow"),
                        ("fast", "prosody", "speed_fast"),
                        ("very_fast", "prosody", "speed_very_fast"),
                    )
                ),
            ),
            AuthoringFeatureDescriptor(
                "pitch",
                "Cao độ",
                "Cho phép hạ hoặc nâng cao độ; không dùng để đổi giới tính giọng.",
                values(
                    (
                        ("low", "prosody", "pitch_low"),
                        ("high", "prosody", "pitch_high"),
                    )
                ),
            ),
            AuthoringFeatureDescriptor(
                "expressiveness",
                "Độ biểu cảm",
                "Kiểm soát mức biến hóa và nhấn nhá của giọng.",
                values(
                    (
                        ("low", "prosody", "expressive_low"),
                        ("high", "prosody", "expressive_high"),
                    )
                ),
            ),
            AuthoringFeatureDescriptor(
                "pause",
                "Khoảng nghỉ",
                "Cho phép AI chèn nhịp nghỉ ngắn hoặc dài sau câu.",
                values(
                    (
                        ("short", "prosody", "pause"),
                        ("long", "prosody", "long_pause"),
                    )
                ),
            ),
            AuthoringFeatureDescriptor(
                "vocal_sfx",
                "SFX giọng nói",
                "Chỉ dùng khi trong câu đã có cue tượng thanh nguyên văn.",
                values(tuple((value, "sfx", value) for value in SOUND_EFFECTS)),
            ),
        )

    def default_scope(self, *, allow_vocal_sfx: bool = False) -> AuthoringControlScope:
        return AuthoringControlScope(
            features={
                descriptor.key: AuthoringFeatureSelection(
                    enabled=descriptor.key != "vocal_sfx" or allow_vocal_sfx,
                    allowed_values=[item.value for item in descriptor.values],
                )
                for descriptor in self.feature_descriptors()
            }
        )

    def normalize_scope(
        self,
        scope: AuthoringControlScope,
        *,
        allow_vocal_sfx: bool = False,
    ) -> AuthoringControlScope:
        if not scope.features:
            return self.default_scope(allow_vocal_sfx=allow_vocal_sfx)
        features: dict[str, AuthoringFeatureSelection] = {}
        for descriptor in self.feature_descriptors():
            supported = {item.value for item in descriptor.values}
            selection = scope.features.get(descriptor.key)
            if selection is None:
                default = self.default_scope(
                    allow_vocal_sfx=allow_vocal_sfx
                ).selection(descriptor.key)
                features[descriptor.key] = default
                continue
            features[descriptor.key] = AuthoringFeatureSelection(
                enabled=selection.enabled,
                allowed_values=[
                    value
                    for value in selection.allowed_values
                    if value in supported
                ],
            )
        return AuthoringControlScope(features=features)

    def scope_presets(self) -> tuple[AuthoringScopePreset, ...]:
        balanced = self.default_scope()

        def with_enabled(*enabled_keys: str) -> AuthoringControlScope:
            allowed = set(enabled_keys)
            return AuthoringControlScope(
                features={
                    key: selection.model_copy(
                        update={"enabled": key in allowed}
                    )
                    for key, selection in balanced.features.items()
                }
            )

        no_emotion = balanced.model_copy(deep=True)
        no_emotion.features["emotion"].enabled = False
        return (
            AuthoringScopePreset(
                "balanced",
                "Cân bằng · khuyên dùng",
                "Cho phép các điều khiển giọng thông dụng; SFX tắt mặc định.",
                balanced,
            ),
            AuthoringScopePreset(
                "prosody_only",
                "Chỉ nhịp & biểu cảm",
                "Không dùng emotion, style hay SFX; chỉ tốc độ, cao độ, "
                "độ biểu cảm và khoảng nghỉ.",
                with_enabled("pace", "pitch", "expressiveness", "pause"),
            ),
            AuthoringScopePreset(
                "no_emotion",
                "Không dùng cảm xúc",
                "Giữ các điều khiển khác nhưng cấm toàn bộ emotion và SFX.",
                no_emotion,
            ),
            AuthoringScopePreset(
                "pause_only",
                "Chỉ khoảng nghỉ",
                "AI chỉ được chèn nghỉ ngắn hoặc nghỉ dài.",
                with_enabled("pause"),
            ),
        )

    def recover_source(self, rendered_text: str) -> str:
        """Best-effort fallback when an exact saved lineage is unavailable."""

        without_inserted_pauses = re.sub(
            r" <\|prosody:(?:pause|long_pause)\|>",
            "",
            rendered_text,
        )
        return _HIGGS_MARKUP_RE.sub("", without_inserted_pauses).strip()

    def render(
        self,
        source_text: str,
        plan: PerformancePlan,
        brief: AuthoringBrief,
    ) -> tuple[str, list[str]]:
        normalized_scope = self.normalize_scope(
            brief.control_scope,
            allow_vocal_sfx=brief.allow_vocal_sfx,
        )
        sfx = normalized_scope.selection("vocal_sfx")
        brief = brief.model_copy(
            update={
                "control_scope": normalized_scope,
                "allow_vocal_sfx": sfx.enabled and bool(sfx.allowed_values),
            }
        )
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
        selection = brief.control_scope.selection("vocal_sfx")
        if (
            not brief.allow_vocal_sfx
            or not selection.enabled
            or decision.sfx_before not in selection.allowed_values
        ):
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
