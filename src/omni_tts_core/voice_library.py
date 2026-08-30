"""Unified, UI-agnostic view over selectable voices (clone profiles + designs).

All search / filter / grouping logic for the voice pickers lives here so no GUI
re-implements it. A GUI binds widgets to these pure functions and the
``VoiceItem`` rows they return.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from omni_tts_shared.schemas import DesignedVoice, VoiceProfile

VoiceKind = Literal["clone", "design"]


@dataclass(frozen=True)
class VoiceItem:
    """One selectable voice, regardless of whether it clones or is designed."""

    item_id: str
    name: str
    kind: VoiceKind
    project: str = ""
    tags: tuple[str, ...] = ()
    language: str = ""
    subtitle: str = ""  # short human-readable descriptor for lists

    @property
    def kind_label(self) -> str:
        return "Clone" if self.kind == "clone" else "Thiết kế"


def build_voice_items(
    profiles: list[VoiceProfile],
    designs: list[DesignedVoice],
) -> list[VoiceItem]:
    items: list[VoiceItem] = []
    for profile in profiles:
        duration = f"{profile.duration_seconds:.1f}s" if profile.duration_seconds else ""
        subtitle = " · ".join(part for part in (profile.language, duration) if part)
        items.append(
            VoiceItem(
                item_id=profile.profile_id,
                name=profile.name,
                kind="clone",
                project=profile.project,
                tags=tuple(profile.tags),
                language=profile.language,
                subtitle=subtitle,
            )
        )
    for design in designs:
        items.append(
            VoiceItem(
                item_id=design.designed_voice_id,
                name=design.name,
                kind="design",
                project=design.project,
                tags=tuple(design.tags),
                language=design.language,
                subtitle=design.instruct[:60],
            )
        )
    return items


def filter_voice_items(
    items: list[VoiceItem],
    *,
    query: str = "",
    project: str | None = None,
    tag: str | None = None,
    kinds: tuple[VoiceKind, ...] | None = None,
) -> list[VoiceItem]:
    """Filter by allowed kinds, project, tag, and a free-text query.

    ``kinds`` restricts to what a provider supports (None = all). The query
    matches name, project, tags, and subtitle, case-insensitively.
    """
    needle = query.strip().casefold()
    result: list[VoiceItem] = []
    for item in items:
        if kinds is not None and item.kind not in kinds:
            continue
        if project is not None and item.project != project:
            continue
        if tag is not None and tag not in item.tags:
            continue
        if needle and not _matches(item, needle):
            continue
        result.append(item)
    return result


def _matches(item: VoiceItem, needle: str) -> bool:
    haystacks = (item.name, item.project, item.subtitle, " ".join(item.tags))
    return any(needle in part.casefold() for part in haystacks if part)


def list_projects(items: list[VoiceItem]) -> list[str]:
    return sorted({item.project for item in items if item.project}, key=str.casefold)


def list_tags(items: list[VoiceItem]) -> list[str]:
    tags: set[str] = set()
    for item in items:
        tags.update(item.tags)
    return sorted(tags, key=str.casefold)


def group_by_project(items: list[VoiceItem]) -> dict[str, list[VoiceItem]]:
    """Group items by project name; the empty project sorts under a shared key."""
    groups: dict[str, list[VoiceItem]] = {}
    for item in items:
        key = item.project or "(Không thuộc dự án)"
        groups.setdefault(key, []).append(item)
    return {key: groups[key] for key in sorted(groups, key=str.casefold)}
