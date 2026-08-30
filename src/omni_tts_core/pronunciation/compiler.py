from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass

from omni_tts_core.pronunciation.store import PronunciationPresetStore
from omni_tts_shared.pronunciation import (
    PronunciationAnalysis,
    PronunciationConflict,
    PronunciationMatch,
    PronunciationPresetSnapshot,
    PronunciationReport,
    PronunciationRule,
    PronunciationSelection,
    PronunciationSnapshot,
)


_PROTECTED_PATTERN = re.compile(
    r"<\|[a-z][a-z0-9_]*:[a-z][a-z0-9_]*\|>|<[^>\n]+>",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class _Candidate:
    start: int
    end: int
    rule: PronunciationRule
    preset_id: str
    preset_name: str
    preset_order: int
    rule_order: int


def freeze_pronunciation_selection(
    store: PronunciationPresetStore,
    selection: PronunciationSelection | None,
) -> PronunciationSnapshot:
    selection = selection or PronunciationSelection()
    if not selection.enabled or not selection.preset_ids:
        return PronunciationSnapshot(enabled=False, content_hash=_content_hash([]))
    presets = [store.get(preset_id) for preset_id in selection.preset_ids]
    snapshots = [
        PronunciationPresetSnapshot(
            preset_id=preset.preset_id,
            name=preset.name,
            revision=preset.revision,
            rules=[rule.model_copy(deep=True) for rule in preset.rules],
        )
        for preset in presets
    ]
    return PronunciationSnapshot(
        enabled=True,
        presets=snapshots,
        content_hash=_content_hash(
            [preset.model_dump(mode="json") for preset in snapshots]
        ),
    )


def analyze_with_selection(
    store: PronunciationPresetStore,
    text: str,
    selection: PronunciationSelection | None,
) -> PronunciationAnalysis:
    return analyze_pronunciation(text, freeze_pronunciation_selection(store, selection))


def analyze_pronunciation(
    text: str,
    snapshot: PronunciationSnapshot | None,
) -> PronunciationAnalysis:
    snapshot = snapshot or PronunciationSnapshot()
    if not snapshot.enabled or not snapshot.presets or not text:
        return PronunciationAnalysis(
            original_text=text,
            speech_text=text,
            snapshot_hash=snapshot.content_hash,
            preset_ids=snapshot.preset_ids,
            preset_names=snapshot.preset_names,
        )

    protected = [(match.start(), match.end()) for match in _PROTECTED_PATTERN.finditer(text)]
    candidates: list[_Candidate] = []
    for preset_order, preset in enumerate(snapshot.presets):
        for rule_order, rule in enumerate(preset.rules):
            if not rule.enabled:
                continue
            pattern = _pattern_for(rule)
            for match in pattern.finditer(text):
                start, end = match.span()
                if _overlaps_protected(start, end, protected):
                    continue
                candidates.append(
                    _Candidate(
                        start=start,
                        end=end,
                        rule=rule,
                        preset_id=preset.preset_id,
                        preset_name=preset.name,
                        preset_order=preset_order,
                        rule_order=rule_order,
                    )
                )

    matches: list[PronunciationMatch] = []
    conflicts: list[PronunciationConflict] = []
    cursor = 0
    by_start: dict[int, list[_Candidate]] = {}
    for candidate in candidates:
        by_start.setdefault(candidate.start, []).append(candidate)
    for start in sorted(by_start):
        if start < cursor:
            continue
        group = by_start[start]
        winner = max(group, key=_candidate_priority)
        ignored = [item for item in group if item is not winner]
        if ignored:
            conflicts.append(
                PronunciationConflict(
                    start=winner.start,
                    end=winner.end,
                    winner_rule_id=winner.rule.rule_id,
                    ignored_rule_ids=[item.rule.rule_id for item in ignored],
                    message=(
                        f"“{text[winner.start:winner.end]}” khớp nhiều quy tắc; "
                        f"đang dùng “{winner.rule.spoken}”."
                    ),
                )
            )
        matches.append(
            PronunciationMatch(
                start=winner.start,
                end=winner.end,
                matched_text=text[winner.start:winner.end],
                written=winner.rule.written,
                spoken=winner.rule.spoken,
                rule_id=winner.rule.rule_id,
                preset_id=winner.preset_id,
                preset_name=winner.preset_name,
            )
        )
        cursor = winner.end

    pieces: list[str] = []
    cursor = 0
    for match in matches:
        pieces.append(text[cursor:match.start])
        pieces.append(match.spoken)
        cursor = match.end
    pieces.append(text[cursor:])
    speech_text = "".join(pieces)
    return PronunciationAnalysis(
        original_text=text,
        speech_text=speech_text,
        snapshot_hash=snapshot.content_hash,
        preset_ids=snapshot.preset_ids,
        preset_names=snapshot.preset_names,
        matches=matches,
        conflicts=conflicts,
        term_count=len({(match.preset_id, match.rule_id) for match in matches}),
        match_count=len(matches),
        conflict_count=len(conflicts),
    )


def build_pronunciation_report(analysis: PronunciationAnalysis) -> PronunciationReport:
    return PronunciationReport(
        snapshot_hash=analysis.snapshot_hash,
        preset_ids=analysis.preset_ids,
        preset_names=analysis.preset_names,
        original_sha256=hashlib.sha256(analysis.original_text.encode("utf-8")).hexdigest(),
        speech_sha256=hashlib.sha256(analysis.speech_text.encode("utf-8")).hexdigest(),
        term_count=analysis.term_count,
        match_count=analysis.match_count,
        conflict_count=analysis.conflict_count,
        matches=analysis.matches,
        conflicts=analysis.conflicts,
    )


def _pattern_for(rule: PronunciationRule) -> re.Pattern[str]:
    escaped = re.escape(rule.written)
    prefix = r"(?<!\w)" if _word_character(rule.written[0]) else ""
    suffix = r"(?!\w)" if _word_character(rule.written[-1]) else ""
    if rule.match_mode == "literal":
        prefix = suffix = ""
    flags = 0 if rule.case_sensitive else re.IGNORECASE
    return re.compile(prefix + escaped + suffix, flags)


def _candidate_priority(candidate: _Candidate) -> tuple[int, int, int, int]:
    return (
        candidate.end - candidate.start,
        candidate.preset_order,
        candidate.rule.priority,
        -candidate.rule_order,
    )


def _word_character(value: str) -> bool:
    return value == "_" or value.isalnum()


def _overlaps_protected(
    start: int, end: int, protected: list[tuple[int, int]]
) -> bool:
    return any(start < protected_end and end > protected_start for protected_start, protected_end in protected)


def _content_hash(payload) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()