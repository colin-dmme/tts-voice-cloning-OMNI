from __future__ import annotations

import argparse
import gc
import json
import os
import subprocess
import sys
from pathlib import Path

UNCONDITIONED_VOICE_ID = "__unconditioned__"
SAMPLE_RATE = 48_000

_RUNTIME = None
_RUNTIME_KEY: tuple[str, int] | None = None
_CODEC = None
_CODEC_KEY: tuple[str, int] | None = None
_TOKENIZER = None
_TOKENIZER_KEY: str | None = None


class NativeRuntime:
    def __init__(self, executable: Path, model_path: Path, threads: int) -> None:
        creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        self.process = subprocess.Popen(
            [str(executable), str(model_path), str(threads)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            bufsize=1,
            creationflags=creationflags,
        )
        assert self.process.stdout is not None
        ready = self.process.stdout.readline().strip()
        if not ready.startswith("READY\t"):
            error = self.process.stderr.read() if self.process.stderr else ""
            self.close()
            raise RuntimeError(
                error.strip() or "Native ZeroTTS GGUF không khởi động được."
            )

    def close(self) -> None:
        if self.process.poll() is None:
            self.process.terminate()

    def generate(
        self,
        *,
        ids: list[int],
        voice_path: Path,
        seed: int,
        options: dict,
    ):
        import numpy as np

        fields = [
            "GENERATE",
            str(voice_path),
            str(seed & 0xFFFFFFFF),
            str(int(options.get("min_frames", 4))),
            str(int(options.get("max_frames", 1500))),
            str(int(options.get("eoa_extra_frames", 1))),
            str(float(options.get("text_temperature", 1.0))),
            str(int(options.get("text_topk", 50))),
            str(float(options.get("audio_temperature", 0.8))),
            str(int(options.get("audio_topk", 25))),
            str(float(options.get("audio_topp", 0.95))),
            str(float(options.get("audio_repetition_penalty", 1.2))),
            ",".join(str(value) for value in ids),
        ]
        assert self.process.stdin is not None and self.process.stdout is not None
        self.process.stdin.write("\t".join(fields) + "\n")
        self.process.stdin.flush()
        response = self.process.stdout.readline().rstrip("\r\n")
        if response.startswith("ERR\t"):
            raise RuntimeError(response.split("\t", 1)[1])
        if not response.startswith("OK\t"):
            error = self.process.stderr.read() if self.process.stderr else ""
            raise RuntimeError(
                error.strip() or "Native ZeroTTS GGUF trả dữ liệu không hợp lệ."
            )
        frames = np.asarray(json.loads(response.split("\t", 1)[1]), dtype=np.int32)
        if frames.ndim != 2 or not frames.size:
            raise RuntimeError("ZeroTTS GGUF trả về frame rỗng.")
        return frames.T[None, :, :]


def _native_executable() -> Path:
    name = (
        "omni-zerotts-gguf-server.exe"
        if os.name == "nt"
        else "omni-zerotts-gguf-server"
    )
    path = Path(__file__).resolve().parent / "native" / "bin" / name
    if not path.is_file():
        raise FileNotFoundError(
            "Thiếu runtime ZeroTTS GGUF native. Hãy cài lại worker GGUF từ Quản lý model."
        )
    return path


def _load_runtime(model_root: Path, runtime: dict, options: dict) -> NativeRuntime:
    global _RUNTIME, _RUNTIME_KEY

    model_file = str(runtime.get("model_file") or "").strip()
    if not model_file:
        raise ValueError("Model ZeroTTS GGUF chưa khai báo model_file.")
    model_path = model_root / model_file
    threads = int(options.get("intra_op_num_threads", 4))
    if threads < 1:
        raise ValueError("Số luồng ggml phải từ 1 trở lên.")
    key = (str(model_path.resolve()), threads)
    if _RUNTIME is None or _RUNTIME_KEY != key:
        if _RUNTIME is not None:
            _RUNTIME.close()
        _RUNTIME = NativeRuntime(_native_executable(), model_path, threads)
        _RUNTIME_KEY = key
    return _RUNTIME


def _load_codec(model_root: Path, options: dict):
    global _CODEC, _CODEC_KEY
    from zerotts.codec import MossCodecDecoder

    codec_threads = int(options.get("codec_intra_op_num_threads", 0))
    if codec_threads < 0:
        raise ValueError("Số luồng ONNX cho codec không được âm.")
    resolved_threads = codec_threads or int(options.get("intra_op_num_threads", 4))
    key = (str(model_root.resolve()), resolved_threads)
    if _CODEC is None or _CODEC_KEY != key:
        _CODEC = None
        gc.collect()
        _CODEC = MossCodecDecoder(
            model_root / "onnx" / "codec",
            providers=["CPUExecutionProvider"],
            intra_op_num_threads=resolved_threads,
        )
        _CODEC_KEY = key
    return _CODEC


def _load_tokenizer(model_root: Path):
    global _TOKENIZER, _TOKENIZER_KEY
    from zerotts.tokenizer import load_tokenizer

    key = str(model_root.resolve())
    if _TOKENIZER is None or _TOKENIZER_KEY != key:
        config = json.loads((model_root / "config.json").read_text(encoding="utf-8"))
        _TOKENIZER = load_tokenizer(config, model_root)
        _TOKENIZER_KEY = key
    return _TOKENIZER


def _prepare_segments(text: str, language: str, options: dict) -> list[str]:
    from zerotts.chunking import (
        chunk_text,
        clean_segment_punctuation,
        normalize_punctuation,
    )
    from zerotts.text_norm import normalize_vi_text

    prepared = text.strip()
    if language == "vi" and bool(options.get("normalize_vi_text", True)):
        prepared = normalize_vi_text(prepared)
    if bool(options.get("normalize_punctuation", True)):
        prepared = normalize_punctuation(prepared)
    segments = chunk_text(
        prepared, max_chunk_sec=float(options.get("max_chunk_sec", 15.0))
    )
    if bool(options.get("clean_segment_punctuation", True)):
        segments = [clean_segment_punctuation(item) for item in segments]
    return [item for item in segments if item and item.strip()]


def _voice_path(model_root: Path, speaker_id: str | None) -> Path:
    voice = str(speaker_id or "").strip()
    if not voice:
        raise ValueError("Chưa chọn voice pack ZeroTTS.")
    if voice != UNCONDITIONED_VOICE_ID:
        path = model_root / "voices" / voice / "voice.bin"
        if not path.is_file():
            raise FileNotFoundError(f"Không tìm thấy voice.bin của giọng {voice}.")
        return path

    import numpy as np

    cache = model_root / ".omni-cache"
    cache.mkdir(parents=True, exist_ok=True)
    path = cache / "null_voice.bin"
    source = model_root / "null_voice_emb.npy"
    if not path.is_file() or path.stat().st_mtime_ns < source.stat().st_mtime_ns:
        np.load(source).astype(np.float32).reshape(-1).tofile(path)
    return path


def _decode_frames(codec, frames, options: dict):
    import numpy as np

    if not bool(options.get("streaming_decoder", True)):
        return np.asarray(codec.decode(frames), dtype=np.float32).reshape(-1)

    first = int(options.get("first_chunk_frames", 1))
    cap = int(options.get("max_chunk_frames", 16))
    if first < 1 or cap < 1 or first > cap:
        raise ValueError("Frame streaming đầu phải từ 1 đến trần frame mỗi chunk.")
    decoder = codec.streaming_decoder()
    chunks = []
    start = 0
    target = first
    try:
        while start < frames.shape[2]:
            end = min(frames.shape[2], start + target)
            chunks.append(
                np.asarray(decoder.decode_chunk(frames[:, :, start:end])).reshape(-1)
            )
            start = end
            target = min(cap, target * 2)
    finally:
        decoder.close()
    return np.concatenate(chunks) if chunks else np.zeros(0, dtype=np.float32)


def _synthesize(payload: dict) -> None:
    import numpy as np
    import soundfile as sf

    model_root = Path(payload["model_root"])
    runtime = dict(payload.get("runtime") or {})
    options = dict(payload.get("options") or {})
    generator = _load_runtime(model_root, runtime, options)
    codec = _load_codec(model_root, options)
    tokenizer = _load_tokenizer(model_root)
    voice = _voice_path(model_root, payload.get("speaker_id"))
    language = str(payload.get("language") or "vi")
    configured_seed = int(options.get("seed", -1))
    gap_seconds = float(options.get("segment_gap_seconds", 0.08))
    random_source = np.random.default_rng(
        None if configured_seed < 0 else configured_seed
    )

    for chunk in payload.get("chunks") or []:
        segments = _prepare_segments(str(chunk.get("text") or ""), language, options)
        if not segments:
            raise ValueError("Đoạn ZeroTTS không có nội dung hợp lệ.")
        parts = []
        for index, segment in enumerate(segments):
            ids = tokenizer(segment).astype(np.int32).reshape(-1).tolist()
            segment_seed = int(random_source.integers(0, 2**32, dtype=np.uint32))
            frames = generator.generate(
                ids=ids, voice_path=voice, seed=segment_seed, options=options
            )
            audio = _decode_frames(codec, frames, options)
            if not audio.size:
                raise ValueError("ZeroTTS GGUF trả về audio rỗng.")
            parts.append(audio)
            if index < len(segments) - 1 and gap_seconds > 0:
                parts.append(np.zeros(int(SAMPLE_RATE * gap_seconds), dtype=np.float32))
        output = Path(chunk["output_path"])
        output.parent.mkdir(parents=True, exist_ok=True)
        sf.write(str(output), np.concatenate(parts), SAMPLE_RATE, subtype="PCM_16")


def _serve() -> None:
    try:
        for line in sys.stdin:
            try:
                _synthesize(json.loads(line))
                response = {"ok": True}
            except Exception as exc:  # noqa: BLE001 - return worker errors over JSON Lines
                response = {"ok": False, "error": str(exc)}
            sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
            sys.stdout.flush()
    finally:
        if _RUNTIME is not None:
            _RUNTIME.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", type=Path)
    parser.add_argument("--serve", action="store_true")
    args = parser.parse_args()
    if args.serve:
        _serve()
    elif args.request:
        _synthesize(json.loads(args.request.read_text(encoding="utf-8-sig")))
    else:
        parser.error("Cần --serve hoặc --request.")


if __name__ == "__main__":
    main()
