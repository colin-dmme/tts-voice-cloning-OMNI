from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from omni_tts_core.paths import PROJECT_ROOT


USER_STATE_ROOT = "user_state"
SETTINGS_FILE = "settings.json"

PORTABLE_TKINTER_KEYS = {
    "language",
    "model_id",
    "voice_profile_id",
    "speaker_id",
    "speed",
    "pitch_shift",
    "emotion",
    "runtime_target",
    "codec_repo",
    "temperature",
    "top_k",
    "sentence_pause_ms",
    "max_chunk_chars",
    "overwrite",
    "split_output",
    "output_srt",
}


def export_user_state(project_root: Path | None = None) -> dict[str, Any]:
    """Copy portable profiles, samples, and shared UI settings into user_state/."""
    root = _root(project_root)
    state_root = root / USER_STATE_ROOT
    src_profiles = root / "voices" / "profiles"
    src_samples = root / "voices" / "samples"
    dst_profiles = state_root / "voices" / "profiles"
    dst_samples = state_root / "voices" / "samples"

    copied_profiles = _export_profiles(src_profiles, dst_profiles, root)
    copied_samples = _copy_files(src_samples, dst_samples, overwrite=True)
    settings = _export_settings(root / "config" / "ui_tkinter.json", state_root / SETTINGS_FILE)

    return {
        "profiles": copied_profiles,
        "samples": copied_samples,
        "settings_keys": sorted(settings),
        "state_root": str(state_root),
    }


def restore_user_state(
    project_root: Path | None = None,
    *,
    overwrite: bool = False,
    overwrite_settings: bool = False,
) -> dict[str, Any]:
    """Restore tracked user_state/ data into runtime folders before the app starts."""
    root = _root(project_root)
    state_root = root / USER_STATE_ROOT
    src_profiles = state_root / "voices" / "profiles"
    src_samples = state_root / "voices" / "samples"
    dst_profiles = root / "voices" / "profiles"
    dst_samples = root / "voices" / "samples"

    restored_samples = _copy_files(src_samples, dst_samples, overwrite=overwrite)
    restored_profiles = _restore_profiles(src_profiles, dst_profiles, root, overwrite=overwrite)
    restored_settings = _restore_settings(
        state_root / SETTINGS_FILE,
        root / "config" / "ui_tkinter.json",
        overwrite=overwrite_settings,
    )

    return {
        "profiles": restored_profiles,
        "samples": restored_samples,
        "settings_restored": restored_settings,
        "state_root": str(state_root),
    }


def _root(project_root: Path | None) -> Path:
    return Path(project_root).resolve() if project_root is not None else PROJECT_ROOT


def _copy_files(source_dir: Path, target_dir: Path, *, overwrite: bool) -> int:
    if not source_dir.exists():
        return 0
    target_dir.mkdir(parents=True, exist_ok=True)
    count = 0
    for source in sorted(source_dir.iterdir()):
        if not source.is_file():
            continue
        target = target_dir / source.name
        if target.exists() and not overwrite:
            continue
        shutil.copy2(source, target)
        count += 1
    return count


def _export_profiles(source_dir: Path, target_dir: Path, project_root: Path) -> int:
    if not source_dir.exists():
        return 0
    target_dir.mkdir(parents=True, exist_ok=True)
    count = 0
    for source in sorted(source_dir.glob("*.json")):
        data = _read_json(source)
        _portable_profile_paths(data, project_root)
        _write_json(target_dir / source.name, data)
        count += 1
    return count


def _restore_profiles(source_dir: Path, target_dir: Path, project_root: Path, *, overwrite: bool) -> int:
    if not source_dir.exists():
        return 0
    target_dir.mkdir(parents=True, exist_ok=True)
    count = 0
    for source in sorted(source_dir.glob("*.json")):
        target = target_dir / source.name
        if target.exists() and not overwrite:
            continue
        data = _read_json(source)
        _local_profile_paths(data, project_root)
        _write_json(target, data)
        count += 1
    return count


def _export_settings(source_path: Path, target_path: Path) -> dict[str, Any]:
    if not source_path.exists():
        return {}
    data = _read_json(source_path)
    shared = {key: data[key] for key in PORTABLE_TKINTER_KEYS if key in data}
    payload = {
        "schema_version": 1,
        "ui_tkinter": shared,
    }
    _write_json(target_path, payload)
    return shared


def _restore_settings(source_path: Path, target_path: Path, *, overwrite: bool) -> bool:
    if not source_path.exists():
        return False
    payload = _read_json(source_path)
    shared = payload.get("ui_tkinter", payload)
    if not isinstance(shared, dict):
        return False
    portable = {key: shared[key] for key in PORTABLE_TKINTER_KEYS if key in shared}
    if not portable:
        return False
    if target_path.exists() and not overwrite:
        return False

    current: dict[str, Any] = {}
    if target_path.exists():
        try:
            current = _read_json(target_path)
        except ValueError:
            current = {}
    current.update(portable)
    _write_json(target_path, current)
    return True


def _portable_profile_paths(data: dict[str, Any], project_root: Path) -> None:
    _rewrite_path_field(data, "audio_path", lambda value: _portable_path(value, project_root))
    for sample in _extra_samples(data):
        _rewrite_path_field(sample, "audio_path", lambda value: _portable_path(value, project_root))


def _local_profile_paths(data: dict[str, Any], project_root: Path) -> None:
    _rewrite_path_field(data, "audio_path", lambda value: _local_sample_path(value, project_root))
    for sample in _extra_samples(data):
        _rewrite_path_field(sample, "audio_path", lambda value: _local_sample_path(value, project_root))


def _extra_samples(data: dict[str, Any]) -> list[dict[str, Any]]:
    samples = data.get("extra_samples")
    if not isinstance(samples, list):
        return []
    return [sample for sample in samples if isinstance(sample, dict)]


def _rewrite_path_field(data: dict[str, Any], key: str, rewrite) -> None:
    value = str(data.get(key) or "").strip()
    if value:
        data[key] = rewrite(value)


def _portable_path(value: str, project_root: Path) -> str:
    path = Path(value)
    try:
        relative = path.resolve().relative_to(project_root)
        return relative.as_posix()
    except Exception:
        return f"voices/samples/{path.name}" if path.name else value


def _local_sample_path(value: str, project_root: Path) -> str:
    path = Path(value)
    if path.is_absolute():
        return str(path) if path.exists() else str(project_root / "voices" / "samples" / path.name)
    return str((project_root / path).resolve())


def _read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON: {path}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"JSON must be an object: {path}")
    return data


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
