"""
SRT/TXT Parser - Parse subtitle files for batch TTS generation.
Uses regex-based SRT parsing (no external srt library needed).
Ported from Qwen3-TTS app.
"""

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import logging

logger = logging.getLogger(__name__)


@dataclass
class Subtitle:
    """A single subtitle entry."""
    index: int
    content: str
    start_time: Optional[float] = None  # seconds
    end_time: Optional[float] = None  # seconds

    @property
    def char_count(self) -> int:
        """Get character count of content."""
        return len(self.content.strip())


def detect_encoding(file_path: str) -> str:
    """Detect file encoding."""
    encodings = ['utf-8-sig', 'utf-8', 'utf-16', 'latin-1', 'cp1252']

    for encoding in encodings:
        try:
            with open(file_path, 'r', encoding=encoding) as f:
                f.read()
            return encoding
        except (UnicodeDecodeError, UnicodeError):
            continue

    return 'utf-8'  # fallback


def _parse_srt_timestamp(ts: str) -> float:
    """Parse SRT timestamp string to seconds."""
    # Format: HH:MM:SS,mmm
    match = re.match(r'(\d+):(\d+):(\d+)[,.](\d+)', ts.strip())
    if match:
        h, m, s, ms = match.groups()
        return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000.0
    return 0.0


def parse_srt_file(file_path: str) -> list[Subtitle]:
    """
    Parse an SRT subtitle file using regex.

    Args:
        file_path: Path to the SRT file

    Returns:
        List of Subtitle objects
    """
    encoding = detect_encoding(file_path)
    logger.info(f"Reading SRT file with encoding: {encoding}")

    try:
        with open(file_path, 'r', encoding=encoding) as f:
            content = f.read()

        # SRT pattern: index\ntimestamp --> timestamp\ncontent\n\n
        pattern = re.compile(
            r'(\d+)\s*\n'
            r'(\d{1,2}:\d{2}:\d{2}[,.]\d{3})\s*-->\s*(\d{1,2}:\d{2}:\d{2}[,.]\d{3})\s*\n'
            r'((?:(?!\d+\s*\n\d{1,2}:\d{2}:\d{2}).)+)',
            re.MULTILINE
        )

        subtitles = []
        for match in pattern.finditer(content):
            index = int(match.group(1))
            start_time = _parse_srt_timestamp(match.group(2))
            end_time = _parse_srt_timestamp(match.group(3))
            text = match.group(4).strip()

            # Remove HTML tags if any
            text = re.sub(r'<[^>]+>', '', text)
            # Replace newlines within subtitle with space
            text = re.sub(r'\n', ' ', text).strip()

            if text:
                subtitles.append(Subtitle(
                    index=index,
                    content=text,
                    start_time=start_time,
                    end_time=end_time
                ))

        logger.info(f"Parsed {len(subtitles)} subtitles from SRT")
        return subtitles

    except Exception as e:
        logger.error(f"Error parsing SRT file: {e}")
        return []


def parse_txt_file(file_path: str) -> list[Subtitle]:
    """
    Parse a TXT file (one sentence per line).

    Args:
        file_path: Path to the TXT file

    Returns:
        List of Subtitle objects
    """
    encoding = detect_encoding(file_path)
    logger.info(f"Reading TXT file with encoding: {encoding}")

    try:
        with open(file_path, 'r', encoding=encoding) as f:
            lines = f.readlines()

        subtitles = []
        index = 1

        for line in lines:
            text = line.strip()
            if text:  # Skip empty lines
                subtitles.append(Subtitle(
                    index=index,
                    content=text
                ))
                index += 1

        logger.info(f"Parsed {len(subtitles)} lines from TXT")
        return subtitles

    except Exception as e:
        logger.error(f"Error parsing TXT file: {e}")
        return []


def parse_subtitle_file(file_path: str) -> list[Subtitle]:
    """
    Parse a subtitle file (auto-detect format).

    Args:
        file_path: Path to the file

    Returns:
        List of Subtitle objects
    """
    ext = Path(file_path).suffix.lower()

    if ext == '.srt':
        return parse_srt_file(file_path)
    elif ext in ('.txt', '.md'):
        return parse_txt_file(file_path)
    else:
        logger.warning(f"Unknown file extension: {ext}, trying as TXT")
        return parse_txt_file(file_path)


def calculate_total_characters(subtitles: list[Subtitle]) -> int:
    """Calculate total characters across all subtitles."""
    return sum(sub.char_count for sub in subtitles)
