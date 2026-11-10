from __future__ import annotations

import importlib
import os
import subprocess
import sys
from types import ModuleType
from unittest.mock import patch

import pytest


ALIASES = (
    ("omni_tts_core.remote_compute.client", "colin_colab_remote.broker.client"),
    ("omni_tts_core.remote_compute.models", "colin_colab_remote.broker.models"),
    ("omni_tts_core.remote_compute.profiles", "colin_colab_remote.broker.profiles"),
    ("omni_tts_core.remote_compute.failover", "colin_colab_remote.broker.failover"),
    ("omni_tts_core.remote_compute.local_broker", "colin_colab_remote.broker.local_broker"),
    ("omni_tts_ui_qt.pages.remote_compute_section", "colin_colab_remote.ui.remote_compute_section"),
    ("omni_tts_ui_qt.pages.colab_pairing_dialog", "colin_colab_remote.ui.colab_pairing_dialog"),
    ("omni_tts_ui_qt.widgets.broker_control", "colin_colab_remote.ui.broker_control"),
    ("omni_tts_ui_qt.broker_control", "colin_colab_remote.ui.broker_app"),
)


@pytest.mark.parametrize(("legacy", "canonical"), ALIASES)
def test_legacy_modules_share_the_canonical_module(legacy, canonical):
    assert importlib.import_module(legacy) is importlib.import_module(canonical)


def test_legacy_monkeypatch_changes_the_canonical_client():
    client_module = importlib.import_module("colin_colab_remote.broker.client")
    with patch("omni_tts_core.remote_compute.client.urlopen") as urlopen:
        assert client_module.urlopen is urlopen


@pytest.mark.parametrize(
    "module",
    ("omni_tts_core.remote_compute.local_broker", "colin_colab_remote.broker.local_broker"),
)
def test_broker_cli_entrypoints_keep_the_same_arguments(module):
    result = subprocess.run(
        [sys.executable, "-m", module, "--help"],
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 0, result.stderr
    assert "--confirm-stop" in result.stdout
    assert "{status,start,stop}" in result.stdout


@pytest.mark.parametrize("launch_id", ("", "managed-launch-123"))
def test_pairing_approval_preserves_managed_launch_identity(launch_id):
    from colin_colab_remote.broker.client import BrokerClient
    from colin_colab_remote.broker.models import BrokerConnectionOptions, PairingPreview

    preview = PairingPreview(
        pairing_id="pairing-123",
        worker_id="google-pro-1",
        launch_id=launch_id,
        provider="vieneu_v3",
        device="cuda",
        expires_at="2026-11-09T15:00:00+00:00",
        session_hours=12,
    )
    client = BrokerClient(BrokerConnectionOptions(base_url="https://broker.test"))
    with patch.object(BrokerClient, "_json_request", return_value={"status": "approved"}) as request:
        client.approve_pairing("ABCD-EFGH", preview)
    payload = request.call_args.kwargs["payload"]
    if launch_id:
        assert payload["launch_id"] == launch_id
    else:
        assert "launch_id" not in payload


def test_managed_dialog_button_loads_the_dialog_when_clicked(monkeypatch, tmp_path):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    from colin_colab_remote.ui import remote_compute_section

    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(remote_compute_section, "PROJECT_ROOT", tmp_path)
    opened = []

    class ManagedColabDialog:
        def __init__(self, parent):
            self.parent = parent

        def exec(self):
            opened.append(self.parent)

    module = ModuleType("colin_colab_remote.ui.managed_dialog")
    module.ManagedColabDialog = ManagedColabDialog
    monkeypatch.setitem(sys.modules, module.__name__, module)
    widget = remote_compute_section.RemoteComputeGroup()
    widget.managed_button.click()
    assert widget.managed_button.text() == "Quản lý Colab tự động"
    assert opened == [widget]
    assert not (tmp_path / "config" / "remote_compute_workers.json").exists()
    widget.close()
    app.processEvents()
