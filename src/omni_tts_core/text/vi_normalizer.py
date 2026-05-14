from __future__ import annotations

import re


_COMMON_REPLACEMENTS = {
    "TP.HCM": "Thành phố Hồ Chí Minh",
    "TP HCM": "Thành phố Hồ Chí Minh",
    "VN": "Việt Nam",
    "TTS": "text to speech",
    "AI": "A I",
    "%": " phần trăm",
}


def normalize_vietnamese_text(text: str) -> str:
    output = text.strip()
    for source, target in _COMMON_REPLACEMENTS.items():
        output = output.replace(source, target)
    output = _normalize_spaces_around_punctuation(output)
    return output


def _normalize_spaces_around_punctuation(text: str) -> str:
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)
    text = re.sub(r"([,.;:!?])([^\s])", r"\1 \2", text)
    return re.sub(r"\s+", " ", text).strip()
