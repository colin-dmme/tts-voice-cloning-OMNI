from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Literal

from omni_tts_core.engines.base import BaseTtsEngine
from omni_tts_core.engines.chatterbox_engine import ChatterboxSubprocessEngine
from omni_tts_core.engines.f5tts_engine import F5TtsSubprocessEngine
from omni_tts_core.engines.higgs_remote_engine import HiggsRemoteEngine
from omni_tts_core.engines.preset_onnx_engine import PresetOnnxSubprocessEngine
from omni_tts_core.engines.omnivoice_engine import OmniVoiceEngine
from omni_tts_core.engines.piper_engine import PiperSubprocessEngine
from omni_tts_core.engines.qwen_engine import QwenSubprocessEngine
from omni_tts_core.engines.valtec_engine import ValtecSubprocessEngine
from omni_tts_core.engines.vieneu_engine import VieneuSubprocessEngine
from omni_tts_core.model_registry import ModelSpec
from omni_tts_core.provider_options import ProviderSettingSpec


StorageMode = Literal["folder", "hf_cache", "remote"]
AutomaticChunkJoin = Literal["native", "punctuation", "silence"]
EngineFactory = Callable[[ModelSpec, object | None], BaseTtsEngine]


@dataclass(frozen=True)
class ProviderDescriptor:
    provider_id: str
    label: str
    storage_mode: StorageMode
    worker_name: str | None
    engine_factory: EngineFactory
    controls: frozenset[str] = frozenset()
    max_parallel_jobs: int = 1
    # Optional provider-neutral authoring contract.  A future TTS provider only
    # declares its dialect/features and supplies an adapter; GUI code never
    # branches on provider_id.
    authoring_dialect: str | None = None
    authoring_features: frozenset[str] = frozenset()
    # Core owns the generic join modes, while each provider declares what
    # "Auto" means.  Frontends only display the resulting metadata.
    automatic_chunk_join: AutomaticChunkJoin = "silence"
    settings: tuple[ProviderSettingSpec, ...] = ()
    speed_minimum: float = 0.5
    speed_maximum: float = 1.8


def _omnivoice(spec: ModelSpec, cache: object | None) -> BaseTtsEngine:
    return OmniVoiceEngine(spec, cache)


def _vieneu(spec: ModelSpec, cache: object | None) -> BaseTtsEngine:
    return VieneuSubprocessEngine(spec, cache)


def _qwen(spec: ModelSpec, cache: object | None) -> BaseTtsEngine:
    return QwenSubprocessEngine(spec, cache)


def _simple(factory):
    return lambda spec, _cache: factory(spec)


def _preset_onnx(spec: ModelSpec, _cache: object | None) -> BaseTtsEngine:
    return PresetOnnxSubprocessEngine(spec)


PROVIDERS: dict[str, ProviderDescriptor] = {
    "omnivoice": ProviderDescriptor(
        "omnivoice", "OmniVoice", "folder", None, _omnivoice,
        frozenset({"speed"}),
    ),
    "vieneu": ProviderDescriptor(
        "vieneu", "VieNeu", "hf_cache", "vieneu_worker", _vieneu,
        frozenset({"codec", "sampling", "emotion"}),
        automatic_chunk_join="native",
    ),
    "qwen": ProviderDescriptor(
        "qwen", "Qwen", "folder", "qwen_worker", _qwen,
    ),
    "valtec": ProviderDescriptor(
        "valtec", "Valtec", "hf_cache", "valtec_worker", _simple(ValtecSubprocessEngine),
    ),
    "f5tts": ProviderDescriptor(
        "f5tts", "F5-TTS", "folder", "f5_worker", _simple(F5TtsSubprocessEngine),
        frozenset({"f5"}),
    ),
    "chatterbox": ProviderDescriptor(
        "chatterbox", "Chatterbox", "folder", "chatterbox_worker",
        _simple(ChatterboxSubprocessEngine), frozenset({"chatterbox"}),
    ),
    "piper": ProviderDescriptor(
        "piper", "Piper ONNX", "folder", "piper_worker", _simple(PiperSubprocessEngine),
        frozenset({"speed", "punctuation_pauses", "piper"}), 2,
        automatic_chunk_join="punctuation",
    ),
    "kokoro_onnx": ProviderDescriptor(
        "kokoro_onnx",
        "Kokoro ONNX",
        "folder",
        "kokoro_worker",
        _preset_onnx,
        frozenset({"speed", "punctuation_pauses", "provider_options"}),
        1,
        automatic_chunk_join="punctuation",
        settings=(
            ProviderSettingSpec(
                "trim_silence",
                "Cắt im lặng đầu/cuối",
                "boolean",
                True,
                "Bỏ khoảng im lặng dư do model tạo ở đầu và cuối từng đoạn nhỏ.",
            ),
            ProviderSettingSpec(
                "continuous_prosody",
                "Ngữ điệu liên tục",
                "boolean",
                False,
                "Giữ mạch ngữ điệu tốt hơn giữa các câu; chậm hơn và chỉ dùng với model timestamped.",
            ),
        ),
    ),
    "supertonic": ProviderDescriptor(
        "supertonic",
        "Supertonic 3",
        "folder",
        "supertonic_worker",
        _preset_onnx,
        frozenset({"speed", "punctuation_pauses", "provider_options"}),
        1,
        automatic_chunk_join="punctuation",
        settings=(
            ProviderSettingSpec(
                "total_steps",
                "Mức chất lượng",
                "integer",
                8,
                "Số bước khử nhiễu: cao hơn thường rõ hơn nhưng xử lý chậm hơn. Khuyến nghị 8.",
                minimum=5,
                maximum=12,
                step=1,
            ),
        ),
        speed_minimum=0.7,
        speed_maximum=1.8,
    ),
    "higgs_remote": ProviderDescriptor(
        "higgs_remote",
        "Higgs Remote GPU",
        "remote",
        None,
        _simple(HiggsRemoteEngine),
        frozenset({"higgs_remote", "higgs_script"}),
        2,
        "higgs_v1",
        frozenset(
            {
                "emotion",
                "style",
                "pace",
                "pitch",
                "expressiveness",
                "pause",
                "vocal_sfx",
            }
        ),
    ),
}


def provider_descriptor(provider_id: str) -> ProviderDescriptor | None:
    return PROVIDERS.get(provider_id)
