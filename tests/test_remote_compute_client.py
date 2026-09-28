from __future__ import annotations

import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from omni_tts_core.remote_compute.client import BrokerClient
from omni_tts_core.remote_compute.models import (
    BrokerConnectionOptions,
    RemoteJobStatus,
    RemoteTtsJob,
    RemoteTtsRequest,
    RemoteTtsResultMetadata,
)
from omni_tts_shared.errors import ConfigError, GenerationError


class _Response:
    def __init__(self, body: bytes) -> None:
        self._body = body

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        return None

    def read(self) -> bytes:
        return self._body


def _request() -> RemoteTtsRequest:
    return RemoteTtsRequest(
        client_job_id="studio-job-1",
        inference_unit_id="unit-1",
        idempotency_key="studio-job-1:unit-1",
        model_id="zerotts_202m_official",
        text="Xin chào",
    )


class BrokerClientTest(unittest.TestCase):
    def setUp(self) -> None:
        self.options = BrokerConnectionOptions(
            base_url="https://broker.example.test/",
            auth_env="TEST_COLIN_BROKER_TOKEN",
            max_retries=0,
        )
        self.client = BrokerClient(self.options)

    def test_health_does_not_require_token(self) -> None:
        with patch(
            "omni_tts_core.remote_compute.client.urlopen",
            return_value=_Response(b'{"status":"ok"}'),
        ) as mocked:
            self.assertEqual(self.client.health(), {"status": "ok"})
        self.assertNotIn("Authorization", dict(mocked.call_args.args[0].header_items()))

    def test_submit_includes_selected_worker_and_bearer_token(self) -> None:
        job = RemoteTtsJob(job_id="job-1", request=_request())
        with patch.dict(os.environ, {"TEST_COLIN_BROKER_TOKEN": "secret"}, clear=False):
            with patch(
                "omni_tts_core.remote_compute.client.urlopen",
                return_value=_Response(job.model_dump_json().encode("utf-8")),
            ) as mocked:
                result = self.client.submit(_request(), worker_id="google-pro-2")
        http_request = mocked.call_args.args[0]
        self.assertEqual(result.job_id, "job-1")
        self.assertEqual(http_request.get_header("Authorization"), "Bearer secret")
        self.assertEqual(json.loads(http_request.data)["requested_worker_id"], "google-pro-2")

    def test_list_workers_reads_capabilities(self) -> None:
        payload = [
            {
                "capabilities": {
                    "worker_id": "google-pro-1",
                    "display_name": "Google AI Pro 1",
                    "models": [
                        {
                            "model_id": "zerotts_202m_official",
                            "provider_id": "zerotts",
                            "execution_backend": "cpu",
                            "sample_rate": 48000,
                        }
                    ],
                },
                "last_seen_at": "2026-09-28T00:00:00+00:00",
            }
        ]
        with patch.dict(os.environ, {"TEST_COLIN_BROKER_TOKEN": "secret"}, clear=False):
            with patch(
                "omni_tts_core.remote_compute.client.urlopen",
                return_value=_Response(json.dumps(payload).encode("utf-8")),
            ):
                workers = self.client.list_workers()
        self.assertEqual(workers[0].capabilities.worker_id, "google-pro-1")
        self.assertEqual(workers[0].capabilities.models[0].sample_rate, 48000)

    def test_authenticated_call_rejects_missing_token(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ConfigError):
                self.client.get_job("job-1")

    def test_download_validates_sha256_before_writing(self) -> None:
        audio = b"RIFF-test-wave"
        metadata = RemoteTtsResultMetadata(
            sample_rate=24000,
            byte_size=len(audio),
            sha256=hashlib.sha256(audio).hexdigest(),
        )
        job = RemoteTtsJob(
            job_id="job-1",
            request=_request(),
            status=RemoteJobStatus.SUCCEEDED,
            result=metadata,
        )
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "result.wav"
            with patch.dict(os.environ, {"TEST_COLIN_BROKER_TOKEN": "secret"}, clear=False):
                with patch(
                    "omni_tts_core.remote_compute.client.urlopen",
                    return_value=_Response(audio),
                ):
                    self.client.download_result(job, output)
            self.assertEqual(output.read_bytes(), audio)

    def test_download_does_not_replace_output_on_bad_sha256(self) -> None:
        metadata = RemoteTtsResultMetadata(sample_rate=24000, sha256="0" * 64)
        job = RemoteTtsJob(
            job_id="job-1",
            request=_request(),
            status=RemoteJobStatus.SUCCEEDED,
            result=metadata,
        )
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "result.wav"
            output.write_bytes(b"keep")
            with patch.dict(os.environ, {"TEST_COLIN_BROKER_TOKEN": "secret"}, clear=False):
                with patch(
                    "omni_tts_core.remote_compute.client.urlopen",
                    return_value=_Response(b"wrong"),
                ):
                    with self.assertRaises(GenerationError):
                        self.client.download_result(job, output)
            self.assertEqual(output.read_bytes(), b"keep")


if __name__ == "__main__":
    unittest.main()
