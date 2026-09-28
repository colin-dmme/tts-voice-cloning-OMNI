from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from omni_tts_core.remote_compute import failover
from omni_tts_core.remote_compute.models import (
    RemoteJobStatus,
    RemoteTtsJob,
    RemoteTtsRequest,
    RemoteTtsResultMetadata,
    WorkerCapabilities,
    WorkerModelCapability,
    WorkerProfile,
    WorkerRecord,
    WorkerSelectionSettings,
)
from omni_tts_core.remote_compute.profiles import WorkerProfileDocument
from omni_tts_shared.errors import GenerationError


MODEL_ID = "zerotts_202m_official"


def request() -> RemoteTtsRequest:
    return RemoteTtsRequest(
        client_job_id="studio-job",
        inference_unit_id="unit-1",
        idempotency_key="studio-job:unit-1",
        model_id=MODEL_ID,
        text="Xin chào",
    )


def profile(profile_id: str) -> WorkerProfile:
    return WorkerProfile(
        profile_id=profile_id,
        label=profile_id.upper(),
        broker_url="https://broker.test",
        worker_id=profile_id,
        auth_env="TEST_TOKEN",
    )


def worker(worker_id: str) -> WorkerRecord:
    return WorkerRecord(
        capabilities=WorkerCapabilities(
            worker_id=worker_id,
            display_name=worker_id.upper(),
            models=(
                WorkerModelCapability(
                    model_id=MODEL_ID,
                    provider_id="zerotts",
                    execution_backend="cpu",
                    sample_rate=48000,
                ),
            ),
        ),
        last_seen_at=datetime.now(timezone.utc).isoformat(),
    )


class FakeClient:
    def __init__(self, worker_id: str, terminal: RemoteTtsJob) -> None:
        self.worker_id = worker_id
        self.terminal = terminal
        self.submitted: list[RemoteTtsRequest] = []

    def list_workers(self) -> list[WorkerRecord]:
        return [worker("a"), worker("b"), worker("c")]

    def submit(self, item: RemoteTtsRequest, *, worker_id: str = "") -> RemoteTtsJob:
        self.submitted.append(item)
        return RemoteTtsJob(job_id=f"job-{worker_id}", request=item)

    def wait_for_terminal(self, _job_id: str, **_kwargs) -> RemoteTtsJob:
        return self.terminal

    def get_job_by_idempotency(self, _key: str) -> RemoteTtsJob:
        raise AssertionError("Không cần đối soát trong test này")

    def download_result(self, _job: RemoteTtsJob, destination: Path) -> Path:
        destination.write_bytes(b"RIFF-remote-result")
        return destination


class RemoteComputeFailoverTest(unittest.TestCase):
    def test_automatic_policy_moves_once_to_next_worker_after_retryable_error(self) -> None:
        self.assertTrue(
            hasattr(failover, "RemoteComputeCoordinator"),
            "Thiếu RemoteComputeCoordinator",
        )
        item = request()
        failed = RemoteTtsJob(
            job_id="job-a",
            request=item,
            status=RemoteJobStatus.FAILED,
            error="runtime disconnected",
            retryable=True,
            failure_kind="worker_unavailable",
        )
        succeeded = RemoteTtsJob(
            job_id="job-b",
            request=item,
            status=RemoteJobStatus.SUCCEEDED,
            result=RemoteTtsResultMetadata(
                sample_rate=48000,
                byte_size=len(b"RIFF-remote-result"),
                sha256="0" * 64,
            ),
        )
        clients = {"a": FakeClient("a", failed), "b": FakeClient("b", succeeded)}
        document = WorkerProfileDocument(
            profiles=[profile("a"), profile("b"), profile("c")],
            selection=WorkerSelectionSettings(
                selected_profile_id="a", switch_policy="automatic_failover"
            ),
        )
        coordinator = failover.RemoteComputeCoordinator(
            document,
            client_factory=lambda selected: clients[selected.profile_id],
        )

        with tempfile.TemporaryDirectory() as temp:
            outcome = coordinator.execute(item, Path(temp) / "result.wav")

        self.assertEqual(outcome.initial_profile_id, "a")
        self.assertEqual(outcome.final_profile_id, "b")
        self.assertEqual(outcome.attempted_profile_ids, ("a", "b"))
        self.assertTrue(clients["a"].submitted[0].idempotency_key.endswith(":a"))
        self.assertTrue(clients["b"].submitted[0].idempotency_key.endswith(":b"))

    def test_ask_policy_stops_when_user_rejects_switch(self) -> None:
        self.assertTrue(hasattr(failover, "RemoteComputeCoordinator"))
        item = request()
        failed = RemoteTtsJob(
            job_id="job-a",
            request=item,
            status=RemoteJobStatus.FAILED,
            error="runtime disconnected",
            retryable=True,
            failure_kind="worker_unavailable",
        )
        clients = {"a": FakeClient("a", failed)}
        document = WorkerProfileDocument(
            profiles=[profile("a"), profile("b")],
            selection=WorkerSelectionSettings(
                selected_profile_id="a", switch_policy="ask_before_switch"
            ),
        )
        prompts: list[tuple[str, str, str]] = []
        coordinator = failover.RemoteComputeCoordinator(
            document,
            client_factory=lambda selected: clients[selected.profile_id],
            confirm_switch=lambda old, new, reason: prompts.append(
                (old.profile_id, new.profile_id, reason)
            )
            or False,
        )

        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(GenerationError):
                coordinator.execute(item, Path(temp) / "result.wav")

        self.assertEqual(prompts, [("a", "b", "runtime disconnected")])


if __name__ == "__main__":
    unittest.main()
