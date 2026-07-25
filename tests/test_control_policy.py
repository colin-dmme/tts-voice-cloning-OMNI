from __future__ import annotations

import unittest

from omni_tts_core.ui_presenters.control_policy import (
    NEUTRAL_PITCH,
    NEUTRAL_SPEED,
    build_policy,
)
from omni_tts_shared.schemas import ModelCapabilities, RuntimeStatus


class _Spec:
    def __init__(self, model_id="m", provider="vieneu", display_name="Model X") -> None:
        self.model_id = model_id
        self.provider = provider
        self.display_name = display_name
        self.catalog_info: dict = {}


def _caps(**overrides) -> ModelCapabilities:
    base = dict(
        supported_languages=["vi"],
        supports_speed=True,
        supports_pitch_shift=False,
        supports_emotion=False,
        emotions=[],
    )
    base.update(overrides)
    return ModelCapabilities(**base)


def _runtime(gpu: bool = True) -> RuntimeStatus:
    return RuntimeStatus(
        model_id="m",
        display_name="Model X",
        provider="vieneu",
        installed=True,
        gpu_available=gpu,
        actual_device="auto-cuda" if gpu else "cpu",
        message="",
    )


def _policy(spec=None, caps=None, runtime=None, **flags):
    defaults = dict(
        supports_codec=False, supports_sampling=False,
        supports_f5=False, supports_chatterbox=False,
    )
    defaults.update(flags)
    return build_policy(
        spec=spec or _Spec(),
        capabilities=caps or _caps(),
        runtime_status=runtime or _runtime(),
        **defaults,
    )


class DeviceTargetsTest(unittest.TestCase):
    def test_cuda_offered_when_gpu_available(self) -> None:
        policy = _policy(runtime=_runtime(gpu=True))
        self.assertIn("cuda", [value for _label, value in policy.device_targets])
        self.assertEqual(policy.device_note, "")

    def test_cuda_hidden_for_cpu_only_model(self) -> None:
        policy = _policy(spec=_Spec(provider="piper"), runtime=_runtime(gpu=False))
        values = [value for _label, value in policy.device_targets]
        self.assertNotIn("cuda", values)
        self.assertEqual(values, ["auto", "cpu"])
        self.assertIn("CUDA", policy.device_note)

    def test_default_device_falls_back_when_unavailable(self) -> None:
        policy = _policy(runtime=_runtime(gpu=False))
        self.assertEqual(policy.default_device("cuda"), "auto")
        self.assertEqual(policy.default_device("cpu"), "cpu")


class LanguageTest(unittest.TestCase):
    def test_languages_come_from_capabilities(self) -> None:
        policy = _policy(caps=_caps(supported_languages=["auto", "en", "zh"]))
        self.assertEqual([code for _label, code in policy.languages], ["auto", "en", "zh"])

    def test_default_language_falls_back_to_first_supported(self) -> None:
        policy = _policy(caps=_caps(supported_languages=["en"]))
        self.assertEqual(policy.default_language("vi"), "en")
        self.assertEqual(policy.default_language("en"), "en")


class ControlStateTest(unittest.TestCase):
    def test_unsupported_controls_carry_a_reason(self) -> None:
        policy = _policy(caps=_caps(supports_speed=False))
        self.assertFalse(policy.speed)
        self.assertIn("tốc độ", policy.speed.reason.lower())
        self.assertFalse(policy.pitch)
        self.assertTrue(policy.pitch.reason)

    def test_supported_control_has_no_reason(self) -> None:
        policy = _policy(caps=_caps(supports_speed=True))
        self.assertTrue(policy.speed)
        self.assertEqual(policy.speed.reason, "")

    def test_emotion_requires_both_flag_and_list(self) -> None:
        self.assertFalse(_policy(caps=_caps(supports_emotion=True, emotions=[])).emotion)
        policy = _policy(caps=_caps(supports_emotion=True, emotions=["natural", "storytelling"]))
        self.assertTrue(policy.emotion)
        self.assertEqual(policy.emotions, ("natural", "storytelling"))

    def test_gpu_safety_reason_when_cpu_only(self) -> None:
        policy = _policy(runtime=_runtime(gpu=False))
        self.assertFalse(policy.gpu_safety)
        self.assertIn("CPU", policy.gpu_safety.reason)


