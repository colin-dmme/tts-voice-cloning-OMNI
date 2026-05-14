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
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.isdigit() or "-->" in line:
            continue
        line = re.sub(r"<[^>]+>", "", line)
        if line:
            lines.append(line)
    return "\n".join(lines)


def parse_srt_units(content: str) -> list[SourceUnit]:
    units = []
    blocks = re.split(r"\n\s*\n", content.replace("\r", "\n").strip())
    for block in blocks:
        lines = []
        for raw_line in block.splitlines():
            line = raw_line.strip()
            if not line or line.isdigit() or "-->" in line:
                continue
            line = re.sub(r"<[^>]+>", "", line).strip()
            if line:
                lines.append(line)
        text = " ".join(lines).strip()
        if text:
            units.append(SourceUnit(index=len(units) + 1, text=text))
    return units


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
