from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from omni_tts_core.higgs.custom_voices import (
    HiggsCustomVoiceClient,
    HiggsCustomVoiceStore,
)
from omni_tts_core.higgs.endpoint_capabilities import endpoint_capabilities
from omni_tts_core.higgs.script import (
    compile_higgs_chunks,
    normalize_higgs_text,
    validate_higgs_script,
)
from omni_tts_core.remote.endpoint import HttpResponse
from omni_tts_core.text.source_reader import read_source_text
from omni_tts_shared.schemas import (
    HiggsCustomVoice,
    HiggsTtsOptions,
    RemoteEndpointOptions,
)


class HiggsScriptCompilerTest(unittest.TestCase):
    def test_vietnamese_normalization_preserves_control_tokens(self) -> None:
        source = (
            "<|emotion:contemplation|><|prosody:speed_slow|>"
            "Mặt Trăng cách 1.5 km. <|prosody:pause|> Một con số nhỏ."
        )
        normalized = normalize_higgs_text(source, "vi")
        self.assertIn("<|emotion:contemplation|>", normalized)
        self.assertIn("<|prosody:speed_slow|>", normalized)
        self.assertIn("<|prosody:pause|>", normalized)
        self.assertNotIn("nhỏ hơn emotion", normalized)

    def test_delivery_state_is_carried_to_later_chunks(self) -> None:
        source = (
            "<|emotion:contemplation|><|prosody:speed_slow|>"
            "The Moon drifts away every year. "
            "This second sentence is deliberately long enough to become another turn."
        )
        chunks = compile_higgs_chunks(source, "en", 70)
        self.assertGreaterEqual(len(chunks), 2)
        self.assertTrue(chunks[1].startswith(
            "<|emotion:contemplation|><|prosody:speed_slow|>"
        ))

    def test_inline_change_becomes_next_chunk_state(self) -> None:
        source = (
            "<|emotion:contemplation|>First reflective sentence. "
            "<|emotion:awe|>A second sentence changes the state. "
            "A third sentence inherits awe."
        )
        chunks = compile_higgs_chunks(source, "en", 55)
        self.assertGreaterEqual(len(chunks), 3)
        self.assertTrue(chunks[-1].startswith("<|emotion:awe|>"))

    def test_baseline_only_fills_missing_delivery_categories(self) -> None:
        options = HiggsTtsOptions(
            emotion="amusement",
            speed="speed_slow",
        )
        chunks = compile_higgs_chunks(
            "<|emotion:awe|>A wonderful discovery.", "en", 220, options
        )
        self.assertEqual(
            chunks,
            [
                "<|prosody:speed_slow|><|emotion:awe|>"
                "A wonderful discovery."
            ],
        )

    def test_pause_is_not_carried_to_next_chunk(self) -> None:
        chunks = compile_higgs_chunks(
            "<|emotion:awe|>First sentence. "
            "<|prosody:pause|>Second sentence that creates another chunk.",
            "en",
            45,
        )
        self.assertGreaterEqual(len(chunks), 2)
        self.assertNotIn("<|prosody:pause|>", chunks[-1][:40])

    def test_sfx_with_space_gets_authoring_warning(self) -> None:
        analysis = validate_higgs_script("<|sfx:laughter|> hehe")
        self.assertTrue(analysis.valid)
        self.assertEqual(analysis.issues[0].severity, "warning")

    def test_unknown_tag_is_rejected(self) -> None:
        analysis = validate_higgs_script("<|emotion:calm|>Hello")
        self.assertFalse(analysis.valid)


class HiggsSrtPreservationTest(unittest.TestCase):
    def test_higgs_mode_keeps_tokens_but_still_removes_html_markup(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "tagged.srt"
            path.write_text(
                "1\n00:00:00,000 --> 00:00:02,000\n"
                "<i><|emotion:awe|>Amazing.</i>\n",
                encoding="utf-8",
            )
            self.assertEqual(read_source_text(path), "Amazing.")
            self.assertEqual(
                read_source_text(path, preserve_higgs_tags=True),
                "<|emotion:awe|>Amazing.",
            )


class HiggsEndpointCapabilitiesTest(unittest.TestCase):
    def test_custom_voice_is_endpoint_gated(self) -> None:
        self.assertFalse(
            endpoint_capabilities("sglang").supports_custom_voice_create
        )
        self.assertTrue(
            endpoint_capabilities("boson").supports_custom_voice_create
        )


class HiggsCustomVoiceTest(unittest.TestCase):
    def test_client_posts_profile_and_reads_voice_id(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            audio = Path(temp) / "voice.wav"
            audio.write_bytes(b"RIFF-test")
            endpoint = RemoteEndpointOptions(
                endpoint_id="boson-main",
                api_flavor="boson",
                base_url="https://api.example.test",
            )
            client = HiggsCustomVoiceClient(endpoint)
            calls = []

            def post(url, payload):
                calls.append((url, payload))
                return HttpResponse(
                    body=json.dumps(
                        {"voice_id": "voice_123", "title": "Narrator"}
                    ).encode(),
                    headers={"content-type": "application/json"},
                    status=200,
                )

            client.transport.post_json = post
            voice = client.create(
                title="Narrator",
                reference_audio_path=audio,
                reference_text="Exact transcript.",
            )
            self.assertEqual(voice.voice_id, "voice_123")
            self.assertEqual(voice.endpoint_id, "boson-main")
            self.assertTrue(calls[0][0].endswith("/v1/audio/voices"))
            self.assertTrue(calls[0][1]["ref_audio"].startswith("data:audio/"))

    def test_store_is_endpoint_scoped_and_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = HiggsCustomVoiceStore(Path(temp) / "voices.json")
            voice = HiggsCustomVoice(
                voice_id="voice_123",
                title="First title",
                endpoint_id="one",
            )
            store.save(voice)
            store.save(voice.model_copy(update={"title": "Updated title"}))
            store.save(
                HiggsCustomVoice(
                    voice_id="voice_999",
                    title="Other endpoint",
                    endpoint_id="two",
                )
            )
            self.assertEqual(len(store.list("one")), 1)
            self.assertEqual(store.list("one")[0].title, "Updated title")
            self.assertEqual(len(store.list("two")), 1)


if __name__ == "__main__":
    unittest.main()
