from __future__ import annotations

import re
from pathlib import Path
from dataclasses import dataclass

from omni_tts_shared.errors import ConfigError


SUPPORTED_TEXT_EXTENSIONS = {".txt", ".md", ".srt"}


@dataclass(frozen=True)
class SourceUnit:
    index: int
    text: str


def read_source_text(path: Path) -> str:
    if not path.exists():
        raise ConfigError(f"Không tìm thấy file nguồn: {path}")
    if path.suffix.lower() not in SUPPORTED_TEXT_EXTENSIONS:
        allowed = ", ".join(sorted(SUPPORTED_TEXT_EXTENSIONS))
        raise ConfigError(f"File nguồn chưa được hỗ trợ. Định dạng hiện có: {allowed}")
    content = path.read_text(encoding="utf-8-sig")
    if path.suffix.lower() == ".srt":
        return strip_srt_markup(content)
    return content.strip()


def count_source_text_chars(path: Path) -> int:
    return len(read_source_text(path))


def read_source_units(path: Path) -> list[SourceUnit]:
    if not path.exists():
        raise ConfigError(f"Không tìm thấy file nguồn: {path}")
    if path.suffix.lower() not in SUPPORTED_TEXT_EXTENSIONS:
        allowed = ", ".join(sorted(SUPPORTED_TEXT_EXTENSIONS))
        raise ConfigError(f"File nguồn chưa được hỗ trợ. Định dạng hiện có: {allowed}")
    content = path.read_text(encoding="utf-8-sig")
    if path.suffix.lower() == ".srt":
        return parse_srt_units(content)
    return paragraph_units(content)


def strip_srt_markup(content: str) -> str:
    lines = []
    for block in _srt_blocks(content):
        lines.extend(_srt_text_lines(block))
    return "\n".join(lines)


def parse_srt_units(content: str) -> list[SourceUnit]:
    units = []
    for block in _srt_blocks(content):
        lines = _srt_text_lines(block)
        text = " ".join(lines).strip()
        if text:
            units.append(SourceUnit(index=len(units) + 1, text=text))
    return units


def _srt_blocks(content: str) -> list[str]:
    normalized = content.replace("\r", "\n").strip()
    if not normalized:
        return []
    return re.split(r"\n\s*\n", normalized)


def _srt_text_lines(block: str) -> list[str]:
    raw_lines = [line.strip() for line in block.splitlines() if line.strip()]
    if len(raw_lines) >= 2 and raw_lines[0].isdigit() and "-->" in raw_lines[1]:
        raw_lines = raw_lines[1:]

    lines = []
    for line in raw_lines:
        if "-->" in line:
            continue
        line = re.sub(r"<[^>]+>", "", line).strip()
        if line:
            lines.append(line)
    return lines


def paragraph_units(content: str) -> list[SourceUnit]:
    normalized = content.replace("\r", "\n").strip()
    parts = re.split(r"\n\s*\n+", normalized)
    units = []
    for part in parts:
        text = " ".join(part.split()).strip()
        if text:
            units.append(SourceUnit(index=len(units) + 1, text=text))
    return units


def text_units_from_blank_lines(content: str) -> list[SourceUnit]:
    return paragraph_units(content)
