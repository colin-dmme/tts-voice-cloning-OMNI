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

SAMPLE_ROLES = ["neutral", "storytelling", "news", "emotional", "fast", "slow"]


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
        self.sample_role_var = tk.StringVar(value="neutral")
        self.samples_tree: ttk.Treeview | None = None
        self.audio_meta_label: ttk.Label | None = None
        self.sample_action_buttons: list[ttk.Button] = []
        self._build()
        self.refresh()

    def _build(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        # Main profile list treeview
        columns = ("name", "language", "duration", "project", "audio")
        self.table = ttk.Treeview(self, columns=columns, show="headings", height=10)
        headings = {
            "name": "Tên profile",
            "language": "Ngôn ngữ",
            "duration": "Thời lượng",
            "project": "Dự án",
            "audio": "File giọng mẫu",
        }
        widths = {"name": 160, "language": 90, "duration": 88, "project": 130, "audio": 380}
        for column, text in headings.items():
            self.table.heading(column, text=text)
            self.table.column(column, width=widths[column], anchor="center" if column == "duration" else "w")
        self.table.tag_configure("short_dur", foreground="#cc6600")
        self.table.grid(row=0, column=0, sticky="nsew")
        self.table.bind("<<TreeviewSelect>>", lambda _event: self.load_selected())

        # Edit form
        form = ttk.Frame(self)
        form.grid(row=1, column=0, sticky="ew", pady=(12, 0))
        form.columnconfigure(1, weight=1)

        self._entry(form, "Tên profile", self.name_var, 0)
        self._audio_row(form, 1)

        # Audio metadata label (duration + sample_rate, read-only)
        self.audio_meta_label = ttk.Label(form, text="", foreground="#888888")
        self.audio_meta_label.grid(row=2, column=1, sticky="w", pady=(0, 4))

        self._entry(form, "Dự án", self.project_var, 3)
        self._language_row(form, 4)

        ttk.Label(form, text="Transcript").grid(row=5, column=0, sticky="nw", pady=4)
        self.transcript_text = tk.Text(form, height=4, wrap="word")
        self.transcript_text.grid(row=5, column=1, sticky="ew", pady=4)

        ttk.Label(form, text="Ghi chú").grid(row=6, column=0, sticky="nw", pady=4)
        self.notes_text = tk.Text(form, height=3, wrap="word")
        self.notes_text.grid(row=6, column=1, sticky="ew", pady=4)

        self._build_samples_subframe(form, 7)

        # Action buttons
        buttons = ttk.Frame(self)
        buttons.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        ttk.Button(buttons, text="Lưu profile", command=self.save_profile).pack(side="left")
        ttk.Button(buttons, text="Tạo mới", command=self.clear_form).pack(side="left", padx=(8, 0))
        ttk.Button(buttons, text="Xóa profile", command=self.delete_selected).pack(
            side="left", padx=(8, 0)
        )
        ttk.Button(buttons, text="Làm mới", command=self.refresh).pack(side="left", padx=(8, 0))

    def _build_samples_subframe(self, parent: ttk.Frame, row: int) -> None:
        frame = ttk.LabelFrame(parent, text="Mẫu phụ (tối đa 2, tổng 3 mẫu)", padding=6)
        frame.grid(row=row, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        frame.columnconfigure(0, weight=1)

        self.samples_tree = ttk.Treeview(
            frame,
            columns=("default", "role", "duration", "transcript"),
            show="headings",
            height=3,
            selectmode="browse",
        )
        self.samples_tree.heading("default", text="★")
        self.samples_tree.heading("role", text="Vai trò")
        self.samples_tree.heading("duration", text="Thời lượng")
        self.samples_tree.heading("transcript", text="Transcript")
        self.samples_tree.column("default", width=28, stretch=False, anchor="center")
        self.samples_tree.column("role", width=100, stretch=False)
        self.samples_tree.column("duration", width=78, stretch=False, anchor="center")
        self.samples_tree.column("transcript", width=300)
        self.samples_tree.grid(row=0, column=0, sticky="ew")

        controls = ttk.Frame(frame)
        controls.grid(row=1, column=0, sticky="ew", pady=(6, 0))

        ttk.Label(controls, text="Vai trò:").pack(side="left")
        ttk.Combobox(
            controls,
            textvariable=self.sample_role_var,
            values=SAMPLE_ROLES,
            state="readonly",
            width=13,
        ).pack(side="left", padx=(4, 12))

        add_btn = ttk.Button(controls, text="Thêm mẫu phụ", command=self._add_extra_sample, state="disabled")
        add_btn.pack(side="left")
        remove_btn = ttk.Button(controls, text="Xóa đang chọn", command=self._remove_extra_sample, state="disabled")
        remove_btn.pack(side="left", padx=(8, 0))
        default_btn = ttk.Button(controls, text="Đặt làm mặc định", command=self._set_default_extra_sample, state="disabled")
        default_btn.pack(side="left", padx=(8, 0))

        self.sample_action_buttons = [add_btn, remove_btn, default_btn]

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
            dur = profile.duration_seconds
            dur_text = f"{dur:.1f}s" if dur > 0 else "?"
            tags = ("short_dur",) if 0 < dur < 3.0 else ()
            self.table.insert(
                "",
                "end",
                iid=profile.profile_id,
                values=(profile.name, profile.language, dur_text, profile.project, str(profile.audio_path)),
                tags=tags,
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
            profile, warnings = self.controller.save_voice_profile(
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
        self._update_audio_meta_label(profile)
        self._refresh_samples_treeview(profile)
        self._refresh_sample_buttons()
        self.refresh()
        messagebox.showinfo("Thông báo", f"Đã lưu profile: {profile.name}")
        if warnings:
            warning_text = "\n".join(f"• {w.message}" for w in warnings)
            messagebox.showwarning("Lưu ý", warning_text)

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
        if self.audio_meta_label is not None:
            self.audio_meta_label.configure(text="", foreground="#888888")
        if self.samples_tree is not None:
            for row in self.samples_tree.get_children():
                self.samples_tree.delete(row)
        self._refresh_sample_buttons()

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
        self._update_audio_meta_label(profile)
        self._refresh_samples_treeview(profile)
        self._refresh_sample_buttons()

    def _update_audio_meta_label(self, profile: VoiceProfile) -> None:
        if self.audio_meta_label is None:
            return
        dur = profile.duration_seconds
        sr = profile.sample_rate
        if dur > 0:
            sr_text = f"  |  {sr // 1000}kHz" if sr > 0 else ""
            text = f"{dur:.1f}s{sr_text}"
            color = "#2e7d32" if 3.0 <= dur <= 15.0 else "#e65100"
        else:
            text = "(lưu lại để cập nhật metadata)"
            color = "#888888"
        self.audio_meta_label.configure(text=text, foreground=color)

    def _refresh_samples_treeview(self, profile: VoiceProfile) -> None:
        if self.samples_tree is None:
            return
        for row in self.samples_tree.get_children():
            self.samples_tree.delete(row)
        for sample in profile.extra_samples:
            is_default = profile.default_sample_id == sample.sample_id
            dur_text = f"{sample.duration_seconds:.1f}s" if sample.duration_seconds > 0 else "?"
            transcript_preview = (sample.transcript[:50] + "…") if len(sample.transcript) > 50 else sample.transcript
            self.samples_tree.insert(
                "",
                "end",
                iid=sample.sample_id,
                values=("★" if is_default else "", sample.role, dur_text, transcript_preview),
            )

    def _refresh_sample_buttons(self) -> None:
        state = "normal" if self.profile_id_var.get() else "disabled"
        for btn in self.sample_action_buttons:
            btn.configure(state=state)

    def _add_extra_sample(self) -> None:
        profile_id = self.profile_id_var.get()
        if not profile_id:
            return
        path = filedialog.askopenfilename(
            title="Chọn file giọng mẫu phụ",
            filetypes=[("Audio", "*.wav *.mp3 *.flac"), ("Tất cả", "*.*")],
        )
        if not path:
            return
        role = self.sample_role_var.get()
        try:
            profile, warnings = self.controller.add_voice_profile_sample(
                profile_id=profile_id,
                audio_path=Path(path),
                role=role,
            )
        except Exception as exc:
            messagebox.showerror("Lỗi", str(exc))
            return
        self._refresh_samples_treeview(profile)
        if warnings:
            messagebox.showwarning("Lưu ý", "\n".join(f"• {w.message}" for w in warnings))

    def _remove_extra_sample(self) -> None:
        profile_id = self.profile_id_var.get()
        if not profile_id or self.samples_tree is None:
            return
        selected = self.samples_tree.selection()
        if not selected:
            messagebox.showinfo("Thông báo", "Hãy chọn mẫu phụ cần xóa.")
            return
        sample_id = selected[0]
        try:
            current_profile = self.controller.service.voice_profiles.get_profile(profile_id)
        except Exception as exc:
            messagebox.showerror("Lỗi", str(exc))
            return
        sample_index = next(
            (i + 1 for i, s in enumerate(current_profile.extra_samples) if s.sample_id == sample_id),
            None,
        )
        if sample_index is None:
            messagebox.showerror("Lỗi", "Không tìm thấy mẫu phụ.")
            return
        if not messagebox.askyesno("Xác nhận", "Xóa mẫu phụ đang chọn?"):
            return
        try:
            profile = self.controller.remove_voice_profile_sample(profile_id, sample_index)
        except Exception as exc:
            messagebox.showerror("Lỗi", str(exc))
            return
        self._refresh_samples_treeview(profile)

    def _set_default_extra_sample(self) -> None:
        profile_id = self.profile_id_var.get()
        if not profile_id or self.samples_tree is None:
            return
        selected = self.samples_tree.selection()
        if not selected:
            messagebox.showinfo("Thông báo", "Hãy chọn mẫu phụ muốn đặt làm mặc định.")
            return
        sample_id = selected[0]
        try:
            profile = self.controller.set_voice_profile_default_sample(profile_id, sample_id)
        except Exception as exc:
            messagebox.showerror("Lỗi", str(exc))
            return
        self._refresh_samples_treeview(profile)
