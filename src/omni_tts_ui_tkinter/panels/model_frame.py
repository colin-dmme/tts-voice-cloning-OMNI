"""
Model Frame Widget - Model loading status and controls.
Ported from Qwen3-TTS app.
"""

import tkinter as tk
from tkinter import ttk
from typing import Optional, Callable


class ModelFrame(ttk.LabelFrame):
    """Frame for model loading status and controls."""

    def __init__(
        self,
        parent: tk.Widget,
        on_load: Optional[Callable[[], None]] = None,
        on_unload: Optional[Callable[[], None]] = None,
        **kwargs
    ):
        super().__init__(parent, text="🤖 Model", **kwargs)

        self.on_load = on_load
        self.on_unload = on_unload

        self._setup_ui()

    def _setup_ui(self):
        """Setup UI components."""
        self.columnconfigure(1, weight=1)

        row = 0

        # Status row
        status_frame = ttk.Frame(self)
        status_frame.grid(row=row, column=0, columnspan=2, sticky="ew", padx=10, pady=(10, 5))

        self.status_indicator = ttk.Label(
            status_frame, text="🔴", font=("Segoe UI", 14)
        )
        self.status_indicator.pack(side="left")

        self.status_label = ttk.Label(
            status_frame, text="Chưa chọn model",
            font=("Segoe UI", 10)
        )
        self.status_label.pack(side="left", padx=(10, 0))

        self.vram_label = ttk.Label(
            status_frame, text="", foreground="gray",
            font=("Segoe UI", 9)
        )
        self.vram_label.pack(side="right")

        row += 1

        # Buttons row
        btn_frame = ttk.Frame(self)
        btn_frame.grid(row=row, column=0, columnspan=2, sticky="ew", padx=10, pady=(0, 10))

        self.load_btn = ttk.Button(
            btn_frame, text="⚡ Tải Model",
            command=self._on_load
        )
        self.load_btn.pack(side="left")

        self.unload_btn = ttk.Button(
            btn_frame, text="🔌 Giải phóng",
            command=self._on_unload,
            state="disabled"
        )
        self.unload_btn.pack(side="left", padx=(10, 0))

    def _on_load(self):
        """Handle load button click."""
        if self.on_load:
            self.on_load()

    def _on_unload(self):
        """Handle unload button click."""
        if self.on_unload:
            self.on_unload()

    def set_loading(self):
        """Set UI to loading state."""
        self.status_indicator.config(text="🟡")
        self.status_label.config(text="Đang tải model...")
        self.load_btn.config(state="disabled")
        self.unload_btn.config(state="disabled")

    def set_loaded(self, model_name: str, vram_mb: float = 0):
        """Set UI to loaded state."""
        short_name = model_name.split("/")[-1] if "/" in model_name else model_name
        self.status_indicator.config(text="🟢")
        self.status_label.config(text=f"{short_name}")
        if vram_mb > 0:
            self.vram_label.config(text=f"VRAM: {vram_mb:.0f}MB")
        else:
            self.vram_label.config(text="")
        self.load_btn.config(state="normal", text="🔄 Đổi Model")
        self.unload_btn.config(state="normal")

    def set_unloaded(self):
        """Set UI to unloaded state."""
        self.status_indicator.config(text="🔴")
        self.status_label.config(text="Chưa tải model")
        self.vram_label.config(text="")
        self.load_btn.config(state="normal", text="⚡ Tải Model")
        self.unload_btn.config(state="disabled")

    def set_error(self, message: str):
        """Set UI to error state."""
        self.status_indicator.config(text="❌")
        self.status_label.config(text=f"Lỗi: {message[:60]}")
        self.load_btn.config(state="normal", text="🔄 Thử lại")
        self.unload_btn.config(state="disabled")

    def set_status_text(self, text: str):
        """Set custom status text."""
        self.status_label.config(text=text)
