"""Which generation controls actually apply to a given model.

Every model declares what it supports (`capabilities` in models.yaml) and the
resolved runtime says whether CUDA is really available. This module turns those
facts into one policy object so a GUI never guesses: a control the model cannot
honour is disabled with a reason instead of silently doing nothing (or failing
at generation time, as picking CUDA for a CPU-only model would).

Pure and UI-agnostic; `AppController.control_policy()` supplies the inputs.
"""

from __future__ import annotations

from dataclasses import dataclass

from omni_tts_core.model_registry import ModelSpec
from omni_tts_core.provider_registry import provider_descriptor
from omni_tts_core.provider_options import ProviderSettingSpec
from omni_tts_core.runtime_devices import RUNTIME_TARGET_CHOICES
from omni_tts_core.ui_presenters.tooltips import tooltip
from omni_tts_core.worker_installation import worker_label_for_spec
from omni_tts_shared.languages import language_label
from omni_tts_shared.schemas import ModelCapabilities, RuntimeStatus

# Neutral values sent when a model does not support the control.
NEUTRAL_SPEED = 1.0
NEUTRAL_PITCH = 0.0
NEUTRAL_EMOTION = "natural"

# Kept as names so existing imports stay valid; the text itself lives in
# ``tooltips`` together with every other explanation shown to the user.
CHUNK_TOOLTIP = tooltip("max_chunk")
SENTENCE_PAUSE_TOOLTIP = tooltip("sentence_pause")
PARAGRAPH_PAUSE_TOOLTIP = tooltip("paragraph_pause")

# Provider tuning groups a GUI can draw. A GUI shows a group only when the id is
# in ``policy.tuning_groups`` — that is what keeps the Chatterbox knobs off a
# Piper model instead of merely greying them out.
TUNING_VIENEU = "vieneu"
TUNING_PIPER = "piper"
TUNING_F5 = "f5"
TUNING_CHATTERBOX = "chatterbox"
TUNING_HIGGS_REMOTE = "higgs_remote"
TUNING_PROVIDER_OPTIONS = "provider_options"

_CUDA_TARGETS = {"cuda"}


@dataclass(frozen=True)
class ControlState:
    """Whether one control applies, why not when it doesn't, and how to use it."""

    supported: bool
    reason: str = ""
    hint: str = ""

    def __bool__(self) -> bool:
        return self.supported

    @property
    def tooltip(self) -> str:
        """What to show on hover: the blocking reason, else the how-to hint."""
        return self.reason or self.hint


@dataclass(frozen=True)
class GenerationControlPolicy:
    model_id: str
    provider_id: str
    provider_label: str
    languages: tuple[tuple[str, str], ...]  # (label, code)
    device_targets: tuple[tuple[str, str], ...]  # (label, value)
    device_note: str
    speed: ControlState
    pitch: ControlState
    emotion: ControlState
    emotions: tuple[str, ...]
    codec: ControlState
    sampling: ControlState
    piper: ControlState
    f5: ControlState
    chatterbox: ControlState
    higgs_remote: ControlState
    higgs_script: ControlState
    punctuation_pauses: ControlState
    gpu_safety: ControlState
    omnivoice: ControlState = ControlState(False)
    gpu_scope_note: str = ""
    piper_recommendation: str = ""
    provider_settings: tuple[ProviderSettingSpec, ...] = ()
    speed_minimum: float = 0.5
    speed_maximum: float = 1.8

    @property
    def tuning_groups(self) -> tuple[str, ...]:
        """Ids of the provider tuning groups this model actually exposes."""
        groups: list[str] = []
        if any((self.codec, self.sampling, self.emotion)):
            groups.append(TUNING_VIENEU)
        if self.piper:
            groups.append(TUNING_PIPER)
        if self.f5:
            groups.append(TUNING_F5)
        if self.chatterbox:
            groups.append(TUNING_CHATTERBOX)
        if self.higgs_remote:
            groups.append(TUNING_HIGGS_REMOTE)
        if self.provider_settings:
            groups.append(TUNING_PROVIDER_OPTIONS)
        # OmniVoice's one knob (num_step) lives inline in the basic form, not in
        # a provider tuning box, so it is intentionally not a tuning group here.
        return tuple(groups)

    @property
    def has_tuning(self) -> bool:
        """True when the model exposes any provider-specific tuning control."""
        return bool(self.tuning_groups)

    @property
    def tuning_title(self) -> str:
        return f"Tinh chỉnh riêng · {self.provider_label}"

    def tuning_absent_note(self) -> str:
        return (
            f"{self.provider_label} không có thông số tinh chỉnh chất giọng riêng; "
            "các thiết lập dùng chung hoặc ngắt nghỉ được hiển thị ở mục tương ứng."
        )

    def default_language(self, current: str | None) -> str:
        codes = [code for _label, code in self.languages]
        if current in codes:
            return str(current)
        return codes[0] if codes else "vi"

    def default_device(self, current: str | None) -> str:
        values = [value for _label, value in self.device_targets]
        if current in values:
            return str(current)
        return values[0] if values else "auto"


