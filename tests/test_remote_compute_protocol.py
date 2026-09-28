from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from pydantic import ValidationError

from omni_tts_core.remote_compute.models import (
    RemoteJobStatus,
    RemoteTtsJob,
    RemoteTtsRequest,
    WorkerCapabilities,
    WorkerModelCapability,
    WorkerProfile,
    WorkerRecord,
    WorkerRuntimeInfo,
    WorkerSelectionSettings,
)
from omni_tts_core.remote_compute.profiles import (
    WorkerProfileDocument,
    WorkerProfileStore,
)


def _capabilities(**overrides) -> WorkerCapabilities:
    payload = {
        "worker_id": "colab-a",
        "display_name": "COLAB-A",
        "worker_type": "google_colab",
        "runtime": WorkerRuntimeInfo(platform="linux", cpu="x86_64", ram_mb=12000),
        "models": (
            WorkerModelCapability(
                model_id="zerotts_202m_official",
                provider_id="zerotts",
                execution_backend="cpu",
                sample_rate=48000,
            ),
        ),
    }
    payload.update(overrides)
    return WorkerCapabilities(**payload)


class RemoteComputeProtocolTest(unittest.TestCase):
    def test_worker_capabilities_require_protocol_and_unique_models(self) -> None:
        worker = _capabilities()
        self.assertEqual(worker.protocol_version, "1")
        self.assertEqual(worker.models[0].model_id, "zerotts_202m_official")
        with self.assertRaises(ValidationError):
            _capabilities(protocol_version="2")
        with self.assertRaises(ValidationError):
            _capabilities(models=(worker.models[0], worker.models[0]))

    def test_job_request_has_stable_idempotency_identity(self) -> None:
        request = RemoteTtsRequest(
            client_job_id="studio-job-1",
            inference_unit_id="unit-0001",
            idempotency_key="studio-job-1:unit-0001:settings-hash",
            model_id="zerotts_202m_official",
            text="Xin chào.",
            speaker_id="maichi",
            provider_options={"audio_topk": 25},
        )
        restored = RemoteTtsRequest.model_validate_json(request.model_dump_json())
        self.assertEqual(restored, request)

    def test_failed_job_preserves_retryable_contract_for_failover(self) -> None:
        job = RemoteTtsJob(
            job_id="job-1",
            request=RemoteTtsRequest(
                client_job_id="client-1",
                inference_unit_id="unit-1",
                idempotency_key="client-1:unit-1",
                model_id="zerotts_202m_official",
                text="Xin chào",
            ),
            status=RemoteJobStatus.FAILED,
            error="Colab runtime disconnected",
            retryable=True,
            failure_kind="worker_unavailable",
        )
        self.assertIn("retryable", type(job).model_fields)
        self.assertTrue(job.retryable)
        self.assertEqual(job.failure_kind, "worker_unavailable")

    def test_three_profiles_persist_without_secret_values(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "workers.json"
            store = WorkerProfileStore(path)
            for suffix in ("a", "b", "c"):
                store.upsert(
                    WorkerProfile(
                        profile_id=f"colab-{suffix}",
                        label=f"COLAB-{suffix.upper()}",
                        broker_url="https://broker.example.test",
                        worker_id=f"colab-{suffix}",
                        auth_env=f"COLIN_BROKER_SECRET_{suffix.upper()}",
                    )
                )
            document = store.load()
            self.assertEqual(len(document.profiles), 3)
            self.assertEqual(document.selection.selected_profile_id, "colab-a")
            persisted = path.read_text(encoding="utf-8")
            self.assertNotIn("secret-value", persisted)

    def test_selection_policy_supports_error_only_automatic_failover(self) -> None:
        selected = WorkerSelectionSettings(switch_policy="selected_only")
        prompt = WorkerSelectionSettings(switch_policy="ask_before_switch")
        try:
            automatic = WorkerSelectionSettings(switch_policy="automatic_failover")
        except ValidationError as error:
            self.fail(f"automatic_failover phải là policy hợp lệ: {error}")
        self.assertEqual(selected.switch_policy, "selected_only")
        self.assertEqual(prompt.switch_policy, "ask_before_switch")
        self.assertEqual(automatic.switch_policy, "automatic_failover")
        with self.assertRaises(ValidationError):
            WorkerSelectionSettings(switch_policy="round_robin")

    def test_removing_selected_profile_selects_next_profile(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = WorkerProfileStore(Path(temp_dir) / "workers.json")
            document = WorkerProfileDocument(
                profiles=[
                    WorkerProfile(
                        profile_id="a",
                        label="A",
                        broker_url="https://broker.test",
                        worker_id="a",
                    ),
                    WorkerProfile(
                        profile_id="b",
                        label="B",
                        broker_url="https://broker.test",
                        worker_id="b",
                    ),
                ],
                selection=WorkerSelectionSettings(selected_profile_id="a"),
            )
            store.save(document)
            updated = store.remove("a")
            self.assertEqual(updated.selection.selected_profile_id, "b")

    def test_profile_priority_order_can_be_changed_and_persisted(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = WorkerProfileStore(Path(temp_dir) / "workers.json")
            for profile_id in ("a", "b", "c"):
                store.upsert(
                    WorkerProfile(
                        profile_id=profile_id,
                        label=profile_id.upper(),
                        broker_url="https://broker.test",
                        worker_id=profile_id,
                    )
                )

            self.assertTrue(
                hasattr(store, "reorder"),
                "WorkerProfileStore phải hỗ trợ lưu thứ tự ưu tiên",
            )
            reordered = store.reorder(["c", "a", "b"])

            self.assertEqual(
                [profile.profile_id for profile in reordered.profiles],
                ["c", "a", "b"],
            )
            self.assertEqual(
                [profile.profile_id for profile in store.load().profiles],
                ["c", "a", "b"],
            )

    def test_automatic_failover_selects_next_online_compatible_profile(self) -> None:
        try:
            from omni_tts_core.remote_compute.failover import choose_failover
        except ModuleNotFoundError as error:
            self.fail(f"Thiếu bộ điều phối failover: {error}")

        document = WorkerProfileDocument(
            profiles=[
                WorkerProfile(
                    profile_id=profile_id,
                    label=profile_id.upper(),
                    broker_url="https://broker.test",
                    worker_id=profile_id,
                    enabled=enabled,
                )
                for profile_id, enabled in (("a", True), ("b", True), ("c", False))
            ],
            selection=WorkerSelectionSettings(
                selected_profile_id="a", switch_policy="automatic_failover"
            ),
        )
        workers = [
            WorkerRecord(
                capabilities=_capabilities(worker_id="b", display_name="B"),
                last_seen_at="2026-09-28T10:00:00+00:00",
            ),
            WorkerRecord(
                capabilities=_capabilities(
                    worker_id="c",
                    display_name="C",
                    models=(
                        WorkerModelCapability(
                            model_id="different-model",
                            provider_id="other",
                            execution_backend="cpu",
                            sample_rate=24000,
                        ),
                    ),
                ),
                last_seen_at="2026-09-28T10:00:00+00:00",
            ),
        ]

        decision = choose_failover(
            document,
            workers,
            model_id="zerotts_202m_official",
            failed_profile_ids={"a"},
            now=datetime(2026, 9, 28, 10, 1, tzinfo=timezone.utc),
        )

        self.assertIsNotNone(decision)
        self.assertEqual(decision.profile.profile_id, "b")
        self.assertFalse(decision.requires_confirmation)

    def test_ask_policy_returns_confirmation_and_rejects_stale_worker(self) -> None:
        try:
            from omni_tts_core.remote_compute.failover import choose_failover
        except ModuleNotFoundError as error:
            self.fail(f"Thiếu bộ điều phối failover: {error}")

        document = WorkerProfileDocument(
            profiles=[
                WorkerProfile(
                    profile_id=profile_id,
                    label=profile_id.upper(),
                    broker_url="https://broker.test",
                    worker_id=profile_id,
                )
                for profile_id in ("a", "b", "c")
            ],
            selection=WorkerSelectionSettings(
                selected_profile_id="a", switch_policy="ask_before_switch"
            ),
        )
        workers = [
            WorkerRecord(
                capabilities=_capabilities(worker_id="b", display_name="B"),
                last_seen_at="2026-09-28T09:55:00+00:00",
            ),
            WorkerRecord(
                capabilities=_capabilities(worker_id="c", display_name="C"),
                last_seen_at="2026-09-28T10:00:30+00:00",
            ),
        ]

        decision = choose_failover(
            document,
            workers,
            model_id="zerotts_202m_official",
            failed_profile_ids={"a"},
            now=datetime(2026, 9, 28, 10, 1, tzinfo=timezone.utc),
            stale_after_seconds=120,
        )

        self.assertIsNotNone(decision)
        self.assertEqual(decision.profile.profile_id, "c")
        self.assertTrue(decision.requires_confirmation)


if __name__ == "__main__":
    unittest.main()
