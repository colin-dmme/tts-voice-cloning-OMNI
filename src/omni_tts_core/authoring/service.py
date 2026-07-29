from __future__ import annotations

import hashlib
import math
import re
from collections.abc import Callable
from pathlib import Path
from threading import Event

from omni_tts_core.authoring.capabilities import AuthoringPolicy, build_authoring_policy
from omni_tts_core.authoring.catalog import brief_choices
from omni_tts_core.authoring.dialects.higgs import (
    HiggsDialectAdapter,
    sentence_spans,
)
from omni_tts_core.authoring.key_store import AuthoringKeyStore, KeyImportReport
from omni_tts_core.authoring.prompting import PROMPT_VERSION, build_performance_prompt
from omni_tts_core.authoring.provider_registry import (
    ai_provider_choices,
    ai_provider_descriptor,
)
from omni_tts_core.authoring.providers.gemini import (
    AuthoringProviderError,
)
from omni_tts_core.authoring.providers.rotating import RotatingAuthoringProvider
from omni_tts_core.authoring.schemas import (
    AiProviderSettings,
    AuthoringBrief,
    AuthoringCandidate,
    AuthoringControlScope,
    AuthoringPreset,
    AuthoringSession,
    AuthoringSourceLineage,
    AuthoringSourceResolution,
    PerformanceDecision,
    PerformancePlan,
    VoiceContext,
)
from omni_tts_core.authoring.stores import (
    AiProviderSettingsStore,
    AuthoringSessionStore,
    AuthoringStateStore,
)
from omni_tts_core.provider_registry import ProviderDescriptor

NoticeCallback = Callable[[str], None]
_TAG_RE = re.compile(r"<\|[^|]+:[^|]+\|>")


