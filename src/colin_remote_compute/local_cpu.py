"""A CPU-only slot using Studio's installed workers, without a network hop."""
from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import shutil
import tempfile
import zipfile
from pathlib import Path

import numpy as np
import soundfile as sf

from omni_tts_core.engines.preset_onnx_engine import _JsonLineWorker
from omni_tts_core.model_registry import ModelRegistry
from omni_tts_core.storage_paths import hf_cache_env, hf_repo_cache_dirs
from omni_tts_core.worker_installation import is_worker_installed, worker_for_spec
from omni_tts_shared.errors import GenerationError

from .broker.models import WorkerModelCapability


LOCAL_CPU_ID = "studio-local-cpu"
LOCAL_CPU_LABEL = f"CPU máy này ({platform.node()})"
CODEC_REPO = "OpenMOSS-Team/MOSS-Audio-Tokenizer-Nano-ONNX"


def _snapshot(repo: str) -> Path:
    for cache in hf_repo_cache_dirs(repo):
        ref = cache / "refs" / "main"
        if ref.is_file():
            revision = ref.read_text().strip()
            if re.fullmatch(r"[a-f0-9]{40}", revision):
                snapshot = cache / "snapshots" / revision
                if snapshot.is_dir():
                    return snapshot
    raise GenerationError(f"Chưa có model trong cache máy này: {repo}.")


def _file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _folder_revision(root: Path, files: list[str], *, expected_hashes: dict[str, str] | None = None,
                     force_content: bool = False) -> str:
    """Use a Hub revision when available, or identify installed package bytes.

    Imported/local copies do not have Hub download metadata. Their content hash
    gives a stable identity without downloading or changing any model file.
    """
    revisions = set()
    hashes = {}
    expected_hashes = expected_hashes or {}
    for name in files:
        path = root / name
        if not path.is_file() or not path.stat().st_size:
            raise GenerationError(f"Model trên máy này thiếu tệp {name}. Kiểm tra thư mục model hoặc nhập lại package.")
        if name in expected_hashes:
            hashes[name] = _file_digest(path)
            if hashes[name] != expected_hashes[name].lower():
                raise GenerationError(f"Tệp {name} không khớp SHA-256 của package đã khai báo. Kiểm tra đúng package model.")
        metadata = root / ".cache" / "huggingface" / "download" / (name + ".metadata")
        lines = metadata.read_text().splitlines() if metadata.is_file() else []
        revisions.add(lines[0].strip() if lines else "")
    if not force_content and len(revisions) == 1 and re.fullmatch(r"[a-f0-9]{40}", next(iter(revisions), "")):
        return revisions.pop()
    # Roles/order, not installation paths or filenames, define package identity.
    contents = [hashes.get(name) or _file_digest(root / name) for name in files]
    return "files-sha256:" + hashlib.sha256(json.dumps(contents).encode("ascii")).hexdigest()


