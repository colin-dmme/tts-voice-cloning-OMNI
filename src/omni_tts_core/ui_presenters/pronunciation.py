from __future__ import annotations

from omni_tts_shared.pronunciation import (
    PronunciationAnalysis,
    PronunciationPreset,
    PronunciationReport,
)


def preset_label(preset: PronunciationPreset) -> str:
    suffix = f" · {preset.project}" if preset.project else ""
    return f"{preset.name}{suffix} ({len(preset.rules)} từ){'' if preset.rules else ' · trống'}"


def analysis_summary(analysis: PronunciationAnalysis) -> str:
    if not analysis.preset_ids:
        return "Không dùng preset cách đọc."
    names = ", ".join(analysis.preset_names)
    if not analysis.matches:
        return f"{names} · không có từ nào được áp dụng."
    conflict = f" · {analysis.conflict_count} xung đột" if analysis.conflict_count else ""
    return (
        f"{names} · {analysis.term_count} từ khác nhau · "
        f"{analysis.match_count} lần áp dụng{conflict}"
    )


def analysis_details(
    analysis: PronunciationAnalysis | PronunciationReport, *, limit: int = 8
) -> str:
    counts: dict[tuple[str, str], int] = {}
    for match in analysis.matches:
        key = (match.written, match.spoken)
        counts[key] = counts.get(key, 0) + 1
    parts = [
        f"{written} → {spoken} ×{count}"
        for (written, spoken), count in list(counts.items())[: max(1, limit)]
    ]
    remaining = len(counts) - len(parts)
    if remaining > 0:
        parts.append(f"+{remaining} từ khác")
    return " | ".join(parts)