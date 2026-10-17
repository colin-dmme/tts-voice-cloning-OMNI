import json
import os
from unittest.mock import patch

import pytest

from omni_tts_core.remote_compute.local_broker import LocalBrokerManager, LocalBrokerStatus


def test_status_does_not_claim_online_based_only_on_runtime_file(tmp_path):
    (tmp_path / "runtime.json").write_text(json.dumps({"status": "online", "local_port": 18787, "hostname": "broker.test"}))
    manager = LocalBrokerManager(tmp_path)
    with patch.object(manager, "_task", return_value={"state": "Ready", "enabled": False}), patch.object(manager, "_health", return_value=False):
        result = manager.status()
    assert not result.local_healthy
    assert not result.auto_start


def test_start_and_stop_only_control_the_exact_broker_task(tmp_path):
    manager = LocalBrokerManager(tmp_path)
    on = LocalBrokerStatus(task_state="Running", auto_start=True, local_healthy=True, desired_running=True)
    off = LocalBrokerStatus(task_state="Ready", auto_start=False, local_healthy=False, desired_running=False)
    with patch.object(manager, "_task", return_value={}) as task, patch.object(manager, "_wait", side_effect=[on, off]):
        assert manager.start().local_healthy
        assert json.loads((tmp_path / "background-control.json").read_text())["desired_state"] == "running"
        assert not manager.stop().local_healthy
    assert [call.args[0] for call in task.call_args_list] == ["start", "disable"]
    assert json.loads((tmp_path / "background-control.json").read_text())["desired_state"] == "stopped"


def test_local_control_rejects_untrusted_port_and_does_not_read_secrets(tmp_path):
    (tmp_path / "runtime.json").write_text('{"local_port":80,"hostname":"attacker.test"}')
    manager = LocalBrokerManager(tmp_path)
    with patch.object(manager, "_task", return_value={"state":"Ready","enabled":True}), patch.object(manager, "_health") as health:
        status = manager.status()
    assert not status.local_healthy
    health.assert_not_called()


def test_controller_process_uses_no_console_and_fixed_commands(tmp_path):
    manager = LocalBrokerManager(tmp_path)
    with patch("omni_tts_core.remote_compute.local_broker.subprocess.run") as run:
        run.return_value.stdout = '{"state":"Running","enabled":true}'
        run.return_value.returncode = 0
        assert manager._task("status")["state"] == "Running"
    assert run.call_args.kwargs["creationflags"] == 0x08000000
    assert "Colin TTS Compute Broker" in run.call_args.args[0][-1]
    assert not run.call_args.kwargs.get("shell")


def test_two_control_windows_cannot_race_start_and_stop(tmp_path):
    manager = LocalBrokerManager(tmp_path)
    other = LocalBrokerManager(tmp_path)
    with manager._operation(), patch.object(other, "_task") as task:
        with pytest.raises(RuntimeError, match="cửa sổ khác"):
            other.start()
    task.assert_not_called()
    assert not (tmp_path / "background-control.json").exists()


def test_broker_widget_has_explicit_stop_confirmation_and_does_not_stop_on_close(tmp_path):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication, QMessageBox
    from omni_tts_ui_qt.widgets.broker_control import BrokerControlWidget
    app = QApplication.instance() or QApplication([])
    manager = LocalBrokerManager(tmp_path)
    widget = BrokerControlWidget(manager=manager, auto_refresh=False)
    widget._completed(LocalBrokerStatus(task_state="Running", auto_start=True, local_healthy=True, desired_running=True))
    with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.No), patch.object(manager, "stop") as stop:
        widget.stop_broker()
        widget.close()
        stop.assert_not_called()
