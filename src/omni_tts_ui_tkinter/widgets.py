from __future__ import annotations

from datetime import datetime
import tkinter as tk
from tkinter import filedialog, ttk
from pathlib import Path


class ScrollableFrame(ttk.Frame):
    def __init__(self, parent, *, padding: int = 0) -> None:
        super().__init__(parent)
        self.canvas = tk.Canvas(self, borderwidth=0, highlightthickness=0)
        self.scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.content = ttk.Frame(self.canvas, padding=padding)
        self._window_id = self.canvas.create_window((0, 0), window=self.content, anchor="nw")

        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.scrollbar.grid(row=0, column=1, sticky="ns")

        self.content.bind("<Configure>", self._update_scroll_region)
        self.canvas.bind("<Configure>", self._sync_content_width)
        self.canvas.bind("<Enter>", self._bind_mousewheel)
        self.canvas.bind("<Leave>", self._unbind_mousewheel)
        self.content.bind("<Enter>", self._bind_mousewheel)
        self.content.bind("<Leave>", self._unbind_mousewheel)

    def _update_scroll_region(self, _event=None) -> None:
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _sync_content_width(self, event) -> None:
        self.canvas.itemconfigure(self._window_id, width=event.width)

    def _bind_mousewheel(self, _event=None) -> None:
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)

    def _unbind_mousewheel(self, _event=None) -> None:
        self.canvas.unbind_all("<MouseWheel>")

    def _on_mousewheel(self, event) -> None:
        self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")


def labeled_entry(parent, label: str, textvariable: tk.StringVar, width: int = 40):
    frame = ttk.Frame(parent)
    ttk.Label(frame, text=label).pack(anchor="w")
    ttk.Entry(frame, textvariable=textvariable, width=width).pack(fill="x")
    return frame


def labeled_spinbox(
    parent,
    label: str,
    variable: tk.Variable,
    from_: float,
    to: float,
    increment: float,
):
    frame = ttk.Frame(parent)
    ttk.Label(frame, text=label).pack(anchor="w")
    ttk.Spinbox(
        frame,
        textvariable=variable,
        from_=from_,
        to=to,
        increment=increment,
        width=12,
    ).pack(anchor="w")
    return frame


def browse_file(variable: tk.StringVar, title: str, filetypes: list[tuple[str, str]]) -> None:
    path = filedialog.askopenfilename(title=title, filetypes=filetypes)
    if path:
        variable.set(path)


def browse_directory(variable: tk.StringVar) -> None:
    path = filedialog.askdirectory(title="Chọn thư mục xuất")
    if path:
        variable.set(path)


def split_paths(value: str) -> list[Path]:
    return [Path(item.strip()) for item in value.splitlines() if item.strip()]


def set_text(widget: tk.Text, value: str) -> None:
    widget.delete("1.0", "end")
    widget.insert("1.0", value)


def append_log(widget: tk.Text, value: str) -> None:
    timestamp = datetime.now().strftime("%H:%M:%S")
    lines = value.rstrip().splitlines() or [""]
    widget.configure(state="normal")
    for line in lines:
        widget.insert("end", f"[{timestamp}] {line}\n")
    widget.see("end")
    widget.configure(state="disabled")


def clear_log(widget: tk.Text) -> None:
    widget.configure(state="normal")
    widget.delete("1.0", "end")
    widget.configure(state="disabled")