def build_policy(
    *,
    spec: ModelSpec,
    capabilities: ModelCapabilities,
    runtime_status: RuntimeStatus,
    supports_codec: bool,
    supports_sampling: bool,
    supports_f5: bool,
    supports_chatterbox: bool,
) -> GenerationControlPolicy:
    descriptor = provider_descriptor(spec.provider)
    provider_label = (
        worker_label_for_spec(spec)
        if spec.provider == "vieneu"
        else (descriptor.label if descriptor else (spec.provider or "Khác"))
    )
    is_remote = bool(descriptor and descriptor.storage_mode == "remote")
    gpu_available = bool(runtime_status.gpu_available)

    languages = tuple(
        (_language_choice_label(code), code) for code in capabilities.supported_languages
    ) or (("Tiếng Việt", "vi"),)

    if is_remote:
        device_targets = (("GPU từ xa (server quyết định)", "auto"),)
        device_note = "Máy hiện tại chỉ gửi request; GPU và runtime nằm ở endpoint."
    elif bool((getattr(spec, "runtime", {}) or {}).get("cpu_only")):
        device_targets = (
            ("Tự động · CPU ONNX (khuyến nghị)", "auto"),
            ("CPU ONNX", "cpu"),
        )
        device_note = f"{provider_label} chạy ONNX trên CPU; không dùng GPU CUDA."
    elif spec.provider == "vieneu" and str((getattr(spec, "runtime", {}) or {}).get("vieneu_mode") or "").lower() == "v3turbo":
        precision = str(
            (getattr(spec, "runtime", {}) or {}).get("precision") or "fp32"
        ).strip().upper()
        device_targets = (
            (f"Tự động · CPU ONNX {precision} (khuyến nghị)", "auto"),
            ("CPU ONNX · chất lượng cao, phù hợp câu ngắn", "cpu"),
            *((("GPU CUDA · PyTorch, tối ưu batch dài", "cuda"),) if gpu_available else ()),
        )
        device_note = (
            "VieNeu v3 chạy CPU ONNX khi chọn Tự động. GPU PyTorch chỉ có lợi rõ với "
            "văn bản dài hoặc nhiều câu chạy batch."
            if gpu_available
            else "VieNeu v3 đang dùng CPU ONNX; muốn chạy batch GPU hãy cài CUDA cho worker VieNeu v3."
        )
    else:
        device_targets = tuple(
            (label, value)
            for label, value in RUNTIME_TARGET_CHOICES
            if gpu_available or value not in _CUDA_TARGETS
        )
        device_note = (
            ""
            if gpu_available
            else f"{provider_label} chưa có CUDA khả dụng nên chỉ chạy CPU."
        )

    return GenerationControlPolicy(
        model_id=spec.model_id,
        provider_id=spec.provider,
        provider_label=provider_label,
        languages=languages,
        device_targets=device_targets or (("Auto (khuyến nghị)", "auto"),),
        device_note=device_note,
        speed=_state(
            capabilities.supports_speed,
            f"{spec.display_name} không đổi được tốc độ đọc; luôn dùng {NEUTRAL_SPEED:.2f}.",
            tooltip("speed"),
        ),
        pitch=_state(
            capabilities.supports_pitch_shift,
            f"{spec.display_name} không hỗ trợ đổi cao độ (pitch).",
            tooltip("pitch"),
        ),
        emotion=_state(
            capabilities.supports_emotion and bool(capabilities.emotions),
            f"{spec.display_name} không có tuỳ chọn cảm xúc.",
            tooltip("vieneu_emotion"),
        ),
        emotions=tuple(capabilities.emotions or ()),
        codec=_state(supports_codec, "Model này không chọn được codec.", tooltip("vieneu_codec")),
        sampling=_state(
            supports_sampling,
            "Model này không chỉnh được temperature/top-k.",
        ),
        piper=_state(
            bool(descriptor and "piper" in descriptor.controls),
            "Chỉ áp dụng cho model Piper ONNX.",
            tooltip("piper_noise_scale"),
        ),
        f5=_state(supports_f5, "Chỉ áp dụng cho model F5-TTS."),
        chatterbox=_state(supports_chatterbox, "Chỉ áp dụng cho model Chatterbox."),
        higgs_remote=_state(
            bool(descriptor and "higgs_remote" in descriptor.controls),
            "Chỉ áp dụng cho endpoint Higgs TTS 3 qua SGLang-Omni.",
        ),
        higgs_script=_state(
            bool(descriptor and "higgs_script" in descriptor.controls),
            "Chỉ model Higgs mới đọc các token <|category:value|>.",
            "Chèn Emotion, Style, Prosody, Pause và SFX trực tiếp trong nội dung.",
        ),
        punctuation_pauses=_state(
            bool(descriptor and "punctuation_pauses" in descriptor.controls),
            f"{provider_label} chưa có cơ chế ngắt nghỉ theo từng loại dấu câu.",
            tooltip("punctuation_section"),
        ),
        omnivoice=_state(
            spec.provider == "omnivoice",
            "Chỉ áp dụng cho model OmniVoice.",
            "Số bước diffusion: cao = chất lượng tốt hơn/chậm hơn, thấp = nhanh hơn.",
        ),
        gpu_safety=_state(
            gpu_available and not is_remote,
            "Model đang chạy CPU nên bảo vệ GPU không can thiệp vào lần chạy này.",
            tooltip("gpu_enabled"),
        ),
        gpu_scope_note=(
            "Bảo vệ GPU cục bộ không can thiệp vào GPU từ xa; server phải tự giới hạn tải/nhiệt."
            if is_remote
            else _gpu_scope_note(spec.provider, gpu_available)
        ),
        piper_recommendation=_piper_recommendation(spec),
        provider_settings=descriptor.settings if descriptor else (),
        speed_minimum=descriptor.speed_minimum if descriptor else 0.5,
        speed_maximum=descriptor.speed_maximum if descriptor else 1.8,
    )


