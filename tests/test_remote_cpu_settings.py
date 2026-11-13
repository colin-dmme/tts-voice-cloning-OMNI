import pytest
from pydantic import ValidationError

from colin_studio_tts_mcp.contracts import TextGenerationInput
from omni_tts_core.model_registry import ModelRegistry
from omni_tts_core.ui_presenters.control_policy import build_policy
from omni_tts_core.ui_presenters.settings_state import GenerationSettings
from omni_tts_shared.schemas import GenerateSpeechRequest, RuntimeStatus


CPU_TARGET = {"kind": "existing_worker", "worker_profile_id": "pc-test", "backend": "cpu", "include_local": False}


def test_explicit_remote_target_survives_schema_and_legacy_is_unambiguous():
    request = GenerateSpeechRequest(text="Xin chào", runtime_target="remote", remote_compute=CPU_TARGET)
    assert request.remote_compute.model_dump() == CPU_TARGET
    assert GenerateSpeechRequest(text="Xin chào", runtime_target="remote").remote_compute is None


@pytest.mark.parametrize("runtime_target,target", [
    ("auto", CPU_TARGET),
    ("remote", {**CPU_TARGET, "backend": "cuda"}),
    ("remote", {**CPU_TARGET, "token": "fake"}),
    ("remote_cpu", CPU_TARGET),
])
def test_invalid_or_ui_only_targets_are_rejected(runtime_target, target):
    with pytest.raises(ValidationError):
        GenerateSpeechRequest(text="Xin chào", runtime_target=runtime_target, remote_compute=target)


def test_cpu_combo_round_trip_uses_wire_target_and_retains_profile():
    from omni_tts_core.runtime_devices import normalize_runtime_target, runtime_choice, runtime_choice_settings
    from omni_tts_shared.errors import ConfigError

    settings = GenerationSettings(model_id="piper_ngoc_huyen", **runtime_choice_settings("remote_cpu", "pc-test"))
    for restored in (
        GenerationSettings.from_preferences(settings.to_preferences()),
        GenerationSettings.from_snapshot(settings.to_snapshot()),
    ):
        request = restored.to_request("Xin chào")
        assert request.runtime_target == "remote"
        assert request.remote_compute.model_dump() == CPU_TARGET
        assert runtime_choice(restored.runtime_target, restored.remote_execution_kind) == "remote_cpu"
    assert runtime_choice("remote", "") == "remote"
    assert runtime_choice_settings("auto", "pc-test") == {"runtime_target": "auto"}
    with pytest.raises(ConfigError):
        normalize_runtime_target("remote_cpu")


def test_mcp_keeps_cpu_profile_and_disallows_advanced_target_overrides():
    payload = {"text": "Xin chào", "model_id": "zerotts_202m_official", "generation": {
        "runtime_target": "remote", "remote_compute": CPU_TARGET,
    }}
    request = TextGenerationInput.model_validate(payload).to_settings().to_request(payload["text"])
    assert request.remote_compute.model_dump() == CPU_TARGET
    payload["generation"]["advanced"] = {"remote_worker_profile_id": "pc-wrong"}
    with pytest.raises(ValueError, match="remote_worker_profile_id"):
        TextGenerationInput.model_validate(payload).to_settings()


def test_restoring_legacy_preferences_does_not_reuse_existing_pc_target(tmp_path):
    import json

    from omni_tts_core.user_state import restore_user_state

    saved = tmp_path / "user_state" / "settings.json"
    saved.parent.mkdir()
    saved.write_text(json.dumps({"ui_qt": {"runtime_target": "remote"}}), encoding="utf-8")
    current = tmp_path / "config" / "ui_qt.json"
    current.parent.mkdir()
    current.write_text(json.dumps({
        "runtime_target": "remote", "remote_execution_kind": "existing_worker",
        "remote_worker_profile_id": "pc-old", "remote_execution_backend": "cpu",
    }), encoding="utf-8")
    restore_user_state(tmp_path, overwrite_settings=True)
    settings = GenerationSettings.from_preferences(json.loads(current.read_text(encoding="utf-8")))
    assert settings.runtime_target == "remote"
    assert settings.to_request("Xin chào").remote_compute is None


@pytest.mark.parametrize("model_id", ["piper_ngoc_huyen", "zerotts_202m_official", "vieneu_v3_turbo"])
def test_remote_cpu_choices_do_not_depend_on_local_installation(model_id):
    spec = ModelRegistry().get(model_id)
    policy = _policy_for(spec)
    assert ("CPU máy khác", "remote_cpu") in policy.device_targets


def test_higgs_keeps_its_endpoint_choice():
    policy = _policy_for(ModelRegistry().get("higgs_tts3_remote"))
    assert policy.device_targets == (("GPU từ xa (server quyết định)", "auto"),)


