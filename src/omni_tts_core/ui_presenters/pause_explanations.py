"""Dynamic, user-facing explanations of effective pause behavior."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from omni_tts_core.ui_presenters.settings_state import DEFAULT_GENERATION_PREFERENCES


@dataclass(frozen=True)
class PauseExplanation:
    section: str
    sentence: str
    comma: str
    clause: str
    ellipsis: str
    chunk: str
    paragraph: str


def build_pause_explanation(values: Mapping[str, Any]) -> PauseExplanation:
    active = bool(_value(values, "punctuation_pause_enabled"))
    sentence_random = bool(_value(values, "sentence_pause_random_enabled"))
    sentence_fixed = int(_value(values, "sentence_pause_ms"))
    sentence_min = int(_value(values, "sentence_pause_min_ms"))
    sentence_max = int(_value(values, "sentence_pause_max_ms"))
    chunk_ms = int(_value(values, "chunk_pause_ms"))
    paragraph_random = bool(_value(values, "paragraph_pause_random_enabled"))
    paragraph_ms = int(_value(values, "paragraph_pause_ms"))
    paragraph_min = int(_value(values, "paragraph_pause_min_ms"))
    paragraph_max = int(_value(values, "paragraph_pause_max_ms"))

    sentence_effective = (
        _range_text(sentence_min, sentence_max)
        if sentence_random
        else _seconds_text(sentence_fixed)
    )
    paragraph_effective = (
        _range_text(paragraph_min, paragraph_max)
        if paragraph_random
        else _seconds_text(paragraph_ms)
    )
    chunk_effective = _seconds_text(chunk_ms)
    punctuation_effective = {
        "sentence": sentence_effective,
        "comma": _punctuation_value(values, "comma"),
        "clause": _punctuation_value(values, "clause"),
        "ellipsis": _punctuation_value(values, "ellipsis"),
    }
    sentence_bounds = (
        (sentence_min, sentence_max)
        if sentence_random
        else (sentence_fixed, sentence_fixed)
    )
    paragraph_bounds = (
        (paragraph_min, paragraph_max)
        if paragraph_random
        else (paragraph_ms, paragraph_ms)
    )
    stacked = _range_text(
        sentence_bounds[0] + paragraph_bounds[0],
        sentence_bounds[1] + paragraph_bounds[1],
    )

    if active:
        section = (
            "KẾT QUẢ THỰC TẾ VỚI THIẾT LẬP HIỆN TẠI\n"
            f"• Dấu cuối câu ở giữa cùng một đoạn: nghỉ {sentence_effective}.\n"
            f"• Dấu cuối câu ngay trước dòng trống: chỉ nghỉ đoạn gốc "
            f"{paragraph_effective}; KHÔNG cộng thành {stacked}.\n"
            f"• Ranh giới chunk: có dấu được hỗ trợ thì dùng mức của dấu; "
            f"không có dấu mới dùng {chunk_effective}. Hai mức không cộng dồn."
        )
    else:
        section = (
            "KẾT QUẢ THỰC TẾ VỚI THIẾT LẬP HIỆN TẠI\n"
            "• Ngắt nghỉ theo dấu câu đang tắt.\n"
            f"• Dòng trống vẫn tạo nghỉ đoạn gốc {paragraph_effective}.\n"
            f"• Ranh giới chunk dùng {chunk_effective}."
        )

    return PauseExplanation(
        section=section,
        sentence=_punctuation_detail(
            "dấu cuối câu", punctuation_effective["sentence"], paragraph_effective
        ),
        comma=_punctuation_detail(
            "dấu phẩy", punctuation_effective["comma"], paragraph_effective
        ),
        clause=_punctuation_detail(
            "dấu chấm phẩy hoặc dấu hai chấm",
            punctuation_effective["clause"],
            paragraph_effective,
        ),
        ellipsis=_punctuation_detail(
            "dấu ba chấm", punctuation_effective["ellipsis"], paragraph_effective
        ),
        chunk=(
            f"Thực tế: {chunk_effective} chỉ dùng khi Core chia chunk tại vị trí "
            "không có dấu được hỗ trợ. Nếu chunk kết thúc bằng dấu câu, mức của "
            "dấu thay thế mức chunk; không cộng hai giá trị."
        ),
        paragraph=(
            f"Thực tế: chèn {paragraph_effective} giữa hai đoạn được phân cách "
            "bằng dòng trống. Dù đoạn trước kết thúc bằng . ? !, khoảng nghỉ tại "
            f"ranh giới này vẫn chỉ là {paragraph_effective}, không cộng thêm nghỉ "
            "cuối câu."
            + (
                " Mỗi ranh giới đoạn lấy độc lập một giá trị mới trong khoảng Min–Max."
                if paragraph_random
                else ""
            )
        ),
    )


def _value(values: Mapping[str, Any], key: str) -> Any:
    return values.get(key, DEFAULT_GENERATION_PREFERENCES[key])


def _punctuation_value(values: Mapping[str, Any], prefix: str) -> str:
    if bool(_value(values, f"{prefix}_pause_random_enabled")):
        return _range_text(
            int(_value(values, f"{prefix}_pause_min_ms")),
            int(_value(values, f"{prefix}_pause_max_ms")),
        )
    return _seconds_text(int(_value(values, f"{prefix}_pause_ms")))


def _punctuation_detail(
    label: str, effective: str, paragraph_effective: str
) -> str:
    return (
        f"Thực tế: nghỉ {effective} sau {label} khi còn nội dung tiếp theo trong "
        "cùng một đoạn. Nếu dấu nằm cuối đoạn ngay trước dòng trống, Core bỏ mức "
        f"này và chỉ dùng nghỉ đoạn {paragraph_effective}."
    )


def _range_text(minimum_ms: int, maximum_ms: int) -> str:
    if minimum_ms == maximum_ms:
        return _seconds_text(minimum_ms)
    return f"{_seconds_number(minimum_ms)}–{_seconds_text(maximum_ms)}"


def _seconds_text(milliseconds: int) -> str:
    return f"{_seconds_number(milliseconds)} giây"


def _seconds_number(milliseconds: int) -> str:
    return f"{max(0, int(milliseconds)) / 1000:.3f}".rstrip("0").rstrip(".").replace(".", ",")
