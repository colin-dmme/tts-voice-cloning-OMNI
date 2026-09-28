from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from pydantic import ValidationError

from omni_tts_core.remote_compute.models import (
    RemoteTtsRequest,
    WorkerCapabilities,
    WorkerModelCapability,
    WorkerProfile,
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

    def test_selection_policy_has_no_automatic_account_rotation(self) -> None:
        selected = WorkerSelectionSettings(switch_policy="selected_only")
        prompt = WorkerSelectionSettings(switch_policy="ask_before_switch")
        self.assertEqual(selected.switch_policy, "selected_only")
        self.assertEqual(prompt.switch_policy, "ask_before_switch")
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


if __name__ == "__main__":
    unittest.main()
