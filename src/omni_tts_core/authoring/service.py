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
    EXPRESSIVENESS_VALUES,
    PACE_VALUES,
    PAUSE_VALUES,
    PITCH_VALUES,
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
    AuthoringPreset,
    AuthoringSession,
    PerformanceDecision,
    PerformancePlan,
    VoiceContext,
)
from omni_tts_core.authoring.stores import (
    AiProviderSettingsStore,
    AuthoringSessionStore,
    AuthoringStateStore,
)
from omni_tts_core.higgs.authoring_catalog import EMOTIONS, SOUND_EFFECTS, STYLES
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
        dialect = self._dialects.get(dialect_id)
        if dialect is None:
            raise ValueError(f"Chưa có authoring dialect adapter: {dialect_id}")
        if self.active_key_count(self.settings().provider_id) <= 0:
            raise AuthoringProviderError(
                "Chưa có Gemini API key active. Mở mục AI / API để cấu hình."
            )

        self.state_store.save_last_brief(brief)
        session = AuthoringSession(
            source_hash=hashlib.sha256(clean_source.encode("utf-8")).hexdigest(),
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
            cleaned.append(self._sanitize_decision(decision, brief))

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
        update = {
            "emotion": decision.emotion if decision.emotion in EMOTIONS else "",
            "style": decision.style if decision.style in STYLES else "",
            "pace": decision.pace if decision.pace in PACE_VALUES else "default",
            "pitch": decision.pitch if decision.pitch in PITCH_VALUES else "default",
            "expressiveness": (
                decision.expressiveness
                if decision.expressiveness in EXPRESSIVENESS_VALUES
                else "default"
            ),
            "pause_after": (
                decision.pause_after if decision.pause_after in PAUSE_VALUES else "none"
            ),
            "sfx_before": (
                decision.sfx_before
                if brief.allow_vocal_sfx and decision.sfx_before in SOUND_EFFECTS
                else ""
            ),
            "sfx_cue": decision.sfx_cue if brief.allow_vocal_sfx else "",
        }
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
    def _provider_descriptor(provider_id: str):
        descriptor = ai_provider_descriptor(provider_id)
        if descriptor is None:
            raise ValueError(f"Chưa đăng ký AI provider: {provider_id}")
        return descriptor


def _same_spoken_text(source: str, rendered: str) -> bool:
    stripped = _TAG_RE.sub("", rendered)
    normalize = lambda value: re.sub(r"\s+", " ", value).strip()
    return normalize(source) == normalize(stripped)
