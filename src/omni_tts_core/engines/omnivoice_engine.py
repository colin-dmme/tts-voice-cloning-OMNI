from __future__ import annotations

import pickle
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np

from omni_tts_core.engines.base import BaseTtsEngine, TtsEngineRequest, TtsEngineResult
from omni_tts_core.model_registry import ModelSpec
from omni_tts_core.storage_paths import resolve_model_path
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

        generation_config = _build_generation_config(request.num_step)
        if generation_config is not None:
            kwargs["generation_config"] = generation_config

        instruct = (request.instruct or "").strip()
        if instruct:
            # Voice Design: synthesise from the description; no reference/preset.
            kwargs["instruct"] = instruct
        elif request.reference_audio_path:
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

    def close(self) -> None:
        """Drop the in-process model(s) and release their VRAM.

        OmniVoice loads the model into the main app process (unlike subprocess
        engines), so nothing frees it until we clear the cache and ask CUDA to
        release the now-unreferenced allocations.
        """
        if not self._models:
            return
        self._models.clear()
        try:
            import gc

            import torch

            gc.collect()
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                torch.cuda.ipc_collect()
        except Exception:
            pass

    def _load_model(self, runtime_target: str = "auto"):
        try:
            import torch
            from omnivoice import OmniVoice
            import omnivoice.models.omnivoice as omnivoice_module
        except Exception as exc:
            raise EngineDependencyError(
                f"Không nạp được OmniVoice/torch bằng Python {sys.executable}: "
                f"{type(exc).__name__}: {exc}. "
                "Mở tab Quản lý model, chọn OmniVoice rồi kiểm tra mục Python/Thư viện TTS chính."
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
        # Keep the Whisper ASR model (used only to auto-transcribe reference
        # audio when a profile has no transcript) off the GPU. On an 11 GB
        # Pascal card the main model already runs in fp32 near the VRAM cap, so
        # letting ASR (~1.5 GB) land on CUDA can push a clone over the edge.
        # asr_device is an OmniVoice >= 0.2.1 from_pretrained kwarg; on older
        # builds it is silently ignored.
        self._models[cache_key] = OmniVoice.from_pretrained(
            model_path, device_map=device, dtype=dtype, asr_device="cpu"
        )
        return self._models[cache_key]


def _load_or_build_voice_prompt(
    model: Any,
    asset_dir: Path,
    audio_path: Path,
    transcript: str,
) -> Any | None:
    """
    Load a cached voice clone prompt from asset_dir, else build it via
    model.create_voice_clone_prompt() and cache it.

    Prefers OmniVoice >= 0.2.1's ``VoiceClonePrompt.save()/load()`` (a
    torch-serialised dict, safe to load with ``weights_only=True``) over
    pickling the live object, which was fragile across torch/transformers
    upgrades. Legacy ``.pkl`` caches are still read once, then superseded by a
    ``.pt`` on the next build. Returns None if the model API is unavailable.
    """
    prompt_cls = _voice_clone_prompt_cls()
    pt_path = asset_dir / "voice_clone_prompt.pt"
    if prompt_cls is not None and hasattr(prompt_cls, "load") and pt_path.exists():
        try:
            return prompt_cls.load(str(pt_path))
        except Exception:
            pt_path.unlink(missing_ok=True)

    # Legacy pickle cache written by pre-0.2.1 builds — read once if present.
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

    _cache_voice_prompt(prompt, asset_dir, pt_path, pkl_path)
    return prompt


def _voice_clone_prompt_cls() -> Any | None:
    try:
        from omnivoice import VoiceClonePrompt

        return VoiceClonePrompt
    except Exception:
        return None


def _build_generation_config(num_step: int | None) -> Any | None:
    """Build an OmniVoiceGenerationConfig overriding the diffusion step count.

    Returns None (model defaults) when num_step is unset or the config class is
    unavailable, so a missing value never blocks generation.
    """
    if not num_step:
        return None
    try:
        from omnivoice import OmniVoiceGenerationConfig
    except Exception:
        return None
    try:
        return OmniVoiceGenerationConfig(num_step=int(num_step))
    except Exception:
        return None


def _cache_voice_prompt(
    prompt: Any, asset_dir: Path, pt_path: Path, pkl_path: Path
) -> None:
    try:
        asset_dir.mkdir(parents=True, exist_ok=True)
    except Exception:
        return
    saver = getattr(prompt, "save", None)
    if callable(saver):
        try:
            saver(str(pt_path))
            pkl_path.unlink(missing_ok=True)  # retire any stale legacy cache
            return
        except Exception:
            pass
    # Fallback for builds without VoiceClonePrompt.save().
    try:
        with pkl_path.open("wb") as f:
            pickle.dump(prompt, f)
    except Exception:
        pass


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
    tokenizer_path = resolve_model_path("models/tokenizer/higgs-audio-v2-tokenizer")
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
