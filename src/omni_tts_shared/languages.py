from __future__ import annotations


LANGUAGE_LABELS = {
    "auto": "Tự động",
    "vi": "Tiếng Việt",
    "en": "English",
    "zh": "Chinese",
    "ja": "Japanese",
    "ko": "Korean",
    "de": "German",
    "fr": "French",
    "ru": "Russian",
    "pt": "Portuguese",
    "es": "Spanish",
    "it": "Italian",
}
LANGUAGE_CODES = {label: code for code, label in LANGUAGE_LABELS.items()}


def language_label(code: str) -> str:
    return LANGUAGE_LABELS.get(code, code)


def language_choices(codes: list[str]) -> list[str]:
    return [language_label(code) for code in codes]
