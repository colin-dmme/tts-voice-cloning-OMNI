from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from omni_tts_shared.schemas import VoiceProfile
from omni_tts_ui_tkinter.controller import TkinterController


LANGUAGE_CHOICES = {
    "Tiếng Việt": "vi",
    "English": "en",
    "Chinese": "zh",
    "Japanese": "ja",
    "Korean": "ko",
    "German": "de",
    "French": "fr",
    "Russian": "ru",
    "Portuguese": "pt",
    "Spanish": "es",
    "Italian": "it",
}
LANGUAGE_LABELS = {value: label for label, value in LANGUAGE_CHOICES.items()}


class VoiceProfilePanel(ttk.Frame):
    def __init__(self, parent, controller: TkinterController, on_change) -> None:
        super().__init__(parent, padding=10)
        self.controller = controller
        self.on_change = on_change
        self.profile_id_var = tk.StringVar()
        self.name_var = tk.StringVar()
        self.audio_path_var = tk.StringVar()
        self.language_var = tk.StringVar(value="Tiếng Việt")
        self.project_var = tk.StringVar()
        self._build()
        self.refresh()

    def _build(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        columns = ("name", "language", "project", "audio")
        self.table = ttk.Treeview(self, columns=columns, show="headings", height=10)
        headings = {
            "name": "Tên profile",
            "language": "Ngôn ngữ",
            "project": "Dự án",
            "audio": "File giọng mẫu",
        }
        for column, text in headings.items():
            self.table.heading(column, text=text)
            self.table.column(column, width=160 if column != "audio" else 460)
        self.table.grid(row=0, column=0, sticky="nsew")
        self.table.bind("<<TreeviewSelect>>", lambda _event: self.load_selected())

        form = ttk.Frame(self)
        form.grid(row=1, column=0, sticky="ew", pady=(12, 0))
        form.columnconfigure(1, weight=1)
        self._entry(form, "Tên profile", self.name_var, 0)
        self._audio_row(form, 1)
        self._entry(form, "Dự án", self.project_var, 2)
        self._language_row(form, 3)
        ttk.Label(form, text="Transcript").grid(row=4, column=0, sticky="nw", pady=4)
        self.transcript_text = tk.Text(form, height=4, wrap="word")
        self.transcript_text.grid(row=4, column=1, sticky="ew", pady=4)
        ttk.Label(form, text="Ghi chú").grid(row=5, column=0, sticky="nw", pady=4)
        self.notes_text = tk.Text(form, height=3, wrap="word")
        self.notes_text.grid(row=5, column=1, sticky="ew", pady=4)

        buttons = ttk.Frame(self)
        buttons.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        ttk.Button(buttons, text="Lưu profile", command=self.save_profile).pack(side="left")
        ttk.Button(buttons, text="Tạo mới", command=self.clear_form).pack(side="left", padx=(8, 0))
        ttk.Button(buttons, text="Xóa profile", command=self.delete_selected).pack(
            side="left", padx=(8, 0)
        )
        ttk.Button(buttons, text="Làm mới", command=self.refresh).pack(side="left", padx=(8, 0))

    def _entry(self, parent, label: str, variable: tk.StringVar, row: int) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=4)
        ttk.Entry(parent, textvariable=variable).grid(row=row, column=1, sticky="ew", pady=4)

    def _audio_row(self, parent, row: int) -> None:
        ttk.Label(parent, text="File giọng mẫu").grid(row=row, column=0, sticky="w", pady=4)
        frame = ttk.Frame(parent)
        frame.grid(row=row, column=1, sticky="ew", pady=4)
        frame.columnconfigure(0, weight=1)
        ttk.Entry(frame, textvariable=self.audio_path_var).grid(row=0, column=0, sticky="ew")
        ttk.Button(frame, text="Chọn", command=self.choose_audio).grid(row=0, column=1, padx=(6, 0))

    def _language_row(self, parent, row: int) -> None:
        ttk.Label(parent, text="Ngôn ngữ").grid(row=row, column=0, sticky="w", pady=4)
        ttk.Combobox(
            parent,
            textvariable=self.language_var,
            values=list(LANGUAGE_CHOICES.keys()),
            state="readonly",
        ).grid(row=row, column=1, sticky="ew", pady=4)

    def choose_audio(self) -> None:
        path = filedialog.askopenfilename(
            title="Chọn file giọng mẫu",
            filetypes=[("Audio", "*.wav *.mp3 *.flac"), ("Tất cả", "*.*")],
        )
        if path:
            self.audio_path_var.set(path)

    def refresh(self) -> None:
        for row in self.table.get_children():
            self.table.delete(row)
        for profile in self.controller.all_voice_profiles():
            self.table.insert(
                "",
                "end",
                iid=profile.profile_id,
                values=(profile.name, profile.language, profile.project, str(profile.audio_path)),
            )
        self.on_change()

    def load_selected(self) -> None:
        selected = self.table.selection()
        if not selected:
            return
        profiles = {item.profile_id: item for item in self.controller.all_voice_profiles()}
        profile = profiles.get(selected[0])
        if profile:
            self._fill_form(profile)

    def save_profile(self) -> None:
        try:
            profile = self.controller.save_voice_profile(
                name=self.name_var.get(),
                audio_path=Path(self.audio_path_var.get()),
                transcript=self.transcript_text.get("1.0", "end").strip(),
                language=LANGUAGE_CHOICES.get(self.language_var.get(), "vi"),
                project=self.project_var.get(),
                notes=self.notes_text.get("1.0", "end").strip(),
                profile_id=self.profile_id_var.get() or None,
            )
        except Exception as exc:
            messagebox.showerror("Lỗi", str(exc))
            return
        self.profile_id_var.set(profile.profile_id)
        self.refresh()
        messagebox.showinfo("Thông báo", f"Đã lưu profile: {profile.name}")

    def delete_selected(self) -> None:
        selected = self.table.selection()
        if not selected:
            messagebox.showinfo("Thông báo", "Hãy chọn profile cần xóa.")
            return
        if not messagebox.askyesno("Xác nhận", "Xóa profile giọng đang chọn?"):
            return
        self.controller.delete_voice_profile(selected[0])
        self.clear_form()
        self.refresh()

    def clear_form(self) -> None:
        self.profile_id_var.set("")
        self.name_var.set("")
        self.audio_path_var.set("")
        self.language_var.set("Tiếng Việt")
        self.project_var.set("")
        self.transcript_text.delete("1.0", "end")
        self.notes_text.delete("1.0", "end")

    def _fill_form(self, profile: VoiceProfile) -> None:
        self.profile_id_var.set(profile.profile_id)
        self.name_var.set(profile.name)
        self.audio_path_var.set(str(profile.audio_path))
        self.language_var.set(LANGUAGE_LABELS.get(profile.language, profile.language))
        self.project_var.set(profile.project)
        self.transcript_text.delete("1.0", "end")
        self.transcript_text.insert("1.0", profile.transcript)
        self.notes_text.delete("1.0", "end")
        self.notes_text.insert("1.0", profile.notes)