class LocalCpuExecutor:
    def __init__(self, model_id: str):
        self.spec = spec = ModelRegistry().get(model_id)
        self.worker_name = worker_for_spec(spec) or ("piper_worker" if spec.provider == "piper" else "")
        if not self.worker_name or not is_worker_installed(self.worker_name):
            raise GenerationError("Worker CPU trên máy này chưa được cài. Mở tab Model để cài worker.")
        if spec.provider == "vieneu" and model_id == "vieneu_v3_turbo":
            self.root = _snapshot(spec.hf_repo)
            self.codec = _snapshot(CODEC_REPO)
            required = ["vieneu_prefill.onnx", "vieneu_decode_step.onnx", "vieneu_acoustic_cached.onnx",
                        "vieneu_backbone_shared.data", "vieneu_v3_heads.npz", "config.json", "tokenizer.json"]
            codec_files = ["moss_audio_tokenizer_decode_full.onnx", "moss_audio_tokenizer_decode_shared.data",
                           "moss_audio_tokenizer_decode_step.onnx", "codec_browser_onnx_meta.json",
                           "moss_audio_tokenizer_encode.onnx", "moss_audio_tokenizer_encode.data"]
            if any(not (self.root / "onnx_update" / name).is_file() for name in required) or any(
                not (self.codec / name).is_file() for name in codec_files
            ):
                raise GenerationError("VieNeu CPU trên máy này chưa đủ model ONNX FP32 và codec.")
            revision, rate = self.root.name + "+" + self.codec.name, 48000
        elif spec.provider in {"zerotts", "piper"}:
            self.root = spec.local_path
            files = list(dict.fromkeys([str(spec.runtime["model_file"]), str(spec.runtime["config_file"]),
                                        *spec.runtime.get("required_files", [])]))
            expected = {str(spec.runtime[file_key]): str(spec.runtime[hash_key])
                        for file_key, hash_key in (("model_file", "model_sha256"), ("config_file", "config_sha256"))
                        if spec.runtime.get(hash_key)}
            revision = _folder_revision(self.root, files, expected_hashes=expected,
                                        force_content=getattr(spec, "source_kind", "") == "manual")
            config = json.loads((self.root / str(spec.runtime["config_file"])).read_text(encoding="utf-8"))
            rate = int(config.get("audio", {}).get("sample_rate", 48000)) if spec.provider == "piper" else 48000
        else:
            raise GenerationError("Model này chưa hỗ trợ CPU kết hợp.")
        self.capability = WorkerModelCapability(
            model_id=model_id, provider_id=spec.provider, execution_backend="cpu", revision=revision,
            sample_rate=rate, supports_profile_clone=spec.provider == "vieneu",
            supports_batch=spec.provider == "vieneu", supports_segments=spec.provider == "piper",
            output_formats=("wav", "zip") if spec.provider == "vieneu" else ("wav",),
        )
        self.worker = None

    def close(self):
        if self.worker is not None:
            self.worker.close()
            self.worker = None

    def execute(self, context, unit, digest, rate):
        request = unit.request
        if (request.model_revision, rate) != (self.capability.revision, self.capability.sample_rate):
            raise GenerationError("Phiên bản model CPU máy này không khớp nhóm chia tải.")
        context.check(unit.cancel_event)
        cache, proof = context.cache_paths(request, unit.destination, is_pc=True)[1:]
        if context.copy_verified(cache, proof, unit.destination):
            return
        if self.worker is None:
            self.worker = _JsonLineWorker(self.worker_name, LOCAL_CPU_LABEL, environment={
                **hf_cache_env(), "HF_HUB_OFFLINE": "1", "CUDA_VISIBLE_DEVICES": "",
            })
        with tempfile.TemporaryDirectory(prefix="colin-local-cpu-") as folder:
            root = Path(folder)
            texts = request.batch_texts or (request.text,)
            paths = [root / f"chunk_{index:04d}.wav" for index in range(1, len(texts) + 1)]
            payload = self._payload(request, texts, paths, root, unit.reference_audio)
            self.worker.run(payload, timeout=600, cancel_event=unit.cancel_event,
                            tick_callback=lambda: context.check(unit.cancel_event))
            context.check(unit.cancel_event)
            for path in paths:
                audio, sample_rate = sf.read(path, dtype="float32")
                if sample_rate != rate or audio.ndim != 1 or not audio.size or not np.isfinite(audio).all():
                    raise GenerationError("CPU máy này trả audio không hợp lệ hoặc sai tần số.")
            temporary = root / ("result" + unit.destination.suffix)
            if request.batch_texts:
                with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_STORED) as archive:
                    for path in paths:
                        archive.write(path, path.name)
            else:
                shutil.copyfile(paths[0], temporary)
            shutil.copyfile(temporary, cache)
            proof.write_text(hashlib.sha256(cache.read_bytes()).hexdigest())
            shutil.copyfile(cache, unit.destination)
            with context.verified_lock:
                context.store.set_state(context.job_id + ":verified_units", len(list(context.units.glob("*.sha256"))))

    def _payload(self, request, texts, paths, root, reference_audio):
        options = dict(request.provider_options)
        chunks = [{"text": text, "output_path": str(path)} for text, path in zip(texts, paths)]
        if self.spec.provider == "zerotts":
            return {"model_root": str(self.root), "runtime": self.spec.runtime,
                    "speaker_id": request.speaker_id, "language": request.language,
                    "speed": 1.0, "options": options, "chunks": chunks}
        if self.spec.provider == "piper":
            if request.segments:
                chunks[0]["segments"] = [segment.model_dump() for segment in request.segments]
            return {"model_path": str(self.root / str(self.spec.runtime["model_file"])),
                    "config_path": str(self.root / str(self.spec.runtime["config_file"])),
                    "speaker_id": request.speaker_id, **options, "chunks": chunks}
        payload = {"mode": "v3turbo", "device": "cpu", "backend": "onnx", "precision": "fp32",
                   "backbone_repo": str(self.root), "onnx_dir": str(self.root / "onnx_update"),
                   "threads": min(8, os.cpu_count() or 1), "batch": True, "chunks": chunks,
                   "voice_name": request.speaker_id, **options}
        if reference_audio is not None:
            reference = root / "reference.wav"
            reference.write_bytes(reference_audio)
            payload["ref_audio"] = str(reference)
            payload.pop("voice_name", None)
        return payload