def test_qt_cpu_selection_keeps_profile_after_history_restore(tmp_path, monkeypatch):
    from unittest.mock import Mock

    from PySide6.QtWidgets import QApplication

    from colin_colab_remote.broker.models import WorkerProfile
    from colin_colab_remote.broker.profiles import WorkerProfileStore
    from omni_tts_core.app_controller import AppController
    from omni_tts_ui_qt.context import AppContext
    from omni_tts_ui_qt.pages.settings_panel import SettingsPanel
    from omni_tts_ui_qt.preferences import QtPreferences

    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance() or QApplication([])
    panel = SettingsPanel(AppContext(
        controller=AppController(), probe=Mock(), safety_gate=Mock(),
        preferences=QtPreferences(path=tmp_path / "ui_qt.json"),
        log=Mock(), set_worker_status=Mock(), show_page=Mock(), register_settings_provider=Mock(),
    ))
    store = WorkerProfileStore(tmp_path / "workers.json")
    for worker_id in ("google-pro-1", "pc-other", "pc-test"):
        store.upsert(WorkerProfile(
            profile_id=worker_id, worker_id=worker_id, label=worker_id,
            broker_url="https://broker.example.test",
        ))
    panel.remote_compute_group.store = store
    panel.load_preferences({
        "model_id": "piper_ngoc_huyen", "runtime_target": "remote",
        "remote_execution_kind": "existing_worker", "remote_execution_backend": "cpu",
        "remote_worker_profile_id": "pc-test",
    })
    try:
        assert panel.device_combo.currentData() == "remote_cpu"
        assert panel.remote_compute_group.pc_profile.findData("google-pro-1") == -1
        assert panel.remote_compute_group.pc_profile.currentData() == "pc-test"
        assert panel.current_settings().to_request("Xin chào").remote_compute.model_dump() == CPU_TARGET
        panel.device_combo.setCurrentIndex(panel.device_combo.findData("auto"))
        assert panel.current_settings().to_request("Xin chào").remote_compute is None
        assert store.load().selection.selected_profile_id == "google-pro-1"
    finally:
        panel.close()
        app.processEvents()


def test_device_dialog_approves_only_after_inspection_and_saves_scoped_profile(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import Mock

    from PySide6.QtWidgets import QApplication

    from colin_colab_remote.broker.models import WorkerProfile
    from colin_colab_remote.broker.profiles import WorkerProfileStore
    from colin_remote_compute.ui import pc_devices_dialog

    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance() or QApplication([])
    store = WorkerProfileStore(tmp_path / "workers.json")
    source = WorkerProfile(
        profile_id="google-pro-1", worker_id="google-pro-1", label="Google",
        broker_url="https://broker.example.test", auth_token_file=tmp_path / "local-token.txt",
    )
    store.upsert(source)
    client = Mock()
    client.list_pc_devices.return_value = []
    preview = {
        "pairing_id": "a" * 32, "worker_id": "pc-test-box", "display_name": "Test CPU",
        "runtime": {"platform": "Windows", "cpu": "Test CPU", "ram_mb": 16384},
        "models": [{"model_id": "piper_ngoc_huyen", "execution_backend": "cpu"}],
    }
    client.inspect_pc_pairing.return_value = preview
    client.approve_pc_pairing.return_value = {
        "status": "approved", "worker_id": "pc-test-box", "display_name": "Test CPU",
    }
    monkeypatch.setattr(pc_devices_dialog, "pairing_client", lambda _source: client)
    monkeypatch.setattr(pc_devices_dialog, "QThreadPool", SimpleNamespace(
        globalInstance=lambda: SimpleNamespace(start=lambda task: task.run()),
    ))
    dialog = pc_devices_dialog.PcDevicesDialog(source, store)
    try:
        dialog.code.setText("abcd-efgh")
        assert not dialog.approve_button.isEnabled()
        dialog.inspect_code()
        client.inspect_pc_pairing.assert_called_once_with("ABCD-EFGH")
        client.approve_pc_pairing.assert_not_called()
        assert dialog.approve_button.isEnabled()
        dialog.code.setText("jklm-npqr")
        assert not dialog.approve_button.isEnabled()
        dialog.code.setText("ABCD-EFGH")
        dialog.inspect_code()
        dialog.approve()
        client.approve_pc_pairing.assert_called_once_with("ABCD-EFGH", preview)
        document = store.load()
        assert document.selection.selected_profile_id == "google-pro-1"
        selected = next(profile for profile in document.profiles if profile.profile_id == dialog.selected_profile_id)
        assert (selected.worker_kind, selected.worker_id, selected.broker_url, selected.auth_token_file) == (
            "remote_pc", "pc-test-box", source.broker_url, source.auth_token_file,
        )
    finally:
        dialog.close()
        app.processEvents()


def _policy_for(spec):
    return build_policy(
        spec=spec,
        capabilities=spec.capabilities,
        runtime_status=RuntimeStatus(
            model_id=spec.model_id, display_name=spec.display_name,
            provider=spec.provider, installed=False,
        ),
        supports_codec=False, supports_sampling=False, supports_f5=False, supports_chatterbox=False,
    )
