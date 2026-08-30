from __future__ import annotations

import unittest

from omni_tts_core.ui_presenters import model_actions
from omni_tts_core.ui_presenters.model_actions import build_action_policy
from omni_tts_core.worker_installation import (
    gpu_installer_for_provider,
    provider_supports_gpu_install,
)
from omni_tts_shared.schemas import ModelStatus


def _status(
    model_id: str = "m",
    provider: str = "vieneu",
    installed: bool = True,
    required: bool = False,
    hf_cached: bool | None = None,
    worker_name: str = "",
    source_kind: str = "huggingface",
) -> ModelStatus:
    return ModelStatus(
        model_id=model_id,
        display_name=model_id,
        provider=provider,
        model_type="tts",
        hf_repo="",
        source_kind=source_kind,
        local_path="C:/x",
        installed=installed,
        required=required,
        size_mb=0,
        hf_cached=hf_cached,
        worker_name=worker_name,
    )


class EmptySelectionTest(unittest.TestCase):
    def test_every_per_model_action_is_off(self) -> None:
        policy = build_action_policy([])
        for action in (
            model_actions.DOWNLOAD, model_actions.REMOVE, model_actions.INSTALL_WORKER,
            model_actions.INSTALL_GPU, model_actions.OPEN_STORAGE, model_actions.IMPORT_LOCAL,
        ):
            state = policy.state(action)
            self.assertFalse(state.enabled, msg=action)
            self.assertEqual(state.reason, model_actions.NO_SELECTION)

    def test_global_actions_stay_on(self) -> None:
        policy = build_action_policy([])
        self.assertTrue(policy.state(model_actions.DOWNLOAD_REQUIRED).enabled)
        self.assertTrue(policy.state(model_actions.CATALOG).enabled)
        self.assertTrue(policy.state(model_actions.REFRESH).enabled)


class DownloadTest(unittest.TestCase):
    def test_targets_only_missing_models(self) -> None:
        policy = build_action_policy([
            _status("a", installed=True), _status("b", installed=False), _status("c", installed=False),
        ])
        state = policy.state(model_actions.DOWNLOAD)
        self.assertTrue(state.enabled)
        self.assertEqual(state.targets, ("b", "c"))

    def test_disabled_when_everything_is_present(self) -> None:
        state = build_action_policy([_status("a")]).state(model_actions.DOWNLOAD)
        self.assertFalse(state.enabled)
        self.assertIn("đã tải đủ", state.reason)

    def test_missing_hf_cache_counts_as_not_ready(self) -> None:
        state = build_action_policy([_status("a", installed=True, hf_cached=False)]).state(
            model_actions.DOWNLOAD
        )
        self.assertTrue(state.enabled)

    def test_manual_package_is_not_offered_as_download(self) -> None:
        state = build_action_policy([
            _status("local", installed=False, source_kind="manual")
        ]).state(model_actions.DOWNLOAD)
        self.assertFalse(state.enabled)


class ImportLocalTest(unittest.TestCase):
    def test_targets_only_missing_manual_packages(self) -> None:
        policy = build_action_policy([
            _status("a", installed=False, source_kind="manual"),
            _status("b", installed=True, source_kind="manual"),
            _status("c", installed=False),
        ])
        self.assertEqual(policy.state(model_actions.IMPORT_LOCAL).targets, ("a",))


class RemoveTest(unittest.TestCase):
    def test_skips_required_models(self) -> None:
        policy = build_action_policy([_status("req", required=True), _status("free")])
        self.assertEqual(policy.state(model_actions.REMOVE).targets, ("free",))

    def test_disabled_for_a_required_only_selection(self) -> None:
        state = build_action_policy([_status("req", required=True)]).state(model_actions.REMOVE)
        self.assertFalse(state.enabled)
        self.assertIn("bắt buộc", state.reason)

    def test_disabled_when_nothing_installed(self) -> None:
        state = build_action_policy([_status("a", installed=False)]).state(model_actions.REMOVE)
        self.assertFalse(state.enabled)
        self.assertIn("chưa tải", state.reason)


class ProviderActionTest(unittest.TestCase):
    def test_gpu_install_off_for_piper(self) -> None:
        state = build_action_policy([_status("p", provider="piper")]).state(
            model_actions.INSTALL_GPU
        )
        self.assertFalse(state.enabled)
        self.assertIn("Piper ONNX", state.reason)

    def test_gpu_install_runs_once_per_provider(self) -> None:
        """46 Piper rows must not trigger 46 installs."""
        selection = [_status(f"v{i}", provider="vieneu") for i in range(5)]
        state = build_action_policy(selection).state(model_actions.INSTALL_GPU)
        self.assertTrue(state.enabled)
        self.assertEqual(state.targets, ("v0",))

    def test_vieneu_v2_and_v3_workers_are_not_deduplicated_together(self) -> None:
        selection = [
            _status("v2", worker_name="vieneu_worker"),
            _status("v3", worker_name="vieneu_v3_worker"),
        ]
        state = build_action_policy(selection).state(model_actions.INSTALL_WORKER)
        self.assertEqual(state.targets, ("v2", "v3"))

    def test_mixed_selection_skips_unsupported_providers(self) -> None:
        selection = [_status("v", provider="vieneu"), _status("p", provider="piper")]
        state = build_action_policy(selection).state(model_actions.INSTALL_GPU)
        self.assertEqual(state.targets, ("v",))
        self.assertIn("Bỏ qua: Piper ONNX", state.reason)

    def test_worker_install_available_for_piper(self) -> None:
        state = build_action_policy([_status("p", provider="piper")]).state(
            model_actions.INSTALL_WORKER
        )
        self.assertTrue(state.enabled)


class OpenStorageTest(unittest.TestCase):
    def test_needs_exactly_one_selection(self) -> None:
        self.assertTrue(build_action_policy([_status("a")]).state(model_actions.OPEN_STORAGE))
        state = build_action_policy([_status("a"), _status("b")]).state(model_actions.OPEN_STORAGE)
        self.assertFalse(state.enabled)
        self.assertIn("một model", state.reason)


class GpuInstallerConsistencyTest(unittest.TestCase):
    def test_predicate_agrees_with_the_script_lookup(self) -> None:
        """Guards against the predicate drifting from the script map."""
        for provider in ("omnivoice", "vieneu", "qwen", "f5tts", "chatterbox", "piper", "valtec"):
            self.assertEqual(
                provider_supports_gpu_install(provider),
                gpu_installer_for_provider(provider) is not None,
                msg=provider,
            )


if __name__ == "__main__":
    unittest.main()
