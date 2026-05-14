"""
Trim Settings Frame - Settings for audio trimming with dual padding.
Ported from Qwen3-TTS app.
"""

import tkinter as tk
from tkinter import ttk


class TrimSettingsFrame(ttk.LabelFrame):
    """Frame for audio trim settings."""

    on_setting_change = None

    def __init__(self, parent: tk.Widget, **kwargs):
        super().__init__(parent, text="✂️ Cài đặt Trim", **kwargs)
        self._suppress_callbacks = False
        self._setup_ui()
        self._connect_traces()

    def _setup_ui(self):
        self.columnconfigure(1, weight=1)
        row = 0

        # Detection header
        ttk.Label(self, text="Phát hiện khoảng lặng", font=("Segoe UI", 9, "bold")).grid(
            row=row, column=0, columnspan=2, sticky="w", padx=10, pady=(10, 5))
        row += 1

        # Threshold
        ttk.Label(self, text="Ngưỡng phát hiện (dB):").grid(row=row, column=0, sticky="w", padx=10, pady=5)
        tf = ttk.Frame(self)
        tf.grid(row=row, column=1, sticky="ew", padx=10, pady=5)
        self.threshold_var = tk.IntVar(value=-40)
        ttk.Spinbox(tf, from_=-60, to=-20, width=8, textvariable=self.threshold_var).pack(side="left")
        ttk.Label(tf, text="(Mặc định: -40dB)", foreground="gray").pack(side="left", padx=(10, 0))
        row += 1

        # Min silence
        ttk.Label(self, text="Độ dài tối thiểu (ms):").grid(row=row, column=0, sticky="w", padx=10, pady=5)
        mf = ttk.Frame(self)
        mf.grid(row=row, column=1, sticky="ew", padx=10, pady=5)
        self.min_silence_var = tk.IntVar(value=20)
        ttk.Spinbox(mf, from_=10, to=500, width=8, textvariable=self.min_silence_var).pack(side="left")
        ttk.Label(mf, text="(Mặc định: 20ms)", foreground="gray").pack(side="left", padx=(10, 0))
        row += 1

        ttk.Separator(self, orient="horizontal").grid(row=row, column=0, columnspan=2, sticky="ew", padx=10, pady=10)
        row += 1

        # Padding header
        ttk.Label(self, text="Khoảng lặng thêm vào (Padding)", font=("Segoe UI", 9, "bold")).grid(
            row=row, column=0, columnspan=2, sticky="w", padx=10, pady=(0, 5))
        row += 1

        # Padding 1
        ttk.Label(self, text="Padding #1 (ms):").grid(row=row, column=0, sticky="w", padx=10, pady=5)
        p1f = ttk.Frame(self)
        p1f.grid(row=row, column=1, sticky="ew", padx=10, pady=5)
        self.padding1_var = tk.IntVar(value=25)
        ttk.Spinbox(p1f, from_=0, to=500, width=8, textvariable=self.padding1_var).pack(side="left")
        ttk.Label(p1f, text="(Mặc định: 25ms - folder 1)", foreground="gray").pack(side="left", padx=(10, 0))
        row += 1

        # Padding 2
        ttk.Label(self, text="Padding #2 (ms):").grid(row=row, column=0, sticky="w", padx=10, pady=5)
        p2f = ttk.Frame(self)
        p2f.grid(row=row, column=1, sticky="ew", padx=10, pady=5)
        self.padding2_var = tk.IntVar(value=100)
        ttk.Spinbox(p2f, from_=0, to=500, width=8, textvariable=self.padding2_var).pack(side="left")
        ttk.Label(p2f, text="(Mặc định: 100ms - folder 2)", foreground="gray").pack(side="left", padx=(10, 0))
        row += 1

        # Enable checkbox
        self.enabled_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(self, text="Bật chức năng trim audio", variable=self.enabled_var).grid(
            row=row, column=0, columnspan=2, sticky="w", padx=10, pady=(10, 10))

    def _connect_traces(self):
        for var in [self.threshold_var, self.min_silence_var, self.padding1_var, self.padding2_var, self.enabled_var]:
            var.trace_add("write", self._on_var_changed)

    def _on_var_changed(self, *args):
        if self._suppress_callbacks:
            return
        if self.on_setting_change:
            try:
                self.on_setting_change(self.get_settings())
            except Exception:
                pass

    def set_settings(self, settings: dict):
        self._suppress_callbacks = True
        try:
            if "enabled" in settings: self.enabled_var.set(settings["enabled"])
            if "threshold" in settings: self.threshold_var.set(settings["threshold"])
            if "min_silence" in settings: self.min_silence_var.set(settings["min_silence"])
            if "padding1" in settings: self.padding1_var.set(settings["padding1"])
            if "padding2" in settings: self.padding2_var.set(settings["padding2"])
        finally:
            self._suppress_callbacks = False

    def get_settings(self) -> dict:
        return {
            "enabled": self.enabled_var.get(),
            "threshold": self.threshold_var.get(),
            "min_silence": self.min_silence_var.get(),
            "padding1": self.padding1_var.get(),
            "padding2": self.padding2_var.get()
        }
