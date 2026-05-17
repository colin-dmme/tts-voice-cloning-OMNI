from __future__ import annotations

import pickle
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np

from omni_tts_core.engines.base import BaseTtsEngine, TtsEngineRequest, TtsEngineResult
from omni_tts_core.model_registry import ModelSpec
from omni_tts_core.paths import project_path
from omni_tts_core.progress import check_cancel
from omni_tts_shared.errors import EngineDependencyError, GenerationError

if TYPE_CHECKING:
    from omni_tts_core.engine_profile_cache import EngineProfileCache


class OmniVoiceEngine(BaseTtsEngine):
    sample_rate = 24000

    def __init__(self, spec: ModelSpec, cache: "EngineProfileCache | None" = None) -> None:
        self.spec = spec
        self._cache = cache
        self._models: dict[str, Any] = {}

    def generate(self, request: TtsEngineRequest) -> TtsEngineResult:
        check_cancel(request.cancel_event)
        model = self._load_model(request.runtime_target)
        kwargs: dict = {
            "text": request.text,
            "speed": request.speed,
        }
        language_name = _language_name(request.language)
        if language_name:
            kwargs["language"] = language_name

        if request.reference_audio_path:
            if request.cached_prompt_path is not None:
                voice_prompt = _load_or_build_voice_prompt(
                    model,
                    request.cached_prompt_path,
                    request.reference_audio_path,
                    request.reference_text or "",
                )
                if voice_prompt is not None:
                    kwargs["voice_clone_prompt"] = voice_prompt
                    if self._cache is not None:
                        self._cache.write_meta(
                            request.cached_prompt_path,
                            request.reference_audio_path,
                            request.reference_text or "",
                        )
                else:
                    kwargs["ref_audio"] = str(request.reference_audio_path)
                    if request.reference_text:
                        kwargs["ref_text"] = request.reference_text
            else:
                kwargs["ref_audio"] = str(request.reference_audio_path)
                if request.reference_text:
                    kwargs["ref_text"] = request.reference_text

        try:
            audio = model.generate(**kwargs)
        except Exception as exc:
            raise GenerationError("OmniVoice không sinh được audio cho đoạn hiện tại.") from exc
        check_cancel(request.cancel_event)
        return TtsEngineResult(audio=_first_audio_array(audio), sample_rate=self.sample_rate)

    def _load_model(self, runtime_target: str = "auto"):
        try:
            import torch
            from omnivoice import OmniVoice
            import omnivoice.models.omnivoice as omnivoice_module
        except Exception as exc:
            raise EngineDependencyError(
                "Thiếu thư viện OmniVoice/torch. Chạy install_tts_deps.bat trước."
            ) from exc
        device, dtype = _best_device(torch, runtime_target)
        cache_key = f"{device}:{getattr(dtype, '__name__', str(dtype))}"
        if cache_key in self._models:
            return self._models[cache_key]
        model_path = _model_path_or_repo(
            self.spec.local_path,
            self.spec.hf_repo,
            self.spec.runtime,
        )
        _patch_tokenizer_resolver(omnivoice_module)
        self._models[cache_key] = OmniVoice.from_pretrained(model_path, device_map=device, dtype=dtype)
        return self._models[cache_key]


def _load_or_build_voice_prompt(
    model: Any,
    asset_dir: Path,
    audio_path: Path,
    transcript: str,
) -> Any | None:
    """
    Try to load a cached voice_clone_prompt from asset_dir/voice_clone_prompt.pkl.
    If not found or unloadable, create via model.create_voice_clone_prompt() and save.
    Returns None if the model API is unavailable.
    """
    pkl_path = asset_dir / "voice_clone_prompt.pkl"
    if pkl_path.exists():
        try:
            with pkl_path.open("rb") as f:
                return pickle.load(f)
        except Exception:
            pkl_path.unlink(missing_ok=True)

    if not hasattr(model, "create_voice_clone_prompt"):
        return None

    try:
        prompt = model.create_voice_clone_prompt(str(audio_path), transcript)
    except Exception:
        return None

    try:
        asset_dir.mkdir(parents=True, exist_ok=True)
        with pkl_path.open("wb") as f:
            pickle.dump(prompt, f)
    except Exception:
        pass

    return prompt


def _best_device(torch_module, runtime_target: str = "auto"):
    runtime_target = (runtime_target or "auto").strip().lower()
    if runtime_target == "cpu":
        return "cpu", torch_module.float32
    if runtime_target == "cuda" and not torch_module.cuda.is_available():
        raise EngineDependencyError(
            "OmniVoice chưa dùng được CUDA trong môi trường chính. "
            "Hãy cài PyTorch CUDA hoặc chọn Thiết bị xử lý = CPU/Auto."
        )
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


def _model_path_or_repo(local_path: Path, hf_repo: str, runtime: dict) -> str:
    subfolder = _runtime_text(runtime, "omnivoice_subfolder")
    if local_path.exists() and any(local_path.iterdir()):
        if subfolder:
            model_path = local_path / subfolder
            if model_path.exists() and any(model_path.iterdir()):
                return str(model_path)
            raise GenerationError(
                "OmniVoice checkpoint chưa có đủ file trong thư mục con. "
                f"Hãy tải model trước rồi kiểm tra {model_path}."
            )
        return str(local_path)
    if subfolder:
        raise GenerationError(
            "OmniVoice checkpoint dạng thư mục con cần được tải trong Quản lý model "
            "trước khi tạo audio."
        )
    return hf_repo


def _runtime_text(runtime: dict, key: str) -> str:
    value = runtime.get(key)
    return str(value).strip() if value else ""


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
