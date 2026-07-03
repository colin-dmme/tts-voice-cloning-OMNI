from __future__ import annotations

from pathlib import Path
from tkinter import TclError

from omni_tts_ui_tkinter.path_intake import parse_path_text


try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
except Exception:  # pragma: no cover - optional UI dependency fallback
    DND_FILES = None
    TkinterDnD = None


def create_root(title: str):
    if TkinterDnD is not None:
        root = TkinterDnD.Tk()
    else:
        import tkinter as tk

        root = tk.Tk()
    root.title(title)
    return root


def enable_file_drop(widget, callback) -> bool:
    if DND_FILES is None:
        return False
    try:
        widget.drop_target_register(DND_FILES)
        widget.dnd_bind("<<Drop>>", lambda event: callback(parse_drop_files(event.data, widget)))
    except TclError:
        return False
    return True


def parse_drop_files(data: str, widget) -> list[Path]:
    return parse_path_text(data, widget.tk.splitlist)
