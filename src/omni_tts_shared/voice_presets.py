from __future__ import annotations


NO_VOICE_PRESET_ID = ""
NO_VOICE_PRESET_LABEL = "Không dùng preset"

VALTEC_DEFAULT_SPEAKER = "NF"
VALTEC_SPEAKERS = {
    "NF": "NF - Nữ miền Bắc",
    "SF": "SF - Nữ miền Nam",
    "NM1": "NM1 - Nam miền Bắc 1",
    "SM": "SM - Nam miền Nam",
    "NM2": "NM2 - Nam miền Bắc 2",
}

VIENEU_STANDARD_DEFAULT_SPEAKER = "Ly"
VIENEU_STANDARD_SPEAKERS = {
    "Binh": "Thanh Bình - Nam miền Bắc",
    "Tuyen": "Phạm Tuyên - Nam miền Bắc",
    "Vinh": "Xuân Vĩnh - Nam miền Nam",
    "Doan": "Thục Đoan - Nữ miền Nam",
    "Ly": "Trúc Ly - Nữ miền Bắc",
    "Sơn": "Thái Sơn - Nam miền Nam",
    "Ngoc": "Bích Ngọc - Nữ miền Bắc",
}

VIENEU_TURBO_DEFAULT_SPEAKER = "Xuân Vĩnh (Nam - Miền Nam)"
VIENEU_TURBO_SPEAKERS = {
    "Bích Ngọc (Nữ - Miền Bắc)": "Bích Ngọc - Nữ miền Bắc",
    "Phạm Tuyên (Nam - Miền Bắc)": "Phạm Tuyên - Nam miền Bắc",
    "Thục Đoan (Nữ - Miền Nam)": "Thục Đoan - Nữ miền Nam",
    "Xuân Vĩnh (Nam - Miền Nam)": "Xuân Vĩnh - Nam miền Nam",
}

VOICE_PRESETS_BY_MODEL = {
    "valtec_vietnamese_zeroshot": VALTEC_SPEAKERS,
    "vieneu_v2_standard": VIENEU_STANDARD_SPEAKERS,
    "vieneu_v2_turbo": VIENEU_TURBO_SPEAKERS,
}

DEFAULT_PRESET_BY_MODEL = {
    "valtec_vietnamese_zeroshot": VALTEC_DEFAULT_SPEAKER,
    "vieneu_v2_standard": VIENEU_STANDARD_DEFAULT_SPEAKER,
    "vieneu_v2_turbo": VIENEU_TURBO_DEFAULT_SPEAKER,
}


def voice_preset_map(model_id: str) -> dict[str, str]:
    return VOICE_PRESETS_BY_MODEL.get(model_id, {})


def default_voice_preset_id(model_id: str) -> str | None:
    return DEFAULT_PRESET_BY_MODEL.get(model_id)


def has_voice_presets(model_id: str) -> bool:
    return model_id in VOICE_PRESETS_BY_MODEL


def voice_preset_choices(model_id: str, include_none: bool = True) -> list[tuple[str, str]]:
    presets = voice_preset_map(model_id)
    choices = [(label, preset_id) for preset_id, label in presets.items()]
    if include_none:
        return [(NO_VOICE_PRESET_LABEL, NO_VOICE_PRESET_ID), *choices]
    return choices


def voice_preset_label(model_id: str, preset_id: str | None) -> str:
    if not preset_id:
        return NO_VOICE_PRESET_LABEL
    presets = voice_preset_map(model_id)
    return presets.get(preset_id, NO_VOICE_PRESET_LABEL)


def valid_voice_preset_id(model_id: str, preset_id: str | None) -> str | None:
    if preset_id in voice_preset_map(model_id):
        return preset_id
    return None
