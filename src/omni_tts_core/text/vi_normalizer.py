from __future__ import annotations

import unicodedata

from omni_tts_core.text.cleaner import clean_vietnamese_text


def normalize_vietnamese_text(text: str) -> str:
    text = unicodedata.normalize("NFC", text.strip())
    return clean_vietnamese_text(text)
