"""EPUB content policy controls for the Tkinter import dialog."""

import tkinter as tk
from tkinter import messagebox, ttk

from omni_tts_core.text.epub_content import parse_han_readings
from omni_tts_shared.epub import EpubContentOptions


class EpubContentFrame(ttk.LabelFrame):
    def __init__(self, parent, options=None, *, on_change=None):
        super().__init__(parent, text="Nội dung đưa vào giọng đọc", padding=8)
        policy = EpubContentOptions.model_validate(options or {})
        self.on_change = on_change
        self.readings = dict(policy.han_readings)
        self.variables = {}
        for name, label in [
            ("skip_references", "Bỏ nguồn / tài liệu tham khảo"),
            ("read_notes", "Giữ ghi chú giải thích"),
            ("include_frontmatter", "Đọc giới thiệu / thuật ngữ"),
            ("include_appendices", "Đọc phụ lục nội dung"),
            ("include_technical_notes", "Đọc ghi chú kỹ thuật cuối sách"),
            ("export_references", "Xuất nguồn tham khảo riêng cạnh audio"),
        ]:
            variable = tk.BooleanVar(value=getattr(policy, name))
            self.variables[name] = variable
            ttk.Checkbutton(
                self, text=label, variable=variable, command=self._changed
            ).pack(anchor="w", pady=3)
        self.url_choices = {
            "Không đọc URL / DOI": "skip",
            "Chỉ đọc tên miền": "domain",
            "Đọc nguyên địa chỉ": "read",
        }
        self.han_choices = {
            "Dùng nghĩa Việt sẵn có + cảnh báo": "prefer_vietnamese",
            "Giữ chữ Hán + cảnh báo": "warn",
            "Giữ chữ Hán, không cảnh báo": "keep",
        }
        for name, label, choices in [
            ("url_mode", "Đường link", self.url_choices),
            ("han_mode", "Chữ Hán", self.han_choices),
        ]:
            ttk.Label(self, text=label).pack(anchor="w", pady=(8, 2))
            variable = tk.StringVar(
                value=next(k for k, v in choices.items() if v == getattr(policy, name))
            )
            self.variables[name] = variable
            combo = ttk.Combobox(
                self, textvariable=variable, values=list(choices), state="readonly"
            )
            combo.pack(fill="x")
            combo.bind("<<ComboboxSelected>>", self._changed)
        self.readings_button = ttk.Button(
            self,
            text=f"Cách đọc chữ Hán… ({len(self.readings)} cụm)",
            command=self._edit_readings,
        )
        self.readings_button.pack(fill="x", pady=8)

    def _changed(self, *_):
        if self.on_change:
            self.on_change()

    def options(self):
        values = {k: v.get() for k, v in self.variables.items()}
        values["url_mode"] = self.url_choices[values["url_mode"]]
        values["han_mode"] = self.han_choices[values["han_mode"]]
        return EpubContentOptions(**values, han_readings=self.readings).model_dump()

    def _edit_readings(self):
        dialog = tk.Toplevel(self)
        dialog.title("Cách đọc chữ Hán")
        dialog.transient(self.winfo_toplevel())
        dialog.grab_set()
        ttk.Label(dialog, text="Mỗi dòng: chữ gốc = cách đọc. Ví dụ: 万 = vạn").pack(
            padx=12, pady=8
        )
        editor = tk.Text(dialog, height=9, width=60)
        editor.insert("1.0", "\n".join(f"{a} = {b}" for a, b in self.readings.items()))
        editor.pack(fill="both", expand=True, padx=12)

        def save():
            try:
                self.readings = parse_han_readings(editor.get("1.0", "end"))
            except ValueError as exc:
                messagebox.showwarning("Cách đọc chưa hợp lệ", str(exc), parent=dialog)
                return
            self.readings_button.configure(
                text=f"Cách đọc chữ Hán… ({len(self.readings)} cụm)"
            )
            self._changed()
            dialog.destroy()

        ttk.Button(dialog, text="Lưu cách đọc", command=save).pack(pady=10)
