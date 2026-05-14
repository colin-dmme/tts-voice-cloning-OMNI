from __future__ import annotations

import re


_SENTENCE_PATTERN = re.compile(r"(?<=[.!?。！？])\s+")
_SOFT_BREAK_PATTERN = re.compile(r"(?<=[,;:，；：])\s+")


def split_text(text: str, max_chars: int = 220) -> list[str]:
    if not text.strip():
        return []
    sentences = []
    for line in _normalize_lines(text):
        sentences.extend(_split_line(line))
    sentences = [part for part in sentences if part]
    chunks: list[str] = []
    current = ""
    for sentence in sentences:
        if len(sentence) > max_chars:
            if current:
                chunks.append(current)
                current = ""
            chunks.extend(_split_long_sentence(sentence, max_chars))
            continue
        candidate = f"{current} {sentence}".strip()
        if current and len(candidate) > max_chars:
            chunks.append(current)
            current = sentence
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks


def _split_long_sentence(sentence: str, max_chars: int) -> list[str]:
    parts = _SOFT_BREAK_PATTERN.split(sentence)
    chunks: list[str] = []
    current = ""
    for part in parts:
        if len(part) > max_chars:
            if current:
                chunks.append(current)
                current = ""
            chunks.extend(_split_by_words(part, max_chars))
            continue
        candidate = f"{current} {part}".strip()
        if current and len(candidate) > max_chars:
            chunks.append(current)
            current = part
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks


def _normalize_lines(text: str) -> list[str]:
    lines = []
    for raw_line in text.replace("\r", "\n").split("\n"):
        line = " ".join(raw_line.split()).strip()
        if line:
            lines.append(line)
    return lines


def _split_line(line: str) -> list[str]:
    if line.startswith(("-", "•", "*")):
        return [line]
    return [part.strip() for part in _SENTENCE_PATTERN.split(line) if part.strip()]


def _split_by_words(text: str, max_chars: int) -> list[str]:
    chunks: list[str] = []
    current = ""
    for word in text.split():
        candidate = f"{current} {word}".strip()
        if current and len(candidate) > max_chars:
            chunks.append(current)
            current = word
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks
