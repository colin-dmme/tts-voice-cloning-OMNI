from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from pathlib import Path
from urllib.parse import unquote, urlparse


SplitList = Callable[[str], Iterable[str]]

_QUOTED_OR_BRACED_RE = re.compile(r'"([^"]+)"|\'([^\']+)\'|\{([^{}]+)\}')


def parse_path_text(value: str, splitlist: SplitList | None = None) -> list[Path]:
    paths: list[Path] = []
    normalized = str(value or "").replace("\r\n", "\n").replace("\r", "\n")
    for segment in normalized.splitlines():
        for token in _path_tokens(segment, splitlist):
            paths.append(path_from_text(token))
    return paths


def path_from_text(value: str) -> Path:
    text = _strip_wrapping(value.strip())
    parsed = urlparse(text)
    if parsed.scheme.lower() == "file":
        if parsed.netloc:
            text = f"//{parsed.netloc}{unquote(parsed.path)}"
        else:
            text = unquote(parsed.path)
            if re.match(r"^/[A-Za-z]:", text):
                text = text[1:]
    return Path(text)


def _path_tokens(segment: str, splitlist: SplitList | None) -> list[str]:
    stripped = segment.strip()
    if not stripped:
        return []
    quoted = _quoted_or_braced_tokens(stripped)
    if quoted:
        return quoted
    structured = _split_structured_list(stripped, splitlist)
    if structured is not None:
        return structured
    if "\t" in stripped:
        return _nonempty(stripped.split("\t"))
    if ";" in stripped:
        return _nonempty(stripped.split(";"))
    return [stripped]


def _split_structured_list(value: str, splitlist: SplitList | None) -> list[str] | None:
    if splitlist is None or not any(char in value for char in "{}"):
        return None
    try:
        tokens = _nonempty(splitlist(value))
    except Exception:
        return None
    if len(tokens) > 1 or (tokens and tokens[0] != value):
        return tokens
    return None


def _quoted_or_braced_tokens(value: str) -> list[str]:
    matches = _QUOTED_OR_BRACED_RE.findall(value)
    return _nonempty(double or single or braced for double, single, braced in matches)


def _strip_wrapping(value: str) -> str:
    text = value.strip()
    for left, right in (("{", "}"), ('"', '"'), ("'", "'")):
        if text.startswith(left) and text.endswith(right) and len(text) >= 2:
            text = text[1:-1].strip()
    return text


def _nonempty(values: Iterable[str]) -> list[str]:
    return [str(value).strip() for value in values if str(value).strip()]
