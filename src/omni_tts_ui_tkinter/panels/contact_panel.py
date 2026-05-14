from __future__ import annotations

import tkinter as tk
import webbrowser
from tkinter import ttk


class ContactPanel(ttk.Frame):
    def __init__(self, parent, settings, status_var: tk.StringVar) -> None:
        super().__init__(parent, padding=18)
        self.settings = settings
        self.status_var = status_var
        self._build()

    def _build(self) -> None:
        self.columnconfigure(0, weight=1)
        contact = self.settings.contact_info
        title = contact.get("title") or self.settings.app_name
        subtitle = contact.get("subtitle") or "Thông tin hỗ trợ và liên hệ."

        ttk.Label(self, text=title, font=("Segoe UI", 16, "bold")).grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(self, text=subtitle, foreground="#555555", wraplength=760).grid(
            row=1, column=0, sticky="ew", pady=(6, 16)
        )

        box = ttk.LabelFrame(self, text="Thông tin liên hệ", padding=14)
        box.grid(row=2, column=0, sticky="ew")
        box.columnconfigure(1, weight=1)

        row = 0
        for label, key in (("Telegram", "telegram"), ("Facebook", "facebook")):
            value = contact.get(key, "").strip()
            if not value:
                continue
            ttk.Label(box, text=label).grid(row=row, column=0, sticky="w", pady=4)
            ttk.Label(box, text=value).grid(row=row, column=1, sticky="ew", padx=(12, 0), pady=4)
            ttk.Button(box, text="Mở", command=lambda link=value: self._open(link)).grid(
                row=row, column=2, padx=(12, 0), pady=4
            )
            ttk.Button(box, text="Sao chép", command=lambda copied=value: self._copy(copied)).grid(
                row=row, column=3, padx=(8, 0), pady=4
            )
            row += 1

        if row == 0:
            ttk.Label(
                box,
                text=(
                    "Chưa có thông tin liên hệ. Có thể thêm Telegram hoặc Facebook "
                    "trong config/app.yaml."
                ),
                foreground="#555555",
                wraplength=760,
            ).grid(row=0, column=0, columnspan=4, sticky="ew")

    def _copy(self, value: str) -> None:
        self.clipboard_clear()
        self.clipboard_append(value)
        self.status_var.set("Đã sao chép thông tin liên hệ.")

    @staticmethod
    def _open(value: str) -> None:
        url = value if value.startswith(("http://", "https://")) else f"https://{value}"
        webbrowser.open(url)
