from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Literal

from omni_tts_core.engines.base import BaseTtsEngine
from omni_tts_core.engines.chatterbox_engine import ChatterboxSubprocessEngine
from omni_tts_core.engines.f5tts_engine import F5TtsSubprocessEngine
from omni_tts_core.engines.higgs_remote_engine import HiggsRemoteEngine
from omni_tts_core.engines.omnivoice_engine import OmniVoiceEngine
from omni_tts_core.engines.piper_engine import PiperSubprocessEngine
from omni_tts_core.engines.qwen_engine import QwenSubprocessEngine
from omni_tts_core.engines.valtec_engine import ValtecSubprocessEngine
from omni_tts_core.engines.vieneu_engine import VieneuSubprocessEngine
from omni_tts_core.model_registry import ModelSpec


StorageMode = Literal["folder", "hf_cache", "remote"]
EngineFactory = Callable[[ModelSpec, object | None], BaseTtsEngine]


@dataclass(frozen=True)
class ProviderDescriptor:
    provider_id: str
    label: str
    storage_mode: StorageMode
    worker_name: str | None
    engine_factory: EngineFactory
    controls: frozenset[str] = frozenset()


def _omnivoice(spec: ModelSpec, cache: object | None) -> BaseTtsEngine:
    return OmniVoiceEngine(spec, cache)


def _vieneu(spec: ModelSpec, cache: object | None) -> BaseTtsEngine:
    return VieneuSubprocessEngine(spec, cache)


def _qwen(spec: ModelSpec, cache: object | None) -> BaseTtsEngine:
    return QwenSubprocessEngine(spec, cache)


def _simple(factory):
    return lambda spec, _cache: factory(spec)


PROVIDERS: dict[str, ProviderDescriptor] = {
    "omnivoice": ProviderDescriptor(
        "omnivoice", "OmniVoice", "folder", None, _omnivoice,
        frozenset({"speed"}),
    ),
    "vieneu": ProviderDescriptor(
        "vieneu", "VieNeu", "hf_cache", "vieneu_worker", _vieneu,
        frozenset({"codec", "sampling", "emotion"}),
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
        frozenset({"speed", "punctuation_pauses"}),
    ),
    "higgs_remote": ProviderDescriptor(
        "higgs_remote",
        "Higgs Remote GPU",
        "remote",
        None,
        _simple(HiggsRemoteEngine),
        frozenset({"higgs_remote", "higgs_script"}),
    ),
}


def provider_descriptor(provider_id: str) -> ProviderDescriptor | None:
    return PROVIDERS.get(provider_id)