class TuningTest(unittest.TestCase):
    def test_no_tuning_when_nothing_supported(self) -> None:
        self.assertFalse(_policy().has_tuning)

    def test_tuning_when_any_group_applies(self) -> None:
        self.assertTrue(_policy(supports_sampling=True).has_tuning)
        self.assertTrue(_policy(supports_f5=True).has_tuning)
        self.assertTrue(_policy(supports_chatterbox=True).has_tuning)
        self.assertTrue(_policy(caps=_caps(supports_emotion=True, emotions=["a"])).has_tuning)

    def test_tuning_title_names_the_provider(self) -> None:
        policy = _policy(spec=_Spec(provider="piper"), supports_sampling=True)
        self.assertEqual(policy.tuning_title, "Tinh chỉnh riêng · Piper ONNX")

    def test_groups_name_only_what_the_model_exposes(self) -> None:
        """A GUI shows a provider group only when its id is listed here — that is
        what keeps Chatterbox knobs off a Piper model."""
        self.assertEqual(_policy(supports_f5=True).tuning_groups, ("f5",))
        self.assertEqual(_policy(supports_chatterbox=True).tuning_groups, ("chatterbox",))
        self.assertEqual(_policy(supports_codec=True).tuning_groups, ("vieneu",))
        self.assertEqual(
            _policy(caps=_caps(supports_emotion=True, emotions=["a"])).tuning_groups,
            ("vieneu",),
        )

    def test_no_groups_for_a_provider_without_tuning(self) -> None:
        policy = _policy(spec=_Spec(provider="piper"))
        self.assertEqual(policy.tuning_groups, ())
        self.assertIn("Piper ONNX", policy.tuning_absent_note())


class PunctuationPauseCapabilityTest(unittest.TestCase):
    def test_piper_exposes_punctuation_pauses(self) -> None:
        self.assertTrue(_policy(spec=_Spec(provider="piper")).punctuation_pauses)

    def test_other_providers_hide_punctuation_pauses(self) -> None:
        for provider in ("vieneu", "omnivoice", "qwen", "valtec", "f5tts", "chatterbox"):
            self.assertFalse(_policy(spec=_Spec(provider=provider)).punctuation_pauses)


class GpuScopeTest(unittest.TestCase):
    def test_note_says_the_gate_is_shared_by_every_cuda_model(self) -> None:
        policy = _policy(spec=_Spec(provider="vieneu"), runtime=_runtime(gpu=True))
        self.assertIn("mọi model chạy CUDA", policy.gpu_scope_note)

    def test_chatterbox_note_points_at_its_own_worker_guard(self) -> None:
        policy = _policy(spec=_Spec(provider="chatterbox"), runtime=_runtime(gpu=True))
        self.assertIn("worker", policy.gpu_scope_note)

    def test_cpu_model_note_explains_the_gate_does_not_run(self) -> None:
        policy = _policy(runtime=_runtime(gpu=False))
        self.assertIn("CPU", policy.gpu_scope_note)


class ControlTooltipTest(unittest.TestCase):
    def test_supported_control_still_explains_itself(self) -> None:
        """Hiding the reason when a control works must not leave it with no help."""
        policy = _policy(caps=_caps(supports_speed=True))
        self.assertEqual(policy.speed.reason, "")
        self.assertIn("Tốc độ đọc", policy.speed.tooltip)

    def test_unsupported_control_shows_the_blocking_reason(self) -> None:
        policy = _policy(caps=_caps(supports_speed=False))
        self.assertEqual(policy.speed.tooltip, policy.speed.reason)


class NeutralValuesTest(unittest.TestCase):
    def test_neutral_constants(self) -> None:
        self.assertEqual(NEUTRAL_SPEED, 1.0)
        self.assertEqual(NEUTRAL_PITCH, 0.0)


if __name__ == "__main__":
    unittest.main()
