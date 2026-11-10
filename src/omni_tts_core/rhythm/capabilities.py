"""How each provider/model can realise every pause layer.

Profiles are data: the resolver never branches on a provider id. A provider
without a profile gets the safe default (the app stretches existing silences).
Values come from a source survey on 2026-11-10 and are corrected by the
measurements in plans/2026-11-10-nhip-doc-theo-nang-luc-model (phase 0).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, Literal

from omni_tts_core.rhythm.layers import LAYERS, TEXT_LAYERS

Mechanism = Literal[
    "native_token", "library_param", "library_fixed", "app_split", "app_stretch", "none",
]


@dataclass(frozen=True)
class LayerCapability:
    # Preferred mechanisms for this model, best first. The resolver takes the
    # first one whose requirement holds; "app_stretch" always works as fallback.
    mechanisms: tuple[Mechanism, ...] = ("app_stretch",)
    # library_param: the library argument and whether it means the total silence.
    param: str | None = None
    # library_fixed: the silence the library inserts itself (not adjustable).
    fixed_ms: int | None = None
    # Why the layer can only be partly honoured, written for the user.
    limit: str | None = None
    # A cap the model applies; values above it are flagged as limited.
    limit_max_ms: int | None = None
    # native_token needs text authored with pause tokens.
    requires_tokens: bool = False
    # Remote workers may not accept library parameters.
    remote_ok: bool = True
    # Extra explanation shown with the layer.
    note: str = ""


STRETCH = LayerCapability()


@dataclass(frozen=True)
class RhythmSwitch:
    """A model-specific option shown in Nhịp đọc only while that model is chosen."""

    key: str
    label: str
    choices: tuple[tuple[str, str], ...]
    default: str
    help: str
    # Value -> layer capabilities replacing the profile's for that layer.
    effects: Mapping[str, Mapping[str, LayerCapability]] = field(default_factory=dict)
    # Scopes in which the switch acts ("full" only for switches that would
    # fight the old punctuation settings).
    scopes: tuple[str, ...] = ("pacing_only", "full")
    # Engine argument this switch drives, for the executor and the report.
    engine_option: str | None = None


@dataclass(frozen=True)
class ModelOverride:
    applies: Callable[[str, Mapping[str, Any]], bool]
    layers: Mapping[str, LayerCapability]
    label: str = ""


@dataclass(frozen=True)
class PauseProfile:
    layers: Mapping[str, LayerCapability] = field(default_factory=dict)
    model_overrides: tuple[ModelOverride, ...] = ()
    switches: tuple[RhythmSwitch, ...] = ()
    # Provider settings ("Tinh chỉnh riêng") that duplicate a layer and are
    # locked while Nhịp đọc owns every layer.
    locked_settings: tuple[str, ...] = ()

    def capability(self, layer: str, model_id: str = "", runtime: Mapping[str, Any] | None = None) -> LayerCapability:
        found = self.layers.get(layer, STRETCH)
        for override in self.model_overrides:
            if layer in override.layers and override.applies(model_id, runtime or {}):
                found = override.layers[layer]
        return found


def _all_text(capability: LayerCapability, *, but: Mapping[str, LayerCapability] | None = None) -> dict[str, LayerCapability]:
    layers = dict.fromkeys(TEXT_LAYERS, capability)
    layers.update(but or {})
    return layers


# Short sentences are a beat on top of the sentence pause: only the app knows
# where they are, so this layer is always stretched by the app.
_SHORT = {"short_sentence": STRETCH}

# Remote workers do not trim fragment edges yet, so they fall back to stretching.
_SPLIT = LayerCapability(("app_split", "app_stretch"), remote_ok=False)
# The punctuation splitter has one group for . ! ? — a question gets the
# sentence pause from the split, then the app tops it up to its own target.
_QUESTION_TOPUP = {"question_end": LayerCapability(
    note="Cắt câu như dấu chấm rồi app giãn thêm cho đủ mức của câu hỏi.")}

_KOKORO_CLAUSE = LayerCapability(
    ("library_param", "app_split", "app_stretch"), param="clause_pause", remote_ok=False,
    note="Kokoro dùng một mức chung cho , ; : (điểm giữa Min–Max), không dao động.",
)
_KOKORO_SENTENCE = LayerCapability(
    ("library_param", "app_split", "app_stretch"), param="sentence_pause", remote_ok=False,
    note="Kokoro dùng một mức chung cho . ! ? … (điểm giữa Min–Max), không dao động.",
)
# omnivoice 0.2.1 _post_process_audio: remove_silence(mid_sil=500), which keeps
# 500 ms on each side of a cut, so pauses inside a chunk end up at most ~1 s.
_OMNIVOICE_CLAMP = LayerCapability(
    limit="OmniVoice rút khoảng lặng dài hơn 0,5s trong câu về tối đa khoảng 1s.",
    limit_max_ms=1000,
)


def _vieneu_v3(model_id: str, runtime: Mapping[str, Any]) -> bool:
    return runtime.get("vieneu_mode") == "v3turbo" or "v3" in model_id


PROFILES: dict[str, PauseProfile] = {
    "piper": PauseProfile(_all_text(_SPLIT, but={**_SHORT, **_QUESTION_TOPUP})),
    "supertonic": PauseProfile(_all_text(_SPLIT, but={**_SHORT, **_QUESTION_TOPUP})),
    "kokoro_onnx": PauseProfile(
        _all_text(_SPLIT, but={**_SHORT, **_QUESTION_TOPUP}),
        switches=(
            RhythmSwitch(
                "kokoro_pause_mode",
                "Cách ngắt nghỉ của Kokoro",
                (("library", "Tham số model"), ("app_split", "App cắt câu")),
                "library",
                "Tham số model: đọc liền mạch, mỗi nhóm dấu một mức nghỉ. "
                "App cắt câu: mỗi lần nghỉ dao động trong Min–Max.",
                effects={
                    "library": {
                        "comma": _KOKORO_CLAUSE, "clause": _KOKORO_CLAUSE,
                        "ellipsis": _KOKORO_SENTENCE, "sentence_end": _KOKORO_SENTENCE,
                        "question_end": _KOKORO_SENTENCE,
                    },
                },
                scopes=("full",),
                engine_option="kokoro_pause_mode",
            ),
        ),
    ),
    "zerotts": PauseProfile(
        _all_text(
            STRETCH,
            but={
                "clause": LayerCapability(limit="Thư viện ZeroTTS đổi ; thành dấu phẩy trước khi đọc."),
                "sentence_end": LayerCapability(("library_fixed", "app_stretch"), fixed_ms=80),
                "question_end": LayerCapability(("library_fixed", "app_stretch"), fixed_ms=80),
            },
        ),
        locked_settings=("segment_gap_seconds",),
    ),
    "vieneu": PauseProfile(
        model_overrides=(
            # Measured 2026-11-10: the fixed 0.5 s gap sits only at sentence
            # ends (465/405 ms median); commas stay natural (~155 ms, 17 %
            # read without a pause), so in-sentence layers are app-stretched.
            ModelOverride(
                _vieneu_v3,
                {
                    "sentence_end": LayerCapability(("library_fixed", "app_stretch"), fixed_ms=500),
                    "question_end": LayerCapability(("library_fixed", "app_stretch"), fixed_ms=500),
                },
                label="VieNeu v3 Turbo",
            ),
        ),
    ),
    "omnivoice": PauseProfile(
        switches=(
            RhythmSwitch(
                "omnivoice_keep_long_silence",
                "Giữ khoảng lặng dài",
                (("on", "Bật"), ("off", "Tắt")),
                "on",
                "Bật: tắt bước rút lặng của OmniVoice để giữ nhịp; app tự cắt lặng bất thường "
                "dài hơn 2s. Tắt: OmniVoice rút lặng giữa câu về khoảng 0,6s.",
                effects={"off": _all_text(_OMNIVOICE_CLAMP, but=_SHORT)},
                engine_option="postprocess_output",
            ),
        ),
    ),
    "chatterbox": PauseProfile(
        _all_text(
            STRETCH,
            but={
                "clause": LayerCapability(limit="Thư viện Chatterbox đổi : thành dấu phẩy."),
                "ellipsis": LayerCapability(limit="Thư viện Chatterbox đổi … thành dấu phẩy."),
            },
        ),
    ),
    "higgs_remote": PauseProfile(
        {
            "sentence_end": LayerCapability(
                ("native_token", "app_stretch"), requires_tokens=True,
                note="Token <|prosody:pause|> trong kịch bản đã soạn.",
            ),
            "paragraph": LayerCapability(
                ("native_token", "app_stretch"), requires_tokens=True,
                note="Token <|prosody:long_pause|> trong kịch bản đã soạn.",
            ),
        },
    ),
}
DEFAULT_PROFILE = PauseProfile()

# Every layer id a profile may mention must exist.
_KNOWN = {spec.layer for spec in LAYERS}
for _profile in PROFILES.values():
    _names = set(_profile.layers)
    for _override in _profile.model_overrides:
        _names |= set(_override.layers)
    for _switch in _profile.switches:
        for _effect in _switch.effects.values():
            _names |= set(_effect)
    if not _names <= _KNOWN:
        raise ValueError(f"Unknown pause layers in profile: {_names - _KNOWN}")


def pause_profile_for(provider_id: str) -> PauseProfile:
    return PROFILES.get(provider_id, DEFAULT_PROFILE)
