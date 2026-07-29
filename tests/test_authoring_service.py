from __future__ import annotations

import re
import tempfile
import unittest
from pathlib import Path

from omni_tts_core.authoring.key_store import AuthoringKeyStore
from omni_tts_core.authoring.providers.gemini import AuthoringCallUsage
from omni_tts_core.authoring.schemas import AuthoringBrief, VoiceContext
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


if __name__ == "__main__":
    unittest.main()
