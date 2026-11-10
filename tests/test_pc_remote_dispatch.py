from types import SimpleNamespace

from colin_colab_remote.client import should_manage
from colin_colab_remote.store import ColabStore
from colin_colab_remote.broker.models import WorkerProfile
from omni_tts_core.ui_presenters.settings_state import GenerationSettings


def test_pc_uses_shared_queue_even_without_colab(tmp_path, monkeypatch):
    monkeypatch.setenv("COLIN_COLAB_DATA_DIR", str(tmp_path))
    settings = GenerationSettings(
        model_id="piper_ngoc_huyen", runtime_target="remote",
        remote_execution_kind="existing_worker", remote_worker_profile_id="pc-caro-test",
        remote_execution_backend="cpu",
    )
    assert should_manage(settings)
    assert not should_manage(GenerationSettings(model_id="zerotts_202m_official", runtime_target="remote"))


def test_shared_store_claims_pc_jobs_without_claiming_colab(tmp_path):
    store = ColabStore(tmp_path)
    legacy = store.create("text", {"text": "Colab", "settings": {}})
    pc = store.create("text", {"text": "PC", "settings": {},
                                "remote_target": {"kind": "existing_worker", "profile": {}}})
    assert store.next_job(allow_colab=False)["job_id"] == pc["job_id"]
    assert store.get(legacy["job_id"])["status"] == "queued"


def test_pc_profile_is_not_a_legacy_failover_candidate():
    from colin_colab_remote.broker.failover import choose_failover
    from colin_colab_remote.broker.models import WorkerCapabilities, WorkerRecord, WorkerSelectionSettings, utc_now
    from colin_colab_remote.broker.profiles import WorkerProfileDocument

    profile = WorkerProfile(profile_id="pc-caro-test", label="CAROPC", broker_url="https://example.invalid",
                            worker_id="pc-caro-test", worker_kind="remote_pc")
    record = WorkerRecord(last_seen_at=utc_now(), capabilities=WorkerCapabilities(
        worker_id=profile.worker_id, worker_type="remote_pc", display_name="CAROPC",
        models=[{"model_id": "zerotts_202m_official", "provider_id": "zerotts",
                 "execution_backend": "cpu", "sample_rate": 48000}],
    ))
    document = WorkerProfileDocument(profiles=[profile], selection=WorkerSelectionSettings(
        switch_policy="automatic_failover"))
    assert choose_failover(document, [record], model_id="zerotts_202m_official",
                           failed_profile_ids=set()) is None
