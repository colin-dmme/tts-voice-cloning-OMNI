"""Diacritic-insensitive text matching for search boxes.

Vietnamese names carry tone marks, so a plain ``casefold()`` comparison makes
typing "ngoc" miss "Ngọc". Every GUI search box folds both sides through
``normalize_search`` so accents and letter case stop mattering.
"""

from __future__ import annotations

import unicodedata

# Đ/đ is a distinct Vietnamese letter, not a base letter plus a combining mark,
# so NFD decomposition leaves it untouched — map it explicitly.
_LETTER_MAP = str.maketrans({"đ": "d", "Đ": "d", "ð": "d"})


def normalize_search(value: str) -> str:
    """Lowercase and strip diacritics so 'Ngọc' matches a typed 'ngoc'."""
    text = str(value or "").translate(_LETTER_MAP)
    decomposed = unicodedata.normalize("NFD", text)
    stripped = "".join(char for char in decomposed if not unicodedata.combining(char))
    return unicodedata.normalize("NFC", stripped).casefold().strip()


def matches_search(haystack: str, needle: str) -> bool:
    """True when `needle` is empty or appears in `haystack`, ignoring accents."""
    normalized_needle = normalize_search(needle)
    if not normalized_needle:
        return True
    return normalized_needle in normalize_search(haystack)
