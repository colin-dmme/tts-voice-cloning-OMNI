from __future__ import annotations

import argparse
import os
import shutil
import subprocess
from pathlib import Path

UPSTREAM_REPO = "https://github.com/zeroweight-ai/ZeroTTS.git"
UPSTREAM_REVISION = "9d85578bee9321d6ef8305a4d454baf33e3fe861"


def _run(command: list[str], *, cwd: Path | None = None) -> None:
    print(" ".join(command), flush=True)
    completed = subprocess.run(command, cwd=str(cwd) if cwd else None, check=False)
    if completed.returncode != 0:
        raise SystemExit(completed.returncode)


def _prepare_source(source: Path) -> None:
    if not (source / ".git").exists():
        source.parent.mkdir(parents=True, exist_ok=True)
        _run(["git", "clone", "--filter=blob:none", UPSTREAM_REPO, str(source)])
    _run(["git", "fetch", "origin", UPSTREAM_REVISION], cwd=source)
    _run(["git", "checkout", "--detach", UPSTREAM_REVISION], cwd=source)
    _run(["git", "submodule", "update", "--init", "cpp/vendor-ggml"], cwd=source)


def _built_executable(build_dir: Path) -> Path:
    name = (
        "omni-zerotts-gguf-server.exe"
        if os.name == "nt"
        else "omni-zerotts-gguf-server"
    )
    candidates = [build_dir / "Release" / name, build_dir / name]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(f"Không tìm thấy {name} sau khi build.")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--clean", action="store_true")
    args = parser.parse_args()

    missing = [name for name in ("git", "cmake") if shutil.which(name) is None]
    if missing:
        raise SystemExit("Thiếu công cụ build ZeroTTS GGUF: " + ", ".join(missing))

    worker_dir = Path(__file__).resolve().parent
    source = worker_dir / "vendor" / "ZeroTTS"
    build_dir = worker_dir / "native" / "build"
    runtime_dir = worker_dir / "native" / "bin"
    if args.clean and build_dir.exists():
        shutil.rmtree(build_dir)

    _prepare_source(source)
    configure = [
        "cmake",
        "-S",
        str(worker_dir / "native"),
        "-B",
        str(build_dir),
        f"-DZEROTTS_SOURCE_DIR={source.as_posix()}",
        "-DCMAKE_BUILD_TYPE=Release",
    ]
    _run(configure)
    _run(["cmake", "--build", str(build_dir), "--config", "Release", "--parallel"])

    runtime_dir.mkdir(parents=True, exist_ok=True)
    executable = _built_executable(build_dir)
    destination = runtime_dir / executable.name
    shutil.copy2(executable, destination)
    print(f"Native runtime ready: {destination}")


if __name__ == "__main__":
    main()
