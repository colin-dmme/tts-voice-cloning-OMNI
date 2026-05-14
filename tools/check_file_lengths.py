from __future__ import annotations

from pathlib import Path


MAX_LINES = 700
ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIRS = [ROOT / "src", ROOT / "tools"]


def main() -> int:
    too_long: list[tuple[Path, int]] = []
    for source_dir in SOURCE_DIRS:
        for path in source_dir.rglob("*.py"):
            line_count = len(path.read_text(encoding="utf-8").splitlines())
            if line_count > MAX_LINES:
                too_long.append((path, line_count))
    if not too_long:
        print(f"OK: no Python file exceeds {MAX_LINES} lines.")
        return 0
    for path, line_count in too_long:
        print(f"{path}: {line_count} lines")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
