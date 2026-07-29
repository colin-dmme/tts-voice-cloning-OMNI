from __future__ import annotations

import re
import tempfile
import unittest
from pathlib import Path

from omni_tts_core.authoring.key_store import AuthoringKeyStore
from omni_tts_core.authoring.providers.gemini import AuthoringCallUsage
from omni_tts_core.authoring.prompting import build_performance_prompt
from omni_tts_core.authoring.schemas import (
    AuthoringBrief,
    PerformanceDecision,
    PerformancePlan,
    VoiceContext,
)
from omni_tts_core.authoring.service import AuthoringService
from omni_tts_core.authoring.stores import (
    AiProviderSettingsStore,
    AuthoringSessionStore,
    AuthoringStateStore,
)
from omni_tts_core.provider_registry import provider_descriptor


class _FakeRotatingProvider:
    calls = 0

    def __init__(self, _key_store, _settings, *, client_factory=None) -> None:
        self.client_factory = client_factory

    def call_json(self, _system, _user, **_kwargs):
        type(self).calls += 1
        return (
            {
                "summary": "Kế hoạch thử",
                "decisions": [
                    {
                        "sentence_index": 0,
                        "emotion": "contemplation",
                        "pause_after": "short",
                        "importance": 5,
                        "reason": "Mở vấn đề.",
                    },
                    {
                        "sentence_index": 1,
                        "emotion": "awe",
                        "expressiveness": "high",
                        "importance": 4,
                        "reason": "Điểm tiết lộ.",
                    },
                ],
            },
            AuthoringCallUsage(),
        )


class AuthoringServiceTest(unittest.TestCase):
    def _service(self, root: Path) -> AuthoringService:
        key_store = AuthoringKeyStore(root / "keys.json")
        key_store.add_key("gemini", "test", "fake-test-key-value")
        return AuthoringService(
            settings_store=AiProviderSettingsStore(root / "settings.json"),
            key_store=key_store,
            state_store=AuthoringStateStore(root / "state.json"),
            session_store=AuthoringSessionStore(root / "sessions.json"),
            rotating_provider_factory=_FakeRotatingProvider,
        )

    def test_capability_is_tts_provider_driven(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            service = self._service(Path(folder))
            higgs = service.policy(provider_descriptor("higgs_remote"))
            piper = service.policy(provider_descriptor("piper"))
            self.assertTrue(higgs.enabled)
            self.assertEqual(higgs.dialect_id, "higgs_v1")
            self.assertFalse(piper.supported)

    def test_generate_multiple_candidates_preserves_spoken_text_and_history(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            service = self._service(Path(folder))
            source = "This is the question. Here is the answer."
            session = service.generate(
                source,
                AuthoringBrief(candidate_count=2, tag_density="medium"),
                VoiceContext(
                    display_name="Science narrator",
                    presentation="female",
                    description="Warm and precise.",
                ),
                "higgs_v1",
            )
            self.assertEqual(len(session.candidates), 2)
            for candidate in session.candidates:
                spoken = re.sub(r"<\|[^|]+:[^|]+\|>", "", candidate.rendered_text)
                self.assertEqual(" ".join(spoken.split()), " ".join(source.split()))
            self.assertEqual(
                service.session_store.list_sessions()[0].session_id,
                session.session_id,
            )

    def test_prosody_only_scope_is_enforced_after_ai_response(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            service = self._service(Path(folder))
            prosody_only = next(
                item.scope
                for item in service.scope_presets("higgs_v1")
                if item.preset_id == "prosody_only"
            )
            session = service.generate(
                "This is the question. Here is the answer.",
                AuthoringBrief(
                    candidate_count=1,
                    tag_density="medium",
                    control_scope=prosody_only,
                ),
                VoiceContext(presentation="female"),
                "higgs_v1",
            )
            rendered = session.candidates[0].rendered_text
            self.assertNotIn("<|emotion:", rendered)
            self.assertNotIn("<|style:", rendered)
            self.assertNotIn("<|sfx:", rendered)
            self.assertIn("<|prosody:", rendered)

    def test_individual_emotion_can_be_forbidden(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            service = self._service(Path(folder))
            brief = service.normalize_brief(
                AuthoringBrief(tag_density="medium"),
                "higgs_v1",
            )
            emotion = brief.control_scope.features["emotion"]
            emotion.allowed_values = [
                value for value in emotion.allowed_values if value != "elation"
            ]
            plan = service._sanitize_plan(
                PerformancePlan(
                    decisions=[
                        PerformanceDecision(
                            sentence_index=0,
                            emotion="elation",
                        ),
                        PerformanceDecision(
                            sentence_index=1,
                            emotion="awe",
                        ),
                    ]
                ),
                "First sentence. Second sentence.",
                brief,
            )
            self.assertEqual(plan.decisions[0].emotion, "")
            self.assertEqual(plan.decisions[1].emotion, "awe")
            self.assertTrue(
                any("cảm xúc" in warning for warning in plan.warnings)
            )

    def test_prompt_exposes_only_values_permitted_by_scope(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            service = self._service(Path(folder))
            prosody_only = next(
                item.scope
                for item in service.scope_presets("higgs_v1")
                if item.preset_id == "prosody_only"
            )
            brief = service.normalize_brief(
                AuthoringBrief(control_scope=prosody_only),
                "higgs_v1",
            )
            system, _user = build_performance_prompt(
                "One sentence.",
                brief,
                VoiceContext(),
                service.feature_descriptors("higgs_v1"),
                variant_index=0,
            )
            self.assertIn("- emotion: DISABLED", system)
            self.assertIn("- style: DISABLED", system)
            self.assertIn("- vocal_sfx: DISABLED", system)
            self.assertIn("- pace: very_slow, slow, fast, very_fast", system)

    def test_applied_candidate_resolves_to_original_source_and_history(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            service = self._service(Path(folder))
            source = "This is the question. Here is the answer."
            session = service.generate(
                source,
                AuthoringBrief(candidate_count=1, tag_density="medium"),
                VoiceContext(),
                "higgs_v1",
            )
            rendered = session.candidates[0].rendered_text
            resolution = service.resolve_source(rendered, "higgs_v1")
            self.assertEqual(resolution.mode, "lineage")
            self.assertEqual(resolution.source_text, source)
            self.assertEqual(resolution.session_id, session.session_id)
            history = service.recent_sessions(
                source_text=resolution.source_text,
                dialect_id="higgs_v1",
            )
            self.assertEqual(history[0].session_id, session.session_id)

    def test_markup_recovery_is_available_without_saved_lineage(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            service = self._service(Path(folder))
            resolution = service.resolve_source(
                "<|emotion:awe|>A fact. <|prosody:pause|> "
                "<|prosody:expressive_high|>Another fact.",
                "higgs_v1",
            )
            self.assertEqual(resolution.mode, "recovered_markup")
            self.assertEqual(resolution.source_text, "A fact. Another fact.")


if __name__ == "__main__":
    unittest.main()
