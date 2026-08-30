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
    chunk_mode = _chunk_join_mode(values)
    chunk_ms = int(_value(values, "chunk_pause_ms"))
    chunk_crossfade_ms = int(_value(values, "chunk_crossfade_ms"))
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
    chunk_crossfade_effective = _seconds_text(chunk_crossfade_ms)
    chunk_summary = _chunk_summary(
        chunk_mode, chunk_effective, chunk_crossfade_effective
    )
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
            f"• Điểm nối chunk: {chunk_summary}"
        )
    else:
        section = (
            "KẾT QUẢ THỰC TẾ VỚI THIẾT LẬP HIỆN TẠI\n"
            "• Ngắt nghỉ theo dấu câu đang tắt.\n"
            f"• Dòng trống vẫn tạo nghỉ đoạn gốc {paragraph_effective}.\n"
            f"• Điểm nối chunk: {chunk_summary}"
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
        chunk=_chunk_detail(chunk_mode, chunk_effective, chunk_crossfade_effective),
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


def _chunk_join_mode(values: Mapping[str, Any]) -> str:
    mode = values.get("chunk_join_mode")
    if mode in {"auto", "crossfade", "direct", "silence"}:
        return str(mode)
    if "chunk_pause_ms" in values:
        return "crossfade" if int(values.get("chunk_pause_ms") or 0) == 0 else "silence"
    return "auto"


def _chunk_summary(mode: str, silence: str, crossfade: str) -> str:
    if mode == "crossfade":
        return f"crossfade {crossfade}, không chèn khoảng lặng."
    if mode == "direct":
        return "nối thẳng, không chèn khoảng lặng và không crossfade."
    if mode == "silence":
        return f"chèn khoảng lặng cố định {silence}."
    return "AUTO theo chính sách của provider; không áp một kiểu nối chung cho mọi model."


def _chunk_detail(mode: str, silence: str, crossfade: str) -> str:
    if mode == "crossfade":
        return (
            f"Thực tế: không chèn khoảng lặng tại điểm nối do Core tạo. App chồng "
            f"{crossfade} cuối chunk trước với đầu chunk sau; tổng thời lượng ngắn "
            "đi tương ứng."
        )
    if mode == "direct":
        return (
            "Thực tế: nối thẳng hai waveform tại điểm nối do Core tạo, không chèn "
            "khoảng lặng và không crossfade. Chế độ này chủ yếu dành cho kiểm thử."
        )
    if mode == "silence":
        return (
            f"Thực tế: chèn {silence} giữa mọi Core chunk. Đây là ghi đè cố định, "
            "không tự đổi theo loại dấu câu."
        )
    return (
        "Thực tế: Core đọc metadata của provider. VieNeu có thể tự chia/nối bên "
        "trong SDK; provider hỗ trợ dấu câu dùng nhịp theo dấu; provider chưa có "
        "bộ nối riêng dùng fallback an toàn."
    )


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
