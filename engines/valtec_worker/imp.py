from __future__ import annotations

import importlib.util
from pathlib import Path


def find_module(name: str, path=None):
    spec = importlib.util.find_spec(name, path)
    if spec is None:
        raise ImportError(f"No module named {name!r}")
    if spec.submodule_search_locations:
        pathname = str(Path(next(iter(spec.submodule_search_locations))))
    else:
        pathname = spec.origin or ""
    return None, pathname, None
