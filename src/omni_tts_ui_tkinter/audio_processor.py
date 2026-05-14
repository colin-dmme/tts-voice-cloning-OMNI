"""
Audio Processor - Trim silence and adjust speed.
Ported from Qwen3-TTS app.
"""

import io
import os
import sys
import subprocess
from pathlib import Path
from typing import Optional

import logging

logger = logging.getLogger(__name__)

# Windows: hide subprocess console windows
_SUBPROCESS_FLAGS = {}
if sys.platform == "win32":
    _SUBPROCESS_FLAGS["creationflags"] = subprocess.CREATE_NO_WINDOW

# Check if pydub is available
try:
    from pydub import AudioSegment
    from pydub.silence import detect_silence
    PYDUB_AVAILABLE = True
except ImportError:
    PYDUB_AVAILABLE = False
    logger.warning("pydub not available - trim features disabled")


def check_ffmpeg() -> bool:
    """Check if FFmpeg is available."""
    try:
        result = subprocess.run(
            ['ffmpeg', '-version'],
            capture_output=True,
            text=True,
            timeout=5,
            **_SUBPROCESS_FLAGS
        )
        return result.returncode == 0
    except Exception:
        return False


FFMPEG_AVAILABLE = check_ffmpeg()


def trim_silence(
    audio_path: str,
    output_path: str,
    silence_thresh: int = -40,
    min_silence_len: int = 50,
    padding_ms: int = 50
) -> bool:
    """
    Trim silence from audio file.

    Args:
        audio_path: Input audio file path
        output_path: Output audio file path
        silence_thresh: Silence threshold in dBFS (default -40)
        min_silence_len: Minimum silence length in ms (default 50)
        padding_ms: Padding to keep at start/end in ms (default 50)

    Returns:
        True if successful
    """
    if not PYDUB_AVAILABLE:
        logger.error("pydub not available for trimming")
        return False

    try:
        audio = AudioSegment.from_file(audio_path)

        # Detect silence
        silent_ranges = detect_silence(
            audio,
            min_silence_len=min_silence_len,
            silence_thresh=silence_thresh
        )

        if not silent_ranges:
            # No silence detected, just copy
            fmt = "mp3" if output_path.lower().endswith('.mp3') else "wav"
            audio.export(output_path, format=fmt)
            return True

        # Find start and end of actual content
        start_trim = silent_ranges[0][1] if silent_ranges[0][0] == 0 else 0
        end_trim = silent_ranges[-1][0] if silent_ranges[-1][1] == len(audio) else len(audio)

        # Apply padding
        start_trim = max(0, start_trim - padding_ms)
        end_trim = min(len(audio), end_trim + padding_ms)

        # Trim
        trimmed = audio[start_trim:end_trim]
        fmt = "mp3" if output_path.lower().endswith('.mp3') else "wav"
        trimmed.export(output_path, format=fmt)

        logger.info(f"Trimmed: {len(audio)}ms -> {len(trimmed)}ms")
        return True

    except Exception as e:
        logger.error(f"Error trimming audio: {e}")
        return False


def adjust_speed(audio_path: str, speed: float = 1.0) -> bool:
    """
    Adjust audio speed using FFmpeg (preserves pitch).

    Args:
        audio_path: Path to audio file (will be modified in place)
        speed: Speed factor (1.0 = normal, 1.5 = 50% faster)

    Returns:
        True if successful
    """
    if not FFMPEG_AVAILABLE:
        logger.warning("FFmpeg not available for speed adjustment")
        return False

    if speed == 1.0:
        return True

    try:
        # Create temp file with same extension
        ext = os.path.splitext(audio_path)[1] or ".mp3"
        temp_path = audio_path + f".temp{ext}"

        # FFmpeg command for speed adjustment with pitch preservation
        cmd = [
            'ffmpeg', '-y',
            '-i', audio_path,
            '-filter:a', f'atempo={speed}',
            '-vn',
            temp_path
        ]

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,
            **_SUBPROCESS_FLAGS
        )

        if result.returncode == 0:
            # Replace original with temp
            os.replace(temp_path, audio_path)
            logger.info(f"Speed adjusted to {speed}x: {audio_path}")
            return True
        else:
            logger.error(f"FFmpeg error: {result.stderr}")
            if os.path.exists(temp_path):
                os.remove(temp_path)
            return False

    except Exception as e:
        logger.error(f"Speed adjustment error: {e}")
        return False
