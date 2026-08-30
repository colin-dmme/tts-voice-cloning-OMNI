"""Derive a memorable, filesystem-safe output stem from raw text.

Direct text generations have no source file to name the audio after. Instead of
a generic ``output.mp3``, take the first characters of the text so the file is
recognisable later. Punctuation, whitespace and special characters are folded to
underscores so the name is safe on every filesystem.

Optionally a stem carries a suffix built from the voice used and the audio
duration (``h``/``m``/``s`` — never ``:``, which is illegal in filenames).
"""

from __future__ import annotations

import re
import unicodedata

# One or more non-word characters (punctuation, whitespace, symbols) collapse to
# a single underscore. ``\w`` keeps Unicode letters/digits, so Vietnamese words
# survive intact.
_NON_WORD = re.compile(r"[^\w]+", re.UNICODE)


def _slug(text: str, limit: int | None = None) -> str:
    # NFC keeps precomposed Vietnamese letters as single word characters.
    collapsed = unicodedata.normalize("NFC", " ".join(str(text).split()))
    if limit is not None:
        collapsed = collapsed[: max(1, int(limit))]
    return _NON_WORD.sub("_", collapsed).strip("_")


def default_stem_from_text(text: str, *, limit: int = 20) -> str:
    """Return a slug built from the first ``limit`` characters of ``text``.

    Returns an empty string when there is nothing usable; the caller decides the
    fallback (Core falls back to ``"output"``).
    """
    if not text:
        return ""
    return _slug(text, limit)


def slug_component(text: str) -> str:
    """Fold an arbitrary label (e.g. a voice name) into a filename-safe token."""
    return _slug(text)


def format_duration_stem(seconds: float | int | None) -> str:
    """Format a duration for a filename: ``01m23s`` or ``1h02m03s`` (no colons)."""
    total = max(0, int(round(float(seconds or 0))))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}h{minutes:02d}m{secs:02d}s"
    return f"{minutes:02d}m{secs:02d}s"


def compose_stem(
    base_stem: str,
    *,
    voice_label: str = "",
    duration_seconds: float | int | None = None,
) -> str:
    """Join a base stem with optional voice + duration suffixes.

    Empty parts are skipped, so a missing voice label just yields
    ``base_duration`` and no arguments yields ``base_stem`` unchanged.
    """
    parts = [base_stem]
    voice = slug_component(voice_label)
    if voice:
        parts.append(voice)
    if duration_seconds is not None:
        parts.append(format_duration_stem(duration_seconds))
    return "_".join(part for part in parts if part)
