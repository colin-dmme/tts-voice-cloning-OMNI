from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Protocol

ProviderSettingKind = Literal["boolean", "integer", "number", "choice"]


@dataclass(frozen=True)
class ProviderSettingSpec:
    """Declarative provider option shared by Core and every GUI."""

    key: str
    label: str
    kind: ProviderSettingKind
    default: bool | int | float | str
    tooltip: str
    minimum: float | None = None
    maximum: float | None = None
    step: float | None = None
    decimals: int = 0
    choices: tuple[tuple[str, str], ...] = ()


class _SettingsDescriptor(Protocol):
    label: str
    settings: tuple[ProviderSettingSpec, ...]


def provider_settings_for_model(
    descriptor: _SettingsDescriptor,
    runtime: dict[str, Any] | None,
) -> tuple[ProviderSettingSpec, ...]:
    """Return only settings the selected model runtime can implement."""

    blocked = {
        str(key).strip()
        for key in ((runtime or {}).get("unsupported_provider_settings") or [])
        if str(key).strip()
    }
    return tuple(
        setting for setting in descriptor.settings if setting.key not in blocked
    )


def normalize_provider_options(
    descriptor: _SettingsDescriptor,
    raw: dict[str, Any] | None,
    *,
    settings: tuple[ProviderSettingSpec, ...] | None = None,
) -> dict[str, bool | int | float | str]:
    """Validate an option bag using provider metadata, without provider branches."""

    supplied = dict(raw or {})
    active_settings = descriptor.settings if settings is None else settings
    known = {setting.key for setting in active_settings}
    unknown = sorted(set(supplied) - known)
    if unknown:
        raise ValueError(f"{descriptor.label} không có tuỳ chọn: {', '.join(unknown)}.")
    normalized: dict[str, bool | int | float | str] = {}
    for setting in active_settings:
        value = supplied.get(setting.key, setting.default)
        if setting.kind == "boolean":
            if not isinstance(value, bool):
                raise ValueError(f"{setting.label} phải là bật hoặc tắt.")
            normalized[setting.key] = value
            continue
        if setting.kind in {"integer", "number"}:
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"{setting.label} phải là một con số.")
            number = float(value)
            if setting.minimum is not None and number < setting.minimum:
                raise ValueError(
                    f"{setting.label} không được nhỏ hơn {setting.minimum:g}."
                )
            if setting.maximum is not None and number > setting.maximum:
                raise ValueError(
                    f"{setting.label} không được lớn hơn {setting.maximum:g}."
                )
            normalized[setting.key] = (
                int(number) if setting.kind == "integer" else number
            )
            continue
        allowed = {choice_value for _label, choice_value in setting.choices}
        text = str(value)
        if text not in allowed:
            raise ValueError(f"Giá trị của {setting.label} không hợp lệ.")
        normalized[setting.key] = text
    return normalized
