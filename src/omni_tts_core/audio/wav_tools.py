from __future__ import annotations

from pathlib import Path

import numpy as np
import soundfile as sf

from omni_tts_shared.errors import ConfigError


def concatenate_segments(
    segments: list[np.ndarray],
    sample_rate: int,
    pause_ms: int,
    crossfade_ms: int = 0,
) -> np.ndarray:
    if not segments:
        return np.array([], dtype=np.float32)
    if len(segments) == 1:
        return _to_mono_float32(segments[0])

    mono = [_to_mono_float32(s) for s in segments]

    if pause_ms > 0:
        pause = np.zeros(int(sample_rate * pause_ms / 1000), dtype=np.float32)
        pieces: list[np.ndarray] = []
        for index, segment in enumerate(mono):
            pieces.append(segment)
            if index < len(mono) - 1:
                pieces.append(pause)
        return np.concatenate(pieces)

    if crossfade_ms > 0:
        crossfade_samples = int(sample_rate * crossfade_ms / 1000)
        result = mono[0]
        for next_seg in mono[1:]:
            overlap = min(len(result), len(next_seg), crossfade_samples)
            if overlap <= 0:
                result = np.concatenate([result, next_seg])
                continue
            fade_out = np.linspace(1.0, 0.0, overlap, dtype=np.float32)
            fade_in = np.linspace(0.0, 1.0, overlap, dtype=np.float32)
            blended = result[-overlap:] * fade_out + next_seg[:overlap] * fade_in
            result = np.concatenate([result[:-overlap], blended, next_seg[overlap:]])
        return result

    return np.concatenate(mono)


def save_wav(path: Path, audio: np.ndarray, sample_rate: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(path), _to_mono_float32(audio), sample_rate)


def duration_seconds(audio: np.ndarray, sample_rate: int) -> float:
    if sample_rate <= 0:
        return 0.0
    return float(len(audio) / sample_rate)


def load_audio_info(path: Path) -> tuple[float, int]:
    """Return (duration_seconds, sample_rate) from a sound file without loading audio data."""
    info = sf.info(str(path))
    return float(info.frames / info.samplerate), int(info.samplerate)


def convert_to_wav_24k_mono(src: Path, dst: Path) -> None:
    """Read src (WAV/FLAC/OGG, MP3 nếu libsndfile hỗ trợ hoặc ffmpeg có sẵn),
    convert to mono float32 24kHz, write WAV PCM_16 at dst.
    Raises ConfigError if format cannot be read by any available method."""
    try:
        audio, src_rate = sf.read(str(src), dtype="float32")
    except Exception:
        # soundfile không đọc được (thường là MP3 trên libsndfile < 1.1.0)
        # → thử convert qua ffmpeg trước, rồi đọc lại bằng soundfile
        audio, src_rate = _read_via_ffmpeg(src)

    audio = _to_mono_float32(audio)
    if src_rate != 24000:
        audio = _resample(audio, src_rate, 24000)
    dst.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(dst), audio, 24000, subtype="PCM_16")


def _read_via_ffmpeg(src: Path) -> tuple[np.ndarray, int]:
    """Dùng ffmpeg để decode src sang WAV tạm thời, sau đó đọc bằng soundfile.
    Raises ConfigError nếu ffmpeg không có hoặc convert thất bại."""
    import shutil
    import subprocess
    import tempfile

    ffmpeg_bin = shutil.which("ffmpeg")
    if ffmpeg_bin is None:
        raise ConfigError(
            f"Không đọc được file '{src.suffix.lstrip('.').upper()}'. "
            "Hãy cài ffmpeg (thêm vào PATH) hoặc dùng định dạng WAV/FLAC."
        )

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp_path = Path(tmp.name)

    try:
        result = subprocess.run(
            [
                ffmpeg_bin, "-y",
                "-i", str(src),
                "-ar", "24000",
                "-ac", "1",
                "-sample_fmt", "s16",
                str(tmp_path),
            ],
            capture_output=True,
            timeout=60,
        )
        if result.returncode != 0:
            raise ConfigError(
                f"ffmpeg không convert được file '{src.name}'. "
                "Kiểm tra lại file audio có bị hỏng không."
            )
        audio, sr = sf.read(str(tmp_path), dtype="float32")
        return audio, sr
    finally:
        tmp_path.unlink(missing_ok=True)


def _resample(audio: np.ndarray, orig_rate: int, target_rate: int) -> np.ndarray:
    try:
        from math import gcd
        from scipy.signal import resample_poly
        d = gcd(orig_rate, target_rate)
        return resample_poly(audio, target_rate // d, orig_rate // d).astype(np.float32)
    except ImportError:
        pass
    orig_len = len(audio)
    target_len = int(orig_len * target_rate / orig_rate)
    return np.interp(
        np.linspace(0, orig_len - 1, target_len),
        np.arange(orig_len),
        audio,
    ).astype(np.float32)


def _to_mono_float32(audio: np.ndarray) -> np.ndarray:
    array = np.asarray(audio)
    if array.ndim == 2 and array.shape[0] <= 8 and array.shape[0] < array.shape[1]:
        array = array.mean(axis=0)
    elif array.ndim == 2:
        array = array.mean(axis=1)
    return array.astype(np.float32, copy=False)
