from __future__ import annotations

import json
import os
import unittest
from urllib.error import URLError
from unittest.mock import patch

from omni_tts_core.remote_compute.client import BrokerClient
from omni_tts_core.remote_compute.models import BrokerConnectionOptions, PairingPreview, WorkerProfile
from omni_tts_shared.errors import GenerationError


def preview(**updates):
    return PairingPreview(**({"pairing_id": "id-1234567890123456", "worker_id": "google-pro-1", "provider": "vieneu_v3",
                             "device": "cpu", "expires_at": "2026-10-16T12:00:00+00:00", "session_hours": 12} | updates))


class Response:
    def __init__(self, payload):
        self.payload = payload
    def __enter__(self):
        return self
    def __exit__(self, *_):
        pass
    def read(self):
        return json.dumps(self.payload).encode()


class PairingClientTest(unittest.TestCase):
    def setUp(self):
        self.client = BrokerClient(BrokerConnectionOptions(base_url="https://broker.test", auth_env="PAIRING_TEST_TOKEN", max_retries=5))

    def test_inspect_does_not_approve_and_parses_only_public_metadata(self):
        with patch.dict(os.environ, {"PAIRING_TEST_TOKEN": "local-admin"}), patch(
            "omni_tts_core.remote_compute.client.urlopen", return_value=Response(preview().model_dump())) as request:
            result = self.client.inspect_pairing("abcd-efgh")
        self.assertEqual(result.worker_id, "google-pro-1")
        self.assertTrue(request.call_args.args[0].full_url.endswith("/inspect"))
        self.assertEqual(json.loads(request.call_args.args[0].data), {"user_code": "ABCD-EFGH"})

    def test_approve_binds_worker_provider_device_and_never_retries_uncertain_write(self):
        with patch.dict(os.environ, {"PAIRING_TEST_TOKEN": "local-admin"}), patch(
            "omni_tts_core.remote_compute.client.urlopen", side_effect=URLError("timeout")) as request:
            with self.assertRaises(GenerationError):
                self.client.approve_pairing("ABCD-EFGH", preview())
        self.assertEqual(request.call_count, 1)
        body = json.loads(request.call_args.args[0].data)
        self.assertEqual((body["worker_id"], body["provider"], body["device"]), ("google-pro-1", "vieneu_v3", "cpu"))
        self.assertNotIn("local-admin", request.call_args.args[0].full_url)

    def test_revoke_is_explicit_single_request(self):
        with patch.dict(os.environ, {"PAIRING_TEST_TOKEN": "local-admin"}), patch(
            "omni_tts_core.remote_compute.client.urlopen", return_value=Response({"status": "revoked", "sessions": 1})) as request:
            self.assertEqual(self.client.revoke_pairing("google-pro-1")["sessions"], 1)
        self.assertEqual(request.call_count, 1)
        self.assertTrue(request.call_args.args[0].full_url.endswith("/google-pro-1/revoke-pairing"))


class PairingDialogTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def dialog(self):
        from omni_tts_ui_qt.pages.colab_pairing_dialog import ColabPairingDialog
        return ColabPairingDialog(WorkerProfile(profile_id="google-pro-1", label="Google AI Pro 1", worker_id="google-pro-1", broker_url="https://broker.test"), "vieneu_v3_turbo")

    def test_wrong_worker_or_model_cannot_be_approved(self):
        dialog = self.dialog()
        for value in (preview(worker_id="google-pro-2"), preview(provider="zerotts")):
            dialog._inspected(value)
            self.assertIsNone(dialog.preview)
            self.assertFalse(dialog.approve_button.isEnabled())
        dialog.close()

    def test_inspection_needs_second_click_and_code_change_invalidates_preview(self):
        dialog = self.dialog()
        dialog.code.setText("ABCD-EFGH")
        with patch.object(dialog.client, "approve_pairing") as approve:
            dialog._inspected(preview())
            self.assertTrue(dialog.approve_button.isEnabled())
            approve.assert_not_called()
            dialog.code.setText("ABCD-EFGJ")
            self.assertFalse(dialog.approve_button.isEnabled())
            self.assertIsNone(dialog.preview)
        dialog.close()

    def test_public_notebook_url_has_no_credential(self):
        from omni_tts_ui_qt.pages.colab_pairing_dialog import notebook_url
        self.assertEqual(notebook_url("google-pro-2"), "https://colab.research.google.com/github/colin-dmme/tts-voice-cloning-OMNI/blob/main/colab/Colin-TTS-Pairing-google-pro-2.ipynb")
        with self.assertRaises(ValueError):
            notebook_url("../invalid")