def _state(supported: bool, reason: str, hint: str = "") -> ControlState:
    return ControlState(bool(supported), "" if supported else reason, hint)


def _piper_recommendation(spec: ModelSpec) -> str:
    if spec.provider != "piper":
        return ""
    profile = str(
        (getattr(spec, "runtime", {}) or {}).get("piper_recommended_profile") or ""
    ).lower()
    if profile == "vbee":
        return (
            "Package Vbee Export: có thể thử preset Vbee tham chiếu (Noise 0.900, "
            "Noise W 0.650). Đây chỉ là khuyến nghị; phần mềm không tự đổi thông số."
        )
    return (
        "Khuyến nghị bắt đầu với preset Piper chuẩn (Noise 0.667, Noise W 0.800), "
        "sau đó A/B trên cùng văn bản nếu cần."
    )


def _gpu_scope_note(provider_id: str, gpu_available: bool) -> str:
    """Who enforces GPU protection for this model, in one line."""
    if not gpu_available:
        return "Model đang chạy CPU nên bảo vệ GPU không can thiệp vào lần chạy này."
    if provider_id == "chatterbox":
        return (
            "Chatterbox tự bảo vệ ngay trong worker (chờ trước khi chạy và tạm nghỉ "
            "giữa chừng); các ngưỡng dưới đây được gửi thẳng cho worker."
        )
    return (
        "Ngưỡng dùng chung cho mọi model chạy CUDA: app chờ GPU an toàn trước khi bắt "
        "đầu mỗi lần tạo và mỗi file trong hàng đợi."
    )


def _language_choice_label(code: str) -> str:
    label = language_label(code)
    return label if code == "auto" else f"{code} — {label}"
