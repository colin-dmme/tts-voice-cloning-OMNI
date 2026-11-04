"""One boundary's mutually exclusive silence/music settings for Tkinter."""

import tkinter as tk
from tkinter import ttk

from omni_tts_shared.epub import EpubBreakOptions


class EpubBreakFrame(ttk.LabelFrame):
    def __init__(self, parent, title, options):
        super().__init__(parent, text=title, padding=8)
        self.available = True
        self.on_change = None
        self.on_preview = None
        self.kind = tk.StringVar()
        self.duration_mode = tk.StringVar()
        self.seconds = tk.DoubleVar()
        self.fade_in = tk.DoubleVar()
        self.fade_out = tk.DoubleVar()
        self.kind_combo = ttk.Combobox(
            self,
            textvariable=self.kind,
            state="readonly",
            values=["Không nghỉ", "Khoảng lặng", "Nhạc"],
        )
        self.duration_combo = ttk.Combobox(
            self,
            textvariable=self.duration_mode,
            state="readonly",
            values=["Số giây cố định", "Phát trọn bản nhạc"],
        )
        self.kind_combo.grid(row=0, column=1, sticky="ew", pady=3)
        self.duration_combo.grid(row=1, column=1, sticky="ew", pady=3)
        self.labels = {}
        for row, text in [
            (0, "Loại nghỉ"),
            (1, "Độ dài nhạc"),
            (2, "Số giây cố định"),
            (3, "Fade-in (giây)"),
            (4, "Fade-out (giây)"),
        ]:
            self.labels[row] = ttk.Label(self, text=text)
            self.labels[row].grid(row=row, column=0, sticky="w", padx=(0, 8))
        self.spins = {}
        for row, var, maximum in [
            (2, self.seconds, 10),
            (3, self.fade_in, 2),
            (4, self.fade_out, 3),
        ]:
            spin = ttk.Spinbox(
                self, from_=0, to=maximum, increment=0.05, textvariable=var, width=10
            )
            spin.grid(row=row, column=1, sticky="ew", pady=3)
            self.spins[row] = spin
        self.columnconfigure(1, weight=1)
        self.preview = ttk.Button(
            self,
            text="Nghe thử nhịp này",
            command=lambda: self.on_preview() if self.on_preview else None,
        )
        self.preview.grid(row=5, column=0, columnspan=2, sticky="w", pady=4)
        self.note = ttk.Label(self, wraplength=390)
        self.note.grid(row=6, column=0, columnspan=2, sticky="w", pady=4)
        self.set_options(options)
        for var in (
            self.kind,
            self.duration_mode,
            self.seconds,
            self.fade_in,
            self.fade_out,
        ):
            var.trace_add("write", self._changed)

    def set_options(self, options):
        options = EpubBreakOptions.model_validate(options)
        self.kind.set(
            {"none": "Không nghỉ", "silence": "Khoảng lặng", "music": "Nhạc"}[
                options.mode
            ]
        )
        self.duration_mode.set(
            "Phát trọn bản nhạc"
            if options.duration_mode == "full_track"
            else "Số giây cố định"
        )
        self.seconds.set(options.duration_ms / 1000)
        self.fade_in.set(options.fade_in_ms / 1000)
        self.fade_out.set(options.fade_out_ms / 1000)
        self._sync()

    def set_available(self, available):
        self.available = available
        self._sync()

    def _sync(self):
        music = self.kind.get() == "Nhạc"
        full = music and self.duration_mode.get() == "Phát trọn bản nhạc"
        try:
            audible = music and (full or self.seconds.get() > 0)
        except tk.TclError:
            audible = False
        self.kind_combo.configure(state="readonly" if self.available else "disabled")
        self.duration_combo.configure(
            state="readonly" if self.available and music else "disabled"
        )
        for row, active in [
            (2, self.kind.get() != "Không nghỉ" and not full),
            (3, audible),
            (4, audible),
        ]:
            self.spins[row].configure(
                state="normal" if self.available and active else "disabled"
            )
            self.labels[row].configure(
                state="normal" if self.available and active else "disabled"
            )
        self.labels[1].configure(
            state="normal" if self.available and music else "disabled"
        )
        self.preview.configure(
            state="normal" if self.available and audible else "disabled"
        )
        text = (
            "Theo độ dài bản nhạc; số giây không áp dụng, không cộng thêm khoảng lặng. SRT tự cập nhật."
            if full
            else "Khoảng lặng theo số giây; không phát nhạc."
            if self.kind.get() == "Khoảng lặng"
            else "Không chèn khoảng nghỉ."
            if self.kind.get() == "Không nghỉ"
            else "Nhạc cắt/fade vừa số giây trên; fade dài tự co theo nhịp ngắn."
        )
        self.note.configure(text=text)

    def _changed(self, *_):
        self._sync()
        try:
            if self.on_change:
                self.on_change()
        except tk.TclError:
            pass  # A spinbox can be temporarily empty while typing.

    def options(self):
        return EpubBreakOptions(
            mode={"Không nghỉ": "none", "Khoảng lặng": "silence", "Nhạc": "music"}[
                self.kind.get()
            ],
            duration_mode="full_track"
            if self.duration_mode.get() == "Phát trọn bản nhạc"
            else "fit_pause",
            duration_ms=round(self.seconds.get() * 1000),
            fade_in_ms=round(self.fade_in.get() * 1000),
            fade_out_ms=round(self.fade_out.get() * 1000),
        )
