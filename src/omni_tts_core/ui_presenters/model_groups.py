"""Group the model catalog by provider so GUIs can offer provider-first selection.

The catalog has 40+ entries; picking a provider first keeps the model list short.
Both the tkinter and Qt GUIs read these helpers so the grouping/labels stay in one
place instead of being duplicated per GUI.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from omni_tts_core.model_registry import ModelSpec
from omni_tts_core.provider_registry import PROVIDERS, provider_descriptor
from omni_tts_core.ui_presenters.labels import model_choice_label

ALL_PROVIDERS = "all"
ALL_PROVIDERS_LABEL = "Tất cả"

# Declaration order in the provider registry drives display order everywhere.
_PROVIDER_ORDER = {provider_id: index for index, provider_id in enumerate(PROVIDERS)}


def _provider_of(item: object) -> str:
    return str(getattr(item, "provider", "") or "")


def _ordered_provider_ids(providers: Iterable[str]) -> list[str]:
    unique = list(dict.fromkeys(providers))
    known = [pid for pid in PROVIDERS if pid in unique]
    return known + [pid for pid in unique if pid not in PROVIDERS]


@dataclass(frozen=True)
class ProviderGroup:
    provider_id: str
    label: str
    models: tuple[tuple[str, str], ...]  # (display label, model_id)

    @property
    def count(self) -> int:
        return len(self.models)


def provider_label(provider_id: str) -> str:
    if provider_id == ALL_PROVIDERS:
        return ALL_PROVIDERS_LABEL
    descriptor = provider_descriptor(provider_id)
    return descriptor.label if descriptor else (provider_id or "Khác")


def group_models_by_provider(specs: Iterable[ModelSpec]) -> list[ProviderGroup]:
    """Group specs by provider, ordered by the provider registry declaration."""
    buckets: dict[str, list[tuple[str, str]]] = {}
    for spec in specs:
        buckets.setdefault(spec.provider, []).append(
            (model_choice_label(spec), spec.model_id)
        )
    return [
        ProviderGroup(pid, provider_label(pid), tuple(buckets[pid]))
        for pid in _ordered_provider_ids(buckets)
    ]


def provider_choices(items: Iterable[object], include_all: bool = True) -> list[tuple[str, str]]:
    """(label with count, provider_id) choices for a provider filter combo.

    Counts anything exposing ``.provider`` — model specs for the studio form,
    model statuses for the model-management table.
    """
    counts: dict[str, int] = {}
    for item in items:
        counts[_provider_of(item)] = counts.get(_provider_of(item), 0) + 1
    choices: list[tuple[str, str]] = []
    if include_all:
        choices.append((f"{ALL_PROVIDERS_LABEL} ({sum(counts.values())})", ALL_PROVIDERS))
    for provider_id in _ordered_provider_ids(counts):
        choices.append((f"{provider_label(provider_id)} ({counts[provider_id]})", provider_id))
    return choices


def filter_by_provider(items: Iterable[object], provider_id: str | None) -> list:
    """Keep only the items belonging to one provider (or everything)."""
    collected = list(items)
    if not provider_id or provider_id == ALL_PROVIDERS:
        return collected
    return [item for item in collected if _provider_of(item) == provider_id]


def sort_by_provider(items: Iterable[object]) -> list:
    """Group rows by provider (registry order), then by display name."""
    return sorted(items, key=provider_sort_key)


def provider_sort_key(item: object) -> tuple[int, str, str]:
    provider = _provider_of(item)
    order = _PROVIDER_ORDER.get(provider, len(PROVIDERS))
    return (order, provider, str(getattr(item, "display_name", "")).casefold())


def models_for_provider(
    specs: Iterable[ModelSpec],
    provider_id: str | None,
) -> list[tuple[str, str]]:
    """(display label, model_id) choices limited to one provider (or all)."""
    groups = group_models_by_provider(specs)
    if not provider_id or provider_id == ALL_PROVIDERS:
        return [model for group in groups for model in group.models]
    for group in groups:
        if group.provider_id == provider_id:
            return list(group.models)
    return []


def provider_of_model(specs: Iterable[ModelSpec], model_id: str | None) -> str:
    """Provider id owning a model, or ALL_PROVIDERS when unknown."""
    if not model_id:
        return ALL_PROVIDERS
    for spec in specs:
        if spec.model_id == model_id:
            return spec.provider
    return ALL_PROVIDERS