class AuthoringService:
    """Core facade for AI providers, semantic plans, dialects and persistence."""

    def __init__(
        self,
        *,
        settings_store: AiProviderSettingsStore | None = None,
        key_store: AuthoringKeyStore | None = None,
        state_store: AuthoringStateStore | None = None,
        session_store: AuthoringSessionStore | None = None,
        rotating_provider_factory=None,
    ) -> None:
        self.settings_store = settings_store or AiProviderSettingsStore()
        self.key_store = key_store or AuthoringKeyStore()
        self.state_store = state_store or AuthoringStateStore()
        self.session_store = session_store or AuthoringSessionStore()
        self.rotating_provider_factory = (
            rotating_provider_factory or RotatingAuthoringProvider
        )
        self._dialects = {"higgs_v1": HiggsDialectAdapter()}

    # --- Policy / UI metadata ---------------------------------------------

    def policy(self, descriptor: ProviderDescriptor | None) -> AuthoringPolicy:
        settings = self.settings()
        configured = (
            ai_provider_descriptor(settings.provider_id) is not None
            and self.key_store.active_key_count(settings.provider_id) > 0
        )
        return build_authoring_policy(descriptor, ai_configured=configured)

    @staticmethod
    def brief_choices():
        return brief_choices()

    @staticmethod
    def ai_provider_choices() -> list[tuple[str, str]]:
        return ai_provider_choices()

    def feature_descriptors(self, dialect_id: str):
        return self._dialect(dialect_id).feature_descriptors()

    def scope_presets(self, dialect_id: str):
        return self._dialect(dialect_id).scope_presets()

    def normalize_brief(
        self,
        brief: AuthoringBrief,
        dialect_id: str,
    ) -> AuthoringBrief:
        dialect = self._dialect(dialect_id)
        scope = dialect.normalize_scope(
            brief.control_scope,
            allow_vocal_sfx=brief.allow_vocal_sfx,
        )
        sfx = scope.selection("vocal_sfx")
        return brief.model_copy(
            update={
                "control_scope": scope,
                "allow_vocal_sfx": sfx.enabled and bool(sfx.allowed_values),
            }
        )

    def scope_summary(
        self,
        scope: AuthoringControlScope,
        dialect_id: str,
    ) -> str:
        normalized = self._dialect(dialect_id).normalize_scope(scope)
        parts: list[str] = []
        for descriptor in self.feature_descriptors(dialect_id):
            selection = normalized.selection(descriptor.key)
            if not selection.enabled:
                parts.append(f"{descriptor.label}: tắt")
            else:
                parts.append(
                    f"{descriptor.label}: "
                    f"{len(selection.allowed_values)}/{len(descriptor.values)}"
                )
        return " · ".join(parts)

    # --- Provider settings and keys ---------------------------------------

    def settings(self) -> AiProviderSettings:
        return self.settings_store.load()

    def save_settings(self, payload: AiProviderSettings | dict) -> AiProviderSettings:
        settings = (
            payload
            if isinstance(payload, AiProviderSettings)
            else AiProviderSettings.model_validate(payload)
        )
        return self.settings_store.save(settings)

    def model_choices(self, provider_id: str | None = None) -> list[str]:
        settings = self.settings()
        resolved_provider = provider_id or settings.provider_id
        descriptor = self._provider_descriptor(resolved_provider)
        return [
            model
            for model in dict.fromkeys(
                [
                    settings.model if resolved_provider == settings.provider_id else "",
                    *self.key_store.models(resolved_provider),
                    *descriptor.default_models,
                ]
            )
            if model
        ]

    def model_supports_temperature(
        self, model: str, provider_id: str | None = None
    ) -> bool:
        descriptor = self._provider_descriptor(
            provider_id or self.settings().provider_id
        )
        return descriptor.supports_temperature(model)

    def safe_keys(self, provider_id: str = "gemini") -> list[dict[str, str]]:
        return self.key_store.safe_keys(provider_id)

    def active_key_count(self, provider_id: str = "gemini") -> int:
        return self.key_store.active_key_count(provider_id)

    def add_key(self, name: str, value: str, provider_id: str = "gemini") -> bool:
        return self.key_store.add_key(provider_id, name, value)

    def update_key(
        self,
        old_name: str,
        new_name: str,
        value: str,
        provider_id: str = "gemini",
    ) -> bool:
        return self.key_store.update_key(provider_id, old_name, new_name, value)

    def remove_key(self, name: str, provider_id: str = "gemini") -> bool:
        return self.key_store.remove_key(provider_id, name)

    def reset_key(self, name: str, provider_id: str = "gemini") -> bool:
        return self.key_store.reset_key_status(provider_id, name)

    def import_keys(
        self,
        source_path: Path,
        provider_id: str = "gemini",
    ) -> KeyImportReport:
        return self.key_store.import_file(source_path, provider_id=provider_id)

    def test_connection(self) -> str:
        settings = self.settings()
        descriptor = self._provider_descriptor(settings.provider_id)
        pair = self.key_store.get_next_key(settings.provider_id)
        if pair is None:
            raise AuthoringProviderError("Chưa có Gemini API key active.")
        name, value = pair
        try:
            message = descriptor.client_factory(value, settings).test_connection()
        except AuthoringProviderError as error:
            self.key_store.mark_key_error(settings.provider_id, name, str(error))
            raise
        else:
            self.key_store.release_key(settings.provider_id, name)
            return f"{message} · key={name}"

    def refresh_models(self) -> list[str]:
        settings = self.settings()
        descriptor = self._provider_descriptor(settings.provider_id)
        pair = self.key_store.get_next_key(settings.provider_id)
        if pair is None:
            raise AuthoringProviderError("Chưa có Gemini API key active.")
        name, value = pair
        try:
            models = descriptor.client_factory(value, settings).list_models()
        except AuthoringProviderError as error:
            self.key_store.mark_key_error(settings.provider_id, name, str(error))
            raise
        else:
            self.key_store.release_key(settings.provider_id, name)
        self.key_store.set_models(settings.provider_id, models)
        return models

    # --- Presets / state ---------------------------------------------------

    def last_brief(self) -> AuthoringBrief:
        return self.state_store.last_brief()

    def presets(self) -> list[AuthoringPreset]:
        return self.state_store.presets()

    def recent_sessions(
        self,
        *,
        source_text: str = "",
        dialect_id: str = "",
        limit: int = 20,
    ) -> list[AuthoringSession]:
        sessions = self.session_store.list_sessions()
        if source_text.strip():
            source_hash = hashlib.sha256(
                source_text.strip().encode("utf-8")
            ).hexdigest()
            sessions = [
                item for item in sessions if item.source_hash == source_hash
            ]
        if dialect_id:
            sessions = [
                item for item in sessions if item.dialect_id == dialect_id
            ]
        return sessions[: max(1, limit)]

    def resolve_source(
        self,
        current_text: str,
        dialect_id: str,
    ) -> AuthoringSourceResolution:
        clean = current_text.strip()
        current_hash = _text_hash(clean)
        lineage = self.state_store.source_lineage(current_hash)
        if lineage is not None and lineage.dialect_id == dialect_id:
            return AuthoringSourceResolution(
                source_text=lineage.source_text,
                source_hash=lineage.source_hash,
                mode="lineage",
                note=(
                    "Đã nhận diện đây là phương án AI từng áp dụng; "
                    "AI sẽ dùng lại bản gốc và lịch sử tương ứng."
                ),
                session_id=lineage.session_id,
                candidate_id=lineage.candidate_id,
            )
        dialect = self._dialect(dialect_id)
        if _TAG_RE.search(clean):
            recovered = dialect.recover_source(clean)
            if recovered and recovered != clean:
                return AuthoringSourceResolution(
                    source_text=recovered,
                    source_hash=_text_hash(recovered),
                    mode="recovered_markup",
                    note=(
                        "Không thấy lineage chính xác; đã tách markup để phục hồi "
                        "bản lời gần nhất. Hãy kiểm tra 'Xem bản gốc' trước khi tạo."
                    ),
                )
        return AuthoringSourceResolution(
            source_text=clean,
            source_hash=current_hash,
        )

    def save_preset(
        self,
        name: str,
        brief: AuthoringBrief,
        *,
        voice_profile_id: str = "",
        dialect_id: str = "",
    ) -> AuthoringPreset:
        return self.state_store.save_preset(
            name,
            brief,
            voice_profile_id=voice_profile_id,
            dialect_id=dialect_id,
        )

    # --- Candidate generation --------------------------------------------

    def generate(
        self,
        source_text: str,
        brief: AuthoringBrief,
        voice_context: VoiceContext,
        dialect_id: str,
        *,
        parent_candidate_id: str = "",
        on_notice: NoticeCallback | None = None,
        cancel_event: Event | None = None,
    ) -> AuthoringSession:
        clean_source = source_text.strip()
        if not clean_source:
            raise ValueError("Chưa có văn bản để AI phân tích.")
        dialect = self._dialect(dialect_id)
        if self.active_key_count(self.settings().provider_id) <= 0:
            raise AuthoringProviderError(
                "Chưa có Gemini API key active. Mở mục AI / API để cấu hình."
            )

        brief = self.normalize_brief(brief, dialect_id)
        self.state_store.save_last_brief(brief)
        session = AuthoringSession(
            source_hash=_text_hash(clean_source),
            source_text=clean_source,
            dialect_id=dialect_id,
            brief=brief,
            voice_context=voice_context,
        )
        settings = self.settings()
        descriptor = self._provider_descriptor(settings.provider_id)
        provider = self.rotating_provider_factory(
            self.key_store,
            settings,
            client_factory=descriptor.client_factory,
        )
        candidates: list[AuthoringCandidate] = []
        for index in range(brief.candidate_count):
            if cancel_event is not None and cancel_event.is_set():
                raise AuthoringProviderError("Đã hủy phân tích AI.")
            if on_notice:
                on_notice(
                    f"[AI] Đang tạo phương án {index + 1}/{brief.candidate_count}…"
                )
            system, user = build_performance_prompt(
                clean_source,
                brief,
                voice_context,
                dialect.feature_descriptors(),
                variant_index=index,
            )
            payload, _usage = provider.call_json(
                system,
                user,
                on_notice=on_notice,
                cancel_event=cancel_event,
            )
            raw_plan = PerformancePlan.model_validate(payload)
            plan = self._sanitize_plan(raw_plan, clean_source, brief)
            rendered, messages = dialect.render(clean_source, plan, brief)
            if not _same_spoken_text(clean_source, rendered):
                raise ValueError(
                    "Kết quả renderer đã làm thay đổi lời gốc; phương án bị từ chối."
                )
            candidates.append(
                AuthoringCandidate(
                    parent_candidate_id=parent_candidate_id,
                    label=f"Phương án {index + 1}",
                    rendered_text=rendered,
                    plan=plan,
                    validation_messages=messages,
                    ai_provider=self.settings().provider_id,
                    ai_model=self.settings().model,
                    prompt_version=PROMPT_VERSION,
                )
            )
        session = session.model_copy(update={"candidates": candidates})
        self.session_store.save(session)
        for candidate in candidates:
            self.state_store.save_source_lineage(
                AuthoringSourceLineage(
                    rendered_hash=_text_hash(candidate.rendered_text),
                    source_hash=session.source_hash,
                    source_text=clean_source,
                    dialect_id=dialect_id,
                    session_id=session.session_id,
                    candidate_id=candidate.candidate_id,
                )
            )
        return session

    def _sanitize_plan(
        self,
        plan: PerformancePlan,
        source_text: str,
        brief: AuthoringBrief,
    ) -> PerformancePlan:
        sentence_count = len(sentence_spans(source_text))
        seen: set[int] = set()
        warnings = list(plan.warnings)
        cleaned: list[PerformanceDecision] = []
        for decision in plan.decisions:
            if decision.sentence_index >= sentence_count:
                warnings.append(
                    f"AI tham chiếu câu {decision.sentence_index + 1} ngoài phạm vi."
                )
                continue
            if decision.sentence_index in seen:
                warnings.append(
                    f"AI trả nhiều chỉ dẫn cho câu {decision.sentence_index + 1}; "
                    "chỉ giữ chỉ dẫn đầu."
                )
                continue
            seen.add(decision.sentence_index)
            sanitized = self._sanitize_decision(decision, brief)
            cleaned.append(sanitized)
            changed = self._changed_control_fields(decision, sanitized)
            if changed:
                warnings.append(
                    f"Câu {decision.sentence_index + 1}: đã loại điều khiển "
                    f"ngoài phạm vi ({', '.join(changed)})."
                )

        ratios = {"very_light": 0.20, "light": 0.35, "medium": 0.55}
        max_decisions = max(1, math.ceil(sentence_count * ratios[brief.tag_density]))
        if len(cleaned) > max_decisions:
            selected = sorted(
                cleaned,
                key=lambda item: (-item.importance, item.sentence_index),
            )[:max_decisions]
            cleaned = sorted(selected, key=lambda item: item.sentence_index)
            warnings.append(
                f"Đã giới hạn còn {max_decisions} câu có điều khiển theo mật độ "
                f"'{brief.tag_density}'."
            )
        return PerformancePlan(
            decisions=cleaned,
            summary=plan.summary,
            warnings=list(dict.fromkeys(warnings)),
        )

    @staticmethod
    def _sanitize_decision(
        decision: PerformanceDecision,
        brief: AuthoringBrief,
    ) -> PerformanceDecision:
        scope = brief.control_scope

        def permitted(feature: str, value: str, neutral: str) -> str:
            if value == neutral:
                return neutral
            selection = scope.selection(feature)
            if selection.enabled and value in selection.allowed_values:
                return value
            return neutral

        update = {
            "emotion": permitted("emotion", decision.emotion, ""),
            "style": permitted("style", decision.style, ""),
            "pace": permitted("pace", decision.pace, "default"),
            "pitch": permitted("pitch", decision.pitch, "default"),
            "expressiveness": permitted(
                "expressiveness",
                decision.expressiveness,
                "default",
            ),
            "pause_after": permitted("pause", decision.pause_after, "none"),
            "sfx_before": permitted("vocal_sfx", decision.sfx_before, ""),
        }
        update["sfx_cue"] = decision.sfx_cue if update["sfx_before"] else ""
        if brief.content_type == "science_explainer" and update["style"] in {
            "singing",
            "shouting",
        }:
            update["style"] = ""

        # Keep one primary emotion and a bounded number of additional delivery
        # dimensions. Pauses are positional and handled separately.
        extra_fields = ["style", "pace", "expressiveness", "pitch"]
        max_extras = {"very_light": 0, "light": 1, "medium": 2}[brief.tag_density]
        used = 0
        for field in extra_fields:
            value = update[field]
            is_default = value in {"", "default"}
            if is_default:
                continue
            if used >= max_extras:
                update[field] = "" if field == "style" else "default"
            else:
                used += 1
        return decision.model_copy(update=update)

    @staticmethod
    def _changed_control_fields(
        before: PerformanceDecision,
        after: PerformanceDecision,
    ) -> list[str]:
        labels = {
            "emotion": "cảm xúc",
            "style": "phong cách",
            "pace": "tốc độ",
            "pitch": "cao độ",
            "expressiveness": "độ biểu cảm",
            "pause_after": "khoảng nghỉ",
            "sfx_before": "SFX",
        }
        return [
            label
            for field, label in labels.items()
            if getattr(before, field) != getattr(after, field)
        ]

    def _dialect(self, dialect_id: str):
        dialect = self._dialects.get(dialect_id)
        if dialect is None:
            raise ValueError(f"Chưa có authoring dialect adapter: {dialect_id}")
        return dialect

    @staticmethod
    def _provider_descriptor(provider_id: str):
        descriptor = ai_provider_descriptor(provider_id)
        if descriptor is None:
            raise ValueError(f"Chưa đăng ký AI provider: {provider_id}")
        return descriptor


def _same_spoken_text(source: str, rendered: str) -> bool:
    stripped = _TAG_RE.sub("", rendered)
    normalize = lambda value: re.sub(r"\s+", " ", value).strip()
    return normalize(source) == normalize(stripped)


def _text_hash(text: str) -> str:
    return hashlib.sha256(text.strip().encode("utf-8")).hexdigest()
