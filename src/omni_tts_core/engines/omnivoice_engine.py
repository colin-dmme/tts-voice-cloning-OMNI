from __future__ import annotations

from pathlib import Path

import numpy as np

from omni_tts_core.engines.base import BaseTtsEngine, TtsEngineRequest, TtsEngineResult
from omni_tts_core.model_registry import ModelSpec
from omni_tts_core.paths import project_path
from omni_tts_core.progress import check_cancel
from omni_tts_shared.errors import EngineDependencyError, GenerationError


class OmniVoiceEngine(BaseTtsEngine):
    sample_rate = 24000

    def __init__(self, spec: ModelSpec) -> None:
        self.spec = spec
        self._model = None

    def generate(self, request: TtsEngineRequest) -> TtsEngineResult:
        check_cancel(request.cancel_event)
        model = self._load_model()
        kwargs = {
            "text": request.text,
            "speed": request.speed,
        }
        language_name = _language_name(request.language)
        if language_name:
            kwargs["language"] = language_name
        if request.reference_audio_path:
            kwargs["ref_audio"] = str(request.reference_audio_path)
        if request.reference_text:
            kwargs["ref_text"] = request.reference_text
        try:
            audio = model.generate(**kwargs)
        except Exception as exc:
            raise GenerationError("OmniVoice không sinh được audio cho đoạn hiện tại.") from exc
        check_cancel(request.cancel_event)
        return TtsEngineResult(audio=_first_audio_array(audio), sample_rate=self.sample_rate)

    def _load_model(self):
        if self._model is not None:
            return self._model
        try:
            import torch
            from omnivoice import OmniVoice
            import omnivoice.models.omnivoice as omnivoice_module
        except Exception as exc:
            raise EngineDependencyError(
                "Thiếu thư viện OmniVoice/torch. Chạy install_tts_deps.bat trước."
            ) from exc
        device, dtype = _best_device(torch)
        model_path = _model_path_or_repo(self.spec.local_path, self.spec.hf_repo)
        _patch_tokenizer_resolver(omnivoice_module)
        self._model = OmniVoice.from_pretrained(model_path, device_map=device, dtype=dtype)
        return self._model


def _best_device(torch_module):
    if torch_module.cuda.is_available():
        major, _minor = torch_module.cuda.get_device_capability(0)
        if major >= 7:
            return "cuda:0", torch_module.float16
        return "cuda:0", torch_module.float32
    return "cpu", torch_module.float32


def _patch_tokenizer_resolver(omnivoice_module) -> None:
    tokenizer_path = project_path("models/tokenizer/higgs-audio-v2-tokenizer")
    if not tokenizer_path.exists() or not any(tokenizer_path.iterdir()):
        return
    original_resolver = omnivoice_module._resolve_model_path

    def resolve_local_first(name_or_path: str) -> str:
        if name_or_path == "eustlb/higgs-audio-v2-tokenizer":
            return str(tokenizer_path)
        return original_resolver(name_or_path)

    omnivoice_module._resolve_model_path = resolve_local_first


def _model_path_or_repo(local_path: Path, hf_repo: str) -> str:
    if local_path.exists() and any(local_path.iterdir()):
        return str(local_path)
    return hf_repo


def _language_name(language: str) -> str | None:
    if language == "vi":
        return "vietnamese"
    if language == "en":
        return "english"
    return None


def _first_audio_array(audio) -> np.ndarray:
    if isinstance(audio, list) and audio:
        return np.asarray(audio[0])
    return np.asarray(audio)
