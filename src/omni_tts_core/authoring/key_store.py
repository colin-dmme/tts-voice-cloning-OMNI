from __future__ import annotations

import hashlib
import json
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from omni_tts_core.paths import project_path


def classify_provider_error(message: str) -> str:
    """Classify an API failure without punishing a good key for bad config."""

    value = message.lower()
    if any(
        marker in value
        for marker in ("404", "not found", "not_found", "not supported", "listmodels")
    ):
        return "config_error"
    if any(
        marker in value
        for marker in ("429", "quota", "resource_exhausted", "too many", "rate limit")
    ):
        return "quota_exceeded"
    if any(
        marker in value
        for marker in (
            "401",
            "403",
            "invalid api",
            "api_key",
            "authentication",
            "permission",
            "unauthenticated",
            "revoked",
            "expired",
        )
    ):
        return "invalid"
    if any(
        marker in value
        for marker in (
            "500",
            "502",
            "503",
            "504",
            "unavailable",
            "overloaded",
            "high demand",
            "temporarily",
            "timeout",
            "timed out",
        )
    ):
        return "server_busy"
    return "request_error"


@dataclass(frozen=True)
class KeyImportReport:
    provider_id: str
    added: int
    duplicates: int
    skipped: int
    source_count: int


class AuthoringKeyStore:
    """Thread-safe API-key pool kept separate from TTS provider settings."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or project_path("config/authoring_ai_keys.json")
        self._lock = threading.RLock()
        self._data: dict[str, Any] = {"schema_version": 1, "providers": {}}
        self._indices: dict[str, int] = {}
        self._in_use: dict[str, set[str]] = {}
        self.reload()

    def reload(self) -> None:
        with self._lock:
            if self.path.exists():
                try:
                    payload = json.loads(self.path.read_text(encoding="utf-8"))
                    self._data = self._normalize_payload(payload)
                except Exception:
                    self._data = {"schema_version": 1, "providers": {}}
            else:
                self._data = {"schema_version": 1, "providers": {}}
            # Rate limits are transient; only explicit inactive keys stay off.
            for pool in self._data["providers"].values():
                for key in pool.get("keys", []):
                    if key.get("status") == "quota_exceeded":
                        key["status"] = "active"
            self._indices.clear()
            self._in_use.clear()

    def provider_ids(self) -> list[str]:
        with self._lock:
            return sorted(self._data["providers"])

    def all_keys(self, provider_id: str) -> list[dict[str, str]]:
        with self._lock:
            keys = self._pool(provider_id).get("keys", [])
            return [dict(item) for item in keys]

    def safe_keys(self, provider_id: str) -> list[dict[str, str]]:
        return [
            {
                "name": item.get("name", ""),
                "masked": _mask_key(item.get("key", "")),
                "status": item.get("status", "active"),
            }
            for item in self.all_keys(provider_id)
        ]

    def active_key_count(self, provider_id: str) -> int:
        return sum(
            item.get("status", "active") == "active"
            for item in self.all_keys(provider_id)
        )

    def models(self, provider_id: str) -> list[str]:
        with self._lock:
            return list(self._pool(provider_id).get("models", []))

    def set_models(self, provider_id: str, models: list[str]) -> None:
        with self._lock:
            pool = self._pool(provider_id)
            pool["models"] = list(
                dict.fromkeys(model.strip() for model in models if model.strip())
            )
            self._save_unlocked()

    def get_next_key(self, provider_id: str) -> tuple[str, str] | None:
        with self._lock:
            keys = [
                item
                for item in self._pool(provider_id).get("keys", [])
                if item.get("status", "active") == "active"
            ]
            if not keys:
                return None
            in_use = self._in_use.setdefault(provider_id, set())
            available = [item for item in keys if item.get("name", "") not in in_use]
            choices = available or keys
            index = self._indices.get(provider_id, 0) % len(choices)
            item = choices[index]
            self._indices[provider_id] = index + 1
            name = item.get("name", "")
            in_use.add(name)
            return name, item.get("key", "")

    def release_key(self, provider_id: str, name: str) -> None:
        with self._lock:
            self._in_use.setdefault(provider_id, set()).discard(name)

    def mark_key_error(self, provider_id: str, name: str, message: str) -> str:
        category = classify_provider_error(message)
        with self._lock:
            self.release_key(provider_id, name)
            if category not in {"invalid", "quota_exceeded"}:
                return category
            for item in self._pool(provider_id).get("keys", []):
                if item.get("name") == name:
                    item["status"] = category
                    break
            self._save_unlocked()
        return category

    def add_key(
        self,
        provider_id: str,
        name: str,
        key_value: str,
        *,
        status: str = "active",
    ) -> bool:
        clean_name = name.strip()
        clean_key = key_value.strip()
        if not clean_name or not clean_key:
            return False
        fingerprint = _fingerprint(clean_key)
        with self._lock:
            keys = self._pool(provider_id).setdefault("keys", [])
            if any(
                item.get("name") == clean_name
                or _fingerprint(item.get("key", "")) == fingerprint
                for item in keys
            ):
                return False
            keys.append(
                {"name": clean_name, "key": clean_key, "status": status or "active"}
            )
            self._save_unlocked()
        return True

    def update_key(
        self,
        provider_id: str,
        old_name: str,
        new_name: str,
        key_value: str,
    ) -> bool:
        clean_name = new_name.strip()
        clean_key = key_value.strip()
        if not clean_name or not clean_key:
            return False
        with self._lock:
            keys = self._pool(provider_id).get("keys", [])
            target = next((item for item in keys if item.get("name") == old_name), None)
            if target is None:
                return False
            if any(
                item is not target
                and (
                    item.get("name") == clean_name
                    or _fingerprint(item.get("key", "")) == _fingerprint(clean_key)
                )
                for item in keys
            ):
                return False
            target["name"] = clean_name
            target["key"] = clean_key
            self._save_unlocked()
        return True

    def remove_key(self, provider_id: str, name: str) -> bool:
        with self._lock:
            pool = self._pool(provider_id)
            keys = pool.get("keys", [])
            remaining = [item for item in keys if item.get("name") != name]
            if len(remaining) == len(keys):
                return False
            pool["keys"] = remaining
            self._save_unlocked()
            return True

    def reset_key_status(self, provider_id: str, name: str) -> bool:
        with self._lock:
            for item in self._pool(provider_id).get("keys", []):
                if item.get("name") == name:
                    item["status"] = "active"
                    self.release_key(provider_id, name)
                    self._save_unlocked()
                    return True
        return False

    def import_file(
        self,
        source_path: Path,
        *,
        provider_id: str = "gemini",
    ) -> KeyImportReport:
        payload = json.loads(source_path.read_text(encoding="utf-8"))
        source_pool = _external_provider_pool(payload, provider_id)
        source_keys = list(source_pool.get("keys", []))
        added = duplicates = skipped = 0
        for item in source_keys:
            name = str(item.get("name", "")).strip()
            value = str(item.get("key", "")).strip()
            if not name or not value:
                skipped += 1
                continue
            status = str(item.get("status", "active") or "active")
            if status == "quota_exceeded":
                status = "active"
            if self.add_key(provider_id, name, value, status=status):
                added += 1
            else:
                duplicates += 1
        imported_models = [
            str(model).strip()
            for model in source_pool.get("models", [])
            if str(model).strip()
        ]
        if imported_models:
            self.set_models(
                provider_id,
                [*self.models(provider_id), *imported_models],
            )
        return KeyImportReport(
            provider_id=provider_id,
            added=added,
            duplicates=duplicates,
            skipped=skipped,
            source_count=len(source_keys),
        )

    def _pool(self, provider_id: str) -> dict[str, Any]:
        return self._data["providers"].setdefault(
            provider_id,
            {"keys": [], "models": []},
        )

    def _save_unlocked(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(self._data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temporary.replace(self.path)

    @staticmethod
    def _normalize_payload(payload: dict[str, Any]) -> dict[str, Any]:
        if isinstance(payload.get("providers"), dict):
            return {
                "schema_version": int(payload.get("schema_version", 1) or 1),
                "providers": payload["providers"],
            }
        providers = {
            key: value
            for key, value in payload.items()
            if isinstance(value, dict) and isinstance(value.get("keys"), list)
        }
        return {"schema_version": 1, "providers": providers}


def _external_provider_pool(payload: dict[str, Any], provider_id: str) -> dict[str, Any]:
    providers = payload.get("providers")
    if isinstance(providers, dict):
        pool = providers.get(provider_id)
    else:
        pool = payload.get(provider_id)
    if not isinstance(pool, dict):
        raise ValueError(f"File không có key pool cho provider '{provider_id}'.")
    return pool


def _fingerprint(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _mask_key(value: str) -> str:
    if len(value) <= 8:
        return "•" * len(value)
    return f"{value[:4]}…{value[-4:]}"
