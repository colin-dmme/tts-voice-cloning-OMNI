from __future__ import annotations

from datetime import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Callable

from omni_tts_license.models import LicenseStatus
from omni_tts_ui_tkinter.controller import TkinterController


class LicensePanel(ttk.Frame):
    def __init__(
        self,
        parent,
        controller: TkinterController,
        set_status: Callable[[str], None],
    ) -> None:
        super().__init__(parent, padding=14)
        self.controller = controller
        self.set_status = set_status
        self.status_var = tk.StringVar(value="")
        self.detail_var = tk.StringVar(value="")
        self.device_id_var = tk.StringVar(value=self.controller.current_device_id())
        self.status_label: ttk.Label | None = None
        self.import_button: ttk.Button | None = None
        self._build()
        self.refresh_status()

    def _build(self) -> None:
        self.columnconfigure(0, weight=1)

        status_box = ttk.LabelFrame(self, text="Trạng thái", padding=12)
        status_box.grid(row=0, column=0, sticky="ew")
        status_box.columnconfigure(0, weight=1)
        self.status_label = ttk.Label(
            status_box,
            textvariable=self.status_var,
            font=("Segoe UI", 12, "bold"),
        )
        self.status_label.grid(row=0, column=0, sticky="w")
        ttk.Label(
            status_box,
            textvariable=self.detail_var,
            wraplength=860,
            foreground="#555555",
        ).grid(row=1, column=0, sticky="ew", pady=(6, 0))

        device_box = ttk.LabelFrame(self, text="Mã máy", padding=12)
        device_box.grid(row=1, column=0, sticky="ew", pady=(12, 0))
        device_box.columnconfigure(0, weight=1)
        ttk.Entry(device_box, textvariable=self.device_id_var, state="readonly").grid(
            row=0, column=0, sticky="ew"
        )
        ttk.Button(device_box, text="Sao chép mã máy", command=self.copy_device_id).grid(
            row=0, column=1, padx=(8, 0)
        )

        controls = ttk.Frame(self)
        controls.grid(row=2, column=0, sticky="w", pady=(14, 0))
        self.import_button = ttk.Button(controls, text="Nhập file license", command=self.import_license)
        self.import_button.pack(
            side="left"
        )
        ttk.Button(controls, text="Kiểm tra lại", command=self.refresh_status).pack(
            side="left", padx=(8, 0)
        )

        ttk.Label(
            self,
            text=(
                "Nếu chưa có license, hãy gửi mã máy này cho người cấp bản quyền. "
                "Khi nhận được license.json, bấm Nhập file license để kích hoạt."
            ),
            wraplength=860,
            foreground="#555555",
        ).grid(row=3, column=0, sticky="ew", pady=(14, 0))

    def refresh_status(self) -> None:
        status = self.controller.license_status()
        label = "Đã kích hoạt" if status.valid else "Chưa kích hoạt"
        self.status_var.set(label)
        self.detail_var.set(format_license_status(status))
        foreground = "#1f7a3a" if status.valid else "#a3362d"
        if self.status_label is not None:
            self.status_label.configure(foreground=foreground)

    def focus_import_button(self) -> None:
        if self.import_button is not None:
            self.import_button.focus_set()

    def copy_device_id(self) -> None:
        self.clipboard_clear()
        self.clipboard_append(self.controller.current_device_id())
        self.set_status("Đã sao chép mã máy.")

    def import_license(self) -> None:
        path = filedialog.askopenfilename(
            title="Chọn file license",
            filetypes=[("License JSON", "*.json"), ("Tất cả", "*.*")],
        )
        if not path:
            return
        try:
            status = self.controller.install_license(Path(path))
        except Exception as exc:
            messagebox.showerror("License", f"Không nhập được license: {exc}")
            return
        self.refresh_status()
        if status.valid:
            messagebox.showinfo("License", "Kích hoạt thành công.")
        else:
            messagebox.showwarning("License", status.message)


def format_license_status(status: LicenseStatus) -> str:
    lines = [status.message]
    if status.email:
        lines.append(f"Email: {status.email}")
    if status.plan:
        lines.append(f"Gói: {status.plan}")
    if status.expires_at:
        if status.expires_at.time() == time.max:
            lines.append(f"Hết hạn: {status.expires_at.date().isoformat()}")
        else:
            lines.append(f"Hết hạn: {status.expires_at.strftime('%Y-%m-%d %H:%M')}")
    return "\n".join(lines)
