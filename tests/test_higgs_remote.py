from __future__ import annotations

import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

import numpy as np

from omni_tts_core.model_registry import ModelRegistry
from omni_tts_core.model_storage import ModelStorage
from omni_tts_core.remote.endpoint import HttpResponse, endpoint_paths
from omni_tts_core.remote.higgs_sglang import HiggsSglangClient
from omni_tts_core.service import TtsService
from omni_tts_core.ui_presenters.control_policy import TUNING_HIGGS_REMOTE, build_policy
from omni_tts_core.ui_presenters.settings_state import GenerationSettings
from omni_tts_shared.schemas import HiggsTtsOptions, RemoteEndpointOptions, RuntimeStatus


class EndpointPathsTest(unittest.TestCase):
    def test_accepts_full_speech_url_without_duplicating_route(self):
        paths = endpoint_paths("https://example.test/v1/audio/speech")
        self.assertEqual(paths.root_url, "https://example.test")
        self.assertEqual(paths.speech_url, "https://example.test/v1/audio/speech")
        self.assertEqual(paths.voices_url, "https://example.test/v1/audio/voices")
        self.assertEqual(paths.models_url, "https://example.test/v1/models")

    def test_accepts_deployment_prefix(self):
        paths = endpoint_paths("https://example.test/higgs")
        self.assertEqual(paths.speech_url, "https://example.test/higgs/v1/audio/speech")
        self.assertEqual(paths.health_url, "https://example.test/higgs/health")


class HiggsPayloadTest(unittest.TestCase):
    def _client(self, **options) -> HiggsSglangClient:
        return HiggsSglangClient(
            RemoteEndpointOptions(base_url="https://example.test"),
            HiggsTtsOptions(**options),
        )

    def test_blank_model_is_omitted_and_server_default_can_be_used(self):
        payload = self._client(model="").build_payload(text="Xin chào")
        self.assertNotIn("model", payload)
        self.assertEqual(payload["voice"], "default")

    def test_reference_audio_is_sent_as_data_uri_with_transcript(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "voice.wav"
            path.write_bytes(b"RIFF-test")
            payload = self._client().build_payload(
                text="Xin chào",
                reference_audio_path=path,
                reference_text="Đây là giọng mẫu.",
            )
        reference = payload["references"][0]
        self.assertRegex(reference["audio_path"], r"^data:audio/(x-)?wav;base64,")
        self.assertEqual(reference["text"], "Đây là giọng mẫu.")

    def test_boson_payload_uses_cloud_reference_fields_and_model(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "voice.wav"
            path.write_bytes(b"RIFF-test")
            client = HiggsSglangClient(
                RemoteEndpointOptions(
                    base_url="https://api.boson.test",
                    api_flavor="boson",
                ),
                HiggsTtsOptions(model=""),
            )
            payload = client.build_payload(
                text="Hello",
                reference_audio_path=path,
                reference_text="Exact words.",
            )
        self.assertEqual(payload["model"], "higgs-tts-3")
        self.assertIn("ref_audio", payload)
        self.assertEqual(payload["ref_text"], "Exact words.")
        self.assertNotIn("references", payload)
        self.assertNotIn("initial_codec_chunk_frames", payload)

    def test_delivery_controls_are_composed_at_start_of_input(self):
        payload = self._client(
            emotion="amusement",
            style="whispering",
            speed="speed_slow",
            pitch="pitch_high",
            expressiveness="expressive_high",
        ).build_payload(text="Nội dung")
        self.assertEqual(
            payload["input"],
            "<|emotion:amusement|><|style:whispering|>"
            "<|prosody:speed_slow|><|prosody:pitch_high|>"
            "<|prosody:expressive_high|>Nội dung",
        )

    def test_streaming_forces_pcm_and_decodes_16_bit_audio(self):
        client = self._client(stream=True, response_format="wav")
        samples = np.array([-32768, 0, 32767], dtype="<i2")
        client.transport.post_json = lambda *_args, **_kwargs: HttpResponse(
            body=samples.tobytes(),
            headers={"content-type": "audio/pcm", "x-sample-rate": "24000"},
            status=200,
        )
        audio, sample_rate = client.synthesize(text="test")
        self.assertEqual(client.options.response_format, "pcm")
        self.assertEqual(sample_rate, 24000)
        np.testing.assert_allclose(audio, [-1.0, 0.0, 32767 / 32768], rtol=0, atol=1e-6)


class RemoteCatalogTest(unittest.TestCase):
    def test_remote_model_needs_no_local_payload_and_has_remote_policy(self):
        registry = ModelRegistry()
        spec = registry.get("higgs_tts3_remote")
        storage = ModelStorage(registry)
        self.assertTrue(storage.is_installed(spec))
        status = storage.status_for(spec)
        self.assertEqual(status.storage_kind, "Remote endpoint")
        policy = build_policy(
            spec=spec,
            capabilities=spec.capabilities,
            runtime_status=RuntimeStatus(
                model_id=spec.model_id,
                display_name=spec.display_name,
                provider=spec.provider,
                installed=True,
                actual_device="remote",
            ),
            supports_codec=False,
            supports_sampling=False,
            supports_f5=False,
            supports_chatterbox=False,
        )
        self.assertIn(TUNING_HIGGS_REMOTE, policy.tuning_groups)
        self.assertEqual(policy.device_targets, (("GPU từ xa (server quyết định)", "auto"),))
        self.assertFalse(policy.gpu_safety)

    def test_preferences_round_trip_all_remote_fields(self):
        settings = GenerationSettings(
            model_id="higgs_tts3_remote",
            remote_base_url="https://example.test/v1/audio/speech",
            remote_endpoint_id="boson-main",
            remote_api_flavor="boson",
            remote_auth_mode="bearer_env",
            remote_auth_env="BOSON_API_KEY",
            higgs_model="bosonai/higgs-audio-v3-tts-4b",
            higgs_voice="default",
            higgs_stream=True,
            higgs_top_p=0.9,
            higgs_top_k=50,
            higgs_concurrency=4,
            higgs_emotion="relief",
        )
        restored = GenerationSettings.from_preferences(settings.to_preferences())
        request = restored.to_request("Xin chào")
        self.assertEqual(restored.remote_base_url, settings.remote_base_url)
        self.assertEqual(request.higgs.model, "bosonai/higgs-audio-v3-tts-4b")
        self.assertEqual(request.higgs.concurrency, 4)
        self.assertEqual(request.higgs.emotion, "relief")
        self.assertEqual(request.remote_endpoint.endpoint_id, "boson-main")
        self.assertEqual(request.remote_endpoint.api_flavor, "boson")
        self.assertEqual(request.remote_endpoint.auth_mode, "bearer_env")
        self.assertEqual(request.remote_endpoint.auth_env, "BOSON_API_KEY")

    def test_remote_generation_does_not_require_local_support_payloads(self):
        service = TtsService()
        spec = service.registry.get("higgs_tts3_remote")
        request = GenerationSettings(
            model_id=spec.model_id,
            remote_base_url="https://example.test",
            speaker_id="default",
        ).to_request("Xin chào")
        required_support = service.registry.get("higgs_audio_v2_tokenizer")
        with (
            patch.object(service.storage, "is_installed", return_value=True),
            patch.object(service, "missing_required_models", return_value=[required_support]),
        ):
            service._ensure_request_can_generate(request, spec)


if __name__ == "__main__":
    unittest.main()
