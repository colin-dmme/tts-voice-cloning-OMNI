from __future__ import annotations


LANGUAGE_LABELS = {
    "auto": "Tự động",
    "ar": "Arabic",
    "bg": "Bulgarian",
    "cs": "Czech",
    "da": "Danish",
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
    "el": "Greek",
    "et": "Estonian",
    "fi": "Finnish",
    "hi": "Hindi",
    "hr": "Croatian",
    "hu": "Hungarian",
    "id": "Indonesian",
    "lt": "Lithuanian",
    "lv": "Latvian",
    "nl": "Dutch",
    "pl": "Polish",
    "ro": "Romanian",
    "sk": "Slovak",
    "sl": "Slovenian",
    "sv": "Swedish",
    "tr": "Turkish",
    "uk": "Ukrainian",
}
LANGUAGE_CODES = {label: code for code, label in LANGUAGE_LABELS.items()}


def language_label(code: str) -> str:
    return LANGUAGE_LABELS.get(code, code)


def language_choices(codes: list[str]) -> list[str]:
    return [language_label(code) for code in codes]
