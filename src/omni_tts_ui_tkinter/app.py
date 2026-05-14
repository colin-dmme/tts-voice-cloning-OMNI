from __future__ import annotations

import os
import threading
import tkinter as tk
import time
from pathlib import Path
from threading import Event
from tkinter import filedialog, messagebox, ttk

from omni_tts_core.progress import ProgressEvent
from omni_tts_shared.errors import GenerationCancelled, OmniTtsError
from omni_tts_shared.languages import LANGUAGE_CODES, LANGUAGE_LABELS, language_choices
from omni_tts_ui_tkinter.controller import TkinterController, format_result
from omni_tts_ui_tkinter.dnd import enable_file_drop
from omni_tts_ui_tkinter.panels.contact_panel import ContactPanel
from omni_tts_ui_tkinter.panels.license_panel import LicensePanel
from omni_tts_ui_tkinter.preferences import TkinterPreferences
from omni_tts_ui_tkinter.state import UiSettings
from omni_tts_ui_tkinter.voice_panel import VoiceProfilePanel
from omni_tts_ui_tkinter.widgets import (
    ScrollableFrame,
    append_log,
    browse_directory,
    browse_file,
    clear_log,
    split_paths,
)


class TkinterApp:
    def __init__(self, root) -> None:
        self.root = root
        self.controller = TkinterController()
        self.preferences = TkinterPreferences()
        self.preference_data = self.preferences.load()
        self.model_map = dict(self.controller.model_choices())
        self.voice_profile_map: dict[str, str | None] = {}
        self.voice_profile_combos: list[ttk.Combobox] = []
        self.notebook: ttk.Notebook | None = None
        self.license_panel: LicensePanel | None = None
        self.active_cancel_event: Event | None = None
        self.active_log_widget: tk.Text | None = None
        self.action_buttons: list[ttk.Button] = []
        self.text_output_dirs: list[Path] = []
        self.file_output_dirs: list[Path] = []
        self.text_open_folder_button: ttk.Button | None = None
        self.file_open_folder_button: ttk.Button | None = None
        self.language_combos: list[ttk.Combobox] = []
        self.profile_combos: list[ttk.Combobox] = []
        self.speed_spins: list[ttk.Spinbox] = []
        self.pitch_spins: list[ttk.Spinbox] = []
        self.emotion_combos: list[ttk.Combobox] = []
        self._preference_trace_ready = False
        self._busy_tick_id: str | None = None
        self._last_progress_update = 0.0
        self._pending_progress_after = False
        self._pending_progress_event: ProgressEvent | None = None
        self._init_vars()
        self._configure_root()
        self._build_layout()
        self.refresh_models()
        self._bind_preference_traces()

    def _init_vars(self) -> None:
        model_label = self._model_label_for_id(self.preference_data.get("model_id"))
        language = str(self.preference_data.get("language") or "vi")
        self.language_var = tk.StringVar(value=LANGUAGE_LABELS.get(language, "Tiếng Việt"))
        self.model_var = tk.StringVar(value=model_label)
        self.voice_profile_var = tk.StringVar(value="Không dùng profile")
        self.ref_audio_var = tk.StringVar()
        self.ref_text_var = tk.StringVar()
        self.output_dir_var = tk.StringVar(value=str(self.preference_data.get("output_dir") or ""))
        self.output_stem_var = tk.StringVar(value=str(self.preference_data.get("output_stem") or ""))
        self.speed_var = tk.DoubleVar(value=float(self.preference_data.get("speed", 1.0)))
        self.pitch_var = tk.DoubleVar(value=float(self.preference_data.get("pitch_shift", 0.0)))
        self.emotion_var = tk.StringVar(value=str(self.preference_data.get("emotion") or "natural"))
        self.runtime_var = tk.StringVar(value="")
        self.pause_var = tk.IntVar(value=int(self.preference_data.get("sentence_pause_ms", 450)))
        self.chunk_var = tk.IntVar(value=int(self.preference_data.get("max_chunk_chars", 220)))
        self.overwrite_var = tk.BooleanVar(value=bool(self.preference_data.get("overwrite", False)))
        self.split_output_var = tk.BooleanVar(
            value=bool(self.preference_data.get("split_output", True))
        )
        self.output_srt_var = tk.BooleanVar(value=bool(self.preference_data.get("output_srt", False)))
        self.status_var = tk.StringVar(value=self.controller.startup_notice())
        self.progress_var = tk.DoubleVar(value=0.0)

    def _model_label_for_id(self, model_id: str | None) -> str:
        for label, item_id in self.model_map.items():
            if item_id == model_id:
                return label
        return "OmniVoice Vietnamese"

    def _configure_root(self) -> None:
        self.root.title(self.controller.service.settings.app_display_name)
        self.root.geometry("1180x760")
        self.root.minsize(960, 640)
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        style = ttk.Style()
        style.configure("Accent.TButton", font=("Segoe UI", 10, "bold"))

    def _build_layout(self) -> None:
        main = ttk.Frame(self.root, padding=12)
        main.grid(row=0, column=0, sticky="nsew")
        main.columnconfigure(0, weight=1)
        main.rowconfigure(1, weight=1)

        ttk.Label(
            main,
            text=self.controller.service.settings.app_display_name,
            font=("Segoe UI", 18, "bold"),
        ).grid(
            row=0, column=0, sticky="w"
        )

        notebook = ttk.Notebook(main)
        self.notebook = notebook
        notebook.grid(row=1, column=0, sticky="nsew", pady=(10, 8))
        self._build_text_tab(notebook)
        self._build_file_tab(notebook)
        self._build_model_tab(notebook)
        self._build_voice_profile_tab(notebook)
        self._build_license_tab(notebook)
        self._build_contact_tab(notebook)

        bottom = ttk.Frame(main)
        bottom.grid(row=2, column=0, sticky="ew")
        bottom.columnconfigure(0, weight=1)
        status = ttk.Label(bottom, textvariable=self.status_var, anchor="w")
        status.grid(row=0, column=0, sticky="ew", pady=(0, 4))
        ttk.Progressbar(
            bottom,
            variable=self.progress_var,
            maximum=100,
            mode="determinate",
        ).grid(row=1, column=0, sticky="ew")
        self.cancel_button = ttk.Button(
            bottom,
            text="Hủy",
            command=self.cancel_current_task,
            state="disabled",
        )
        self.cancel_button.grid(row=1, column=1, sticky="e", padx=(8, 0))

    def _build_text_tab(self, notebook: ttk.Notebook) -> None:
        tab = ttk.Frame(notebook, padding=10)
        tab.columnconfigure(0, weight=3)
        tab.columnconfigure(1, weight=1)
        tab.rowconfigure(0, weight=1)
        notebook.add(tab, text="Tạo từ văn bản")

        self.text_input = tk.Text(tab, wrap="word", height=18, undo=True)
        self.text_input.grid(row=0, column=0, sticky="nsew", padx=(0, 10))

        side = ttk.Frame(tab)
        side.grid(row=0, column=1, sticky="nsew")
        side.columnconfigure(0, weight=1)
        side.rowconfigure(1, weight=1)

        self.text_generate_button = ttk.Button(
            side,
            text="Tạo audio",
            style="Accent.TButton",
            command=self.generate_from_text,
        )
        self.text_generate_button.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        self.action_buttons.append(self.text_generate_button)

        controls_scroll = ScrollableFrame(side)
        controls_scroll.grid(row=1, column=0, sticky="nsew")
        self._build_common_controls(controls_scroll.content)

        self._build_output_controls(
            tab,
            include_output_stem=True,
            open_command=self.open_text_output_folder,
            button_attr="text_open_folder_button",
        ).grid(row=1, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        self._build_log_header(tab, self.clear_text_log).grid(
            row=2, column=0, columnspan=2, sticky="ew", pady=(10, 0)
        )
        self.text_log = tk.Text(tab, height=7, state="disabled", wrap="word")
        self.text_log.grid(row=3, column=0, columnspan=2, sticky="nsew", pady=(4, 0))

    def _build_file_tab(self, notebook: ttk.Notebook) -> None:
        tab = ttk.Frame(notebook, padding=10)
        tab.columnconfigure(0, weight=1)
        tab.columnconfigure(1, weight=1)
        tab.rowconfigure(1, weight=1)
        notebook.add(tab, text="Xử lý file")

        top = ttk.Frame(tab)
        top.grid(row=0, column=0, columnspan=2, sticky="ew")
        ttk.Button(top, text="Thêm file", command=self.add_source_files).pack(side="left")
        ttk.Button(top, text="Xóa danh sách", command=self.clear_source_files).pack(
            side="left", padx=(8, 0)
        )
        ttk.Label(top, text="Hỗ trợ: .txt, .md, .srt").pack(side="left", padx=(14, 0))

        self.file_list = tk.Listbox(tab, selectmode="extended", height=14)
        self.file_list.grid(row=1, column=0, sticky="nsew", pady=(8, 0), padx=(0, 10))
        enabled = enable_file_drop(self.file_list, self.add_dropped_files)
        if enabled:
            hint = "Kéo thả một hoặc nhiều file vào danh sách."
        else:
            hint = "Bấm Thêm file để chọn một hoặc nhiều file nguồn."
        ttk.Label(tab, text=hint).grid(row=2, column=0, sticky="w", pady=(6, 0))

        right = ttk.Frame(tab)
        right.grid(row=1, column=1, sticky="nsew", pady=(8, 0))
        right.columnconfigure(0, weight=1)
        right.rowconfigure(1, weight=1)
        self.file_generate_button = ttk.Button(
            right,
            text="Tạo audio cho các file",
            style="Accent.TButton",
            command=self.generate_from_files,
        )
        self.file_generate_button.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        self.action_buttons.append(self.file_generate_button)
        controls_scroll = ScrollableFrame(right)
        controls_scroll.grid(row=1, column=0, sticky="nsew")
        self._build_common_controls(controls_scroll.content, include_output_stem=False)

        self._build_output_controls(
            tab,
            include_output_stem=False,
            open_command=self.open_file_output_folder,
            button_attr="file_open_folder_button",
        ).grid(row=3, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        self._build_log_header(tab, self.clear_file_log).grid(
            row=4, column=0, columnspan=2, sticky="ew", pady=(10, 0)
        )
        self.file_log = tk.Text(tab, height=8, state="disabled", wrap="word")
        self.file_log.grid(row=5, column=0, columnspan=2, sticky="nsew", pady=(4, 0))

    def _build_log_header(self, parent: ttk.Frame, clear_command) -> ttk.Frame:
        header = ttk.Frame(parent)
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text="Nhật ký").grid(row=0, column=0, sticky="w")
        ttk.Button(header, text="Xóa nhật ký", command=clear_command).grid(row=0, column=1, sticky="e")
        return header

    def _build_model_tab(self, notebook: ttk.Notebook) -> None:
        tab = ttk.Frame(notebook, padding=10)
        tab.columnconfigure(0, weight=1)
        tab.rowconfigure(0, weight=1)
        notebook.add(tab, text="Quản lý model")

        columns = ("name", "type", "required", "status", "device", "size", "path")
        self.model_table = ttk.Treeview(tab, columns=columns, show="headings", height=12)
        headings = {
            "name": "Tên",
            "type": "Loại",
            "required": "Bắt buộc",
            "status": "Trạng thái",
            "device": "Thiết bị",
            "size": "MB",
            "path": "Đường dẫn",
        }
        for column, label in headings.items():
            self.model_table.heading(column, text=label)
            self.model_table.column(column, width=140 if column != "path" else 430)
        self.model_table.grid(row=0, column=0, sticky="nsew")

        controls = ttk.Frame(tab)
        controls.grid(row=1, column=0, sticky="ew", pady=(10, 0))
        ttk.Button(controls, text="Tải model đang chọn", command=self.download_selected_model).pack(
            side="left"
        )
        ttk.Button(
            controls,
            text="Tải model bắt buộc còn thiếu",
            command=self.download_required_models,
        ).pack(side="left", padx=(8, 0))
        ttk.Button(controls, text="Làm mới", command=self.refresh_models).pack(
            side="left", padx=(8, 0)
        )

    def _build_voice_profile_tab(self, notebook: ttk.Notebook) -> None:
        panel = VoiceProfilePanel(notebook, self.controller, self.refresh_voice_profiles)
        notebook.add(panel, text="Profile giọng")

    def _build_license_tab(self, notebook: ttk.Notebook) -> None:
        self.license_panel = LicensePanel(notebook, self.controller, self.status_var.set)
        notebook.add(self.license_panel, text="Bản quyền")

    def _build_contact_tab(self, notebook: ttk.Notebook) -> None:
        tab = ContactPanel(notebook, self.controller.service.settings, self.status_var)
        notebook.add(tab, text="Liên hệ")

    def _build_common_controls(self, parent: ttk.Frame, include_output_stem: bool = True) -> None:
        ttk.Label(parent, text="Model TTS").pack(anchor="w")
        model_combo = ttk.Combobox(
            parent,
            textvariable=self.model_var,
            values=list(self.model_map.keys()),
            state="readonly",
        )
        model_combo.pack(fill="x", pady=(4, 8))
        model_combo.bind("<<ComboboxSelected>>", lambda _event: self.on_model_changed())

        ttk.Label(parent, textvariable=self.runtime_var, foreground="#555555", wraplength=360).pack(
            anchor="w", pady=(0, 8)
        )

        ttk.Label(parent, text="Ngôn ngữ").pack(anchor="w")
        language_combo = ttk.Combobox(
            parent,
            textvariable=self.language_var,
            values=language_choices(["vi", "en"]),
            state="readonly",
        )
        language_combo.pack(fill="x", pady=(4, 8))
        self.language_combos.append(language_combo)

        ttk.Label(parent, text="Profile giọng").pack(anchor="w")
        profile_combo = ttk.Combobox(
            parent,
            textvariable=self.voice_profile_var,
            values=list(self.voice_profile_map.keys()),
            state="readonly",
        )
        profile_combo.pack(fill="x", pady=(4, 8))
        self.voice_profile_combos.append(profile_combo)
        self.profile_combos.append(profile_combo)

        self.speed_spins.append(self._spin(parent, "Tốc độ đọc", self.speed_var, 0.5, 1.8, 0.05))
        self.pitch_spins.append(self._spin(parent, "Pitch shift", self.pitch_var, -12.0, 12.0, 0.5))
        ttk.Label(parent, text="Cảm xúc VieNeu").pack(anchor="w")
        emotion_combo = ttk.Combobox(
            parent,
            textvariable=self.emotion_var,
            values=["natural", "storytelling"],
            state="readonly",
        )
        emotion_combo.pack(fill="x", pady=(4, 8))
        self.emotion_combos.append(emotion_combo)
        self._spin(parent, "Nghỉ giữa câu, ms", self.pause_var, 0, 3000, 50)
        self._spin(parent, "Độ dài mỗi đoạn", self.chunk_var, 60, 800, 20)

    def _build_output_controls(
        self,
        parent: ttk.Frame,
        *,
        include_output_stem: bool,
        open_command,
        button_attr: str,
    ) -> ttk.Frame:
        frame = ttk.LabelFrame(parent, text="Tùy chọn xuất", padding=8)
        frame.columnconfigure(1, weight=1)

        ttk.Label(frame, text="Thư mục xuất riêng").grid(row=0, column=0, sticky="w", pady=2)
        output_row = ttk.Frame(frame)
        output_row.grid(row=0, column=1, sticky="ew", padx=(8, 0), pady=2)
        output_row.columnconfigure(0, weight=1)
        ttk.Entry(output_row, textvariable=self.output_dir_var).grid(row=0, column=0, sticky="ew")
        ttk.Button(output_row, text="Chọn", command=self.choose_output_dir).grid(
            row=0, column=1, padx=(6, 0)
        )

        row = 1
        if include_output_stem:
            ttk.Label(frame, text="Tên file xuất").grid(row=row, column=0, sticky="w", pady=2)
            ttk.Entry(frame, textvariable=self.output_stem_var).grid(
                row=row, column=1, sticky="ew", padx=(8, 0), pady=2
            )
            row += 1

        checks = ttk.Frame(frame)
        checks.grid(row=row, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        ttk.Checkbutton(
            checks,
            text="Ghi đè file nếu đã tồn tại",
            variable=self.overwrite_var,
            command=self.save_preferences,
        ).pack(side="left")
        ttk.Checkbutton(
            checks,
            text="Tách mỗi dòng SRT/đoạn văn thành một file audio",
            variable=self.split_output_var,
            command=self.save_preferences,
        ).pack(side="left", padx=(14, 0))
        ttk.Checkbutton(
            checks,
            text="Xuất kèm SRT",
            variable=self.output_srt_var,
            command=self.save_preferences,
        ).pack(side="left", padx=(14, 0))

        open_button = ttk.Button(
            checks,
            text="Mở thư mục audio",
            command=open_command,
            state="disabled",
        )
        open_button.pack(side="right")
        setattr(self, button_attr, open_button)
        return frame

    def _path_row(self, parent, label: str, variable: tk.StringVar, command) -> None:
        ttk.Label(parent, text=label).pack(anchor="w")
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=(4, 8))
        ttk.Entry(row, textvariable=variable).pack(side="left", fill="x", expand=True)
        ttk.Button(row, text="Chọn", command=command).pack(side="left", padx=(6, 0))

    def _spin(self, parent, label: str, variable: tk.Variable, from_: float, to: float, step: float):
        ttk.Label(parent, text=label).pack(anchor="w")
        spin = ttk.Spinbox(parent, textvariable=variable, from_=from_, to=to, increment=step)
        spin.pack(fill="x", pady=(4, 8))
        return spin

    def choose_reference_audio(self) -> None:
        browse_file(
            self.ref_audio_var,
            "Chọn file giọng mẫu",
            [("Audio", "*.wav *.mp3 *.flac"), ("Tất cả", "*.*")],
        )

    def choose_output_dir(self) -> None:
        browse_directory(self.output_dir_var)

    def add_source_files(self) -> None:
        paths = filedialog.askopenfilenames(
            title="Chọn file nguồn",
            filetypes=[("Text/SRT", "*.txt *.md *.srt"), ("Tất cả", "*.*")],
        )
        self.add_dropped_files([Path(path) for path in paths])

    def add_dropped_files(self, paths: list[Path]) -> None:
        existing = set(self.file_list.get(0, "end"))
        for path in paths:
            text = str(path)
            if text not in existing:
                self.file_list.insert("end", text)
                existing.add(text)

    def clear_source_files(self) -> None:
        self.file_list.delete(0, "end")

    def clear_text_log(self) -> None:
        clear_log(self.text_log)

    def clear_file_log(self) -> None:
        clear_log(self.file_log)

    def current_settings(self, for_files: bool = False) -> UiSettings:
        output_dir_text = self.output_dir_var.get().strip()
        ref_audio_text = self.ref_audio_var.get().strip()
        output_stem = None if for_files else self.output_stem_var.get().strip() or None
        return UiSettings(
            language=LANGUAGE_CODES.get(self.language_var.get(), "vi"),
            model_id=self.model_map.get(self.model_var.get(), "omnivoice_vietnamese"),
            voice_profile_id=self.voice_profile_map.get(self.voice_profile_var.get()),
            reference_audio_path=Path(ref_audio_text) if ref_audio_text else None,
            reference_text=self.ref_text_var.get().strip(),
            speed=float(self.speed_var.get()),
            pitch_shift=float(self.pitch_var.get()),
            emotion=self.emotion_var.get(),
            sentence_pause_ms=int(self.pause_var.get()),
            max_chunk_chars=int(self.chunk_var.get()),
            output_dir=Path(output_dir_text) if output_dir_text else None,
            output_stem=output_stem,
            overwrite=bool(self.overwrite_var.get()),
            split_output=bool(self.split_output_var.get()),
            output_srt=bool(self.output_srt_var.get()),
        )

    def save_preferences(self) -> None:
        if not self._preference_trace_ready:
            return
        self.preference_data.update({
            "language": LANGUAGE_CODES.get(self.language_var.get(), "vi"),
            "model_id": self.model_map.get(self.model_var.get(), "omnivoice_vietnamese"),
            "voice_profile_id": self.voice_profile_map.get(self.voice_profile_var.get()),
            "output_dir": self.output_dir_var.get().strip(),
            "output_stem": self.output_stem_var.get().strip(),
            "speed": float(self.speed_var.get()),
            "pitch_shift": float(self.pitch_var.get()),
            "emotion": self.emotion_var.get(),
            "sentence_pause_ms": int(self.pause_var.get()),
            "max_chunk_chars": int(self.chunk_var.get()),
            "overwrite": bool(self.overwrite_var.get()),
            "split_output": bool(self.split_output_var.get()),
            "output_srt": bool(self.output_srt_var.get()),
        })
        self.preferences.save(self.preference_data)

    def _bind_preference_traces(self) -> None:
        variables = [
            self.language_var,
            self.model_var,
            self.voice_profile_var,
            self.output_dir_var,
            self.output_stem_var,
            self.speed_var,
            self.pitch_var,
            self.emotion_var,
            self.pause_var,
            self.chunk_var,
            self.overwrite_var,
            self.split_output_var,
            self.output_srt_var,
        ]
        for variable in variables:
            variable.trace_add("write", lambda *_args: self.save_preferences())
        self._preference_trace_ready = True
        self.save_preferences()

    def generate_from_text(self) -> None:
        text = self.text_input.get("1.0", "end").strip()
        settings = self.current_settings()
        if not self._show_license_problem(settings.model_id):
            return
        self.text_output_dirs = []
        self._set_open_button_state(self.text_open_folder_button, self.text_output_dirs)
        append_log(self.text_log, self._generation_summary(settings, f"Nội dung nhập tay: {len(text)} ký tự"))
        self._run_background(
            "Đang tạo audio từ văn bản...",
            lambda progress, cancel: self.controller.generate_text(text, settings, progress, cancel),
            lambda result: self._handle_text_result(result),
            log_widget=self.text_log,
        )

    def generate_from_files(self) -> None:
        paths = split_paths("\n".join(self.file_list.get(0, "end")))
        settings = self.current_settings(for_files=True)
        if not self._show_license_problem(settings.model_id):
            return
        self.file_output_dirs = []
        self._set_open_button_state(self.file_open_folder_button, self.file_output_dirs)
        append_log(self.file_log, self._generation_summary(settings, f"Số file nguồn: {len(paths)}"))
        for path in paths:
            append_log(self.file_log, f"File nguồn: {path}")
        self._run_background(
            "Đang xử lý danh sách file...",
            lambda progress, cancel: self.controller.generate_files(paths, settings, progress, cancel),
            self._log_file_results,
            log_widget=self.file_log,
        )

    def _handle_text_result(self, result) -> None:
        append_log(self.text_log, format_result(result))
        self.text_output_dirs = _result_output_dirs([result])
        self._set_open_button_state(self.text_open_folder_button, self.text_output_dirs)

    def _log_file_results(self, results) -> None:
        for result in results:
            append_log(self.file_log, format_result(result))
        self.file_output_dirs = _result_output_dirs(results)
        self._set_open_button_state(self.file_open_folder_button, self.file_output_dirs)

    def open_text_output_folder(self) -> None:
        self._open_output_folder(self.text_output_dirs)

    def open_file_output_folder(self) -> None:
        self._open_output_folder(self.file_output_dirs)

    def _open_output_folder(self, dirs: list[Path]) -> None:
        if not dirs:
            return
        os.startfile(str(dirs[0]))

    def _set_open_button_state(self, button: ttk.Button | None, dirs: list[Path]) -> None:
        if button is not None:
            button.configure(state="normal" if dirs else "disabled")

    def _generation_summary(self, settings: UiSettings, source: str) -> str:
        output_dir = settings.output_dir or "mặc định"
        output_stem = settings.output_stem or "tự động"
        return (
            f"{source}\n"
            f"Model: {self.model_var.get()}; Ngôn ngữ: {self.language_var.get()}; "
            f"Profile: {self.voice_profile_var.get()}\n"
            f"Tách file: {'Có' if settings.split_output else 'Không'}; "
            f"Xuất SRT: {'Có' if settings.output_srt else 'Không'}; "
            f"Ghi đè: {'Có' if settings.overwrite else 'Không'}\n"
            f"Thư mục xuất: {output_dir}; Tên file xuất: {output_stem}"
        )

    def refresh_models(self) -> None:
        for row in self.model_table.get_children():
            self.model_table.delete(row)
        for item in self.controller.all_models():
            runtime = self.controller.service.runtime_status_for(item.model_id)
            self.model_table.insert(
                "",
                "end",
                iid=item.model_id,
                values=(
                    item.display_name,
                    item.model_type,
                    "Có" if item.required else "Không",
                    "Đã tải" if item.installed else "Chưa tải",
                    runtime.actual_device,
                    item.size_mb,
                    str(item.local_path),
                ),
            )
        self.update_runtime_label()
        self.refresh_license_status()
        self.status_var.set(self.controller.startup_notice())
        self.apply_model_capabilities()

    def update_runtime_label(self) -> None:
        model_id = self.model_map.get(self.model_var.get(), "omnivoice_vietnamese")
        self.runtime_var.set(self.controller.runtime_status_text(model_id))

    def on_model_changed(self) -> None:
        self.update_runtime_label()
        self.apply_model_capabilities()

    def apply_model_capabilities(self) -> None:
        model_id = self.model_map.get(self.model_var.get(), "omnivoice_vietnamese")
        caps = self.controller.model_capabilities(model_id)
        language_values = language_choices(caps.supported_languages)
        current_code = LANGUAGE_CODES.get(self.language_var.get(), "vi")
        if current_code not in caps.supported_languages:
            self.language_var.set(LANGUAGE_LABELS[caps.supported_languages[0]])
        for combo in self.language_combos:
            combo.configure(values=language_values, state="readonly")

        _set_widgets_state(self.speed_spins, caps.supports_speed)
        if not caps.supports_speed:
            self.speed_var.set(1.0)
        _set_widgets_state(self.pitch_spins, caps.supports_pitch_shift)
        if not caps.supports_pitch_shift:
            self.pitch_var.set(0.0)

        if caps.supports_emotion:
            values = caps.emotions or ["natural"]
            if self.emotion_var.get() not in values:
                self.emotion_var.set(values[0])
            for combo in self.emotion_combos:
                combo.configure(values=values, state="readonly")
        else:
            self.emotion_var.set("natural")
            for combo in self.emotion_combos:
                combo.configure(values=["natural"], state="disabled")

        profile_state = "readonly" if caps.supports_voice_profile else "disabled"
        for combo in self.profile_combos:
            combo.configure(state=profile_state)
        if not caps.supports_voice_profile:
            self.voice_profile_var.set("Không dùng profile")
        if caps.requires_voice_profile and self.voice_profile_var.get() == "Không dùng profile":
            self.status_var.set(f"{self.model_var.get()} cần chọn Profile giọng.")
        self.save_preferences()

    def refresh_voice_profiles(self) -> None:
        current = self.voice_profile_var.get()
        self.voice_profile_map = {"Không dùng profile": None}
        for profile in self.controller.all_voice_profiles():
            label = profile.name
            if profile.project:
                label = f"{profile.name} - {profile.project}"
            self.voice_profile_map[label] = profile.profile_id
        values = list(self.voice_profile_map.keys())
        for combo in self.voice_profile_combos:
            combo.configure(values=values)
        preferred_profile_id = self.preference_data.get("voice_profile_id")
        preferred_label = _label_for_value(self.voice_profile_map, preferred_profile_id)
        if preferred_label:
            self.voice_profile_var.set(preferred_label)
        elif current in self.voice_profile_map:
            self.voice_profile_var.set(current)
        else:
            self.voice_profile_var.set("Không dùng profile")
        self.apply_model_capabilities()

    def download_selected_model(self) -> None:
        selected = self.model_table.selection()
        if not selected:
            messagebox.showinfo("Thông báo", "Hãy chọn một model trong bảng.")
            return
        self._run_background(
            "Đang tải model...",
            lambda _progress, _cancel: self.controller.download_model(selected[0]),
            lambda result: (self.refresh_models(), messagebox.showinfo("Thông báo", result)),
        )

    def download_required_models(self) -> None:
        self._run_background(
            "Đang tải các model bắt buộc...",
            lambda _progress, _cancel: self.controller.download_required_models(),
            lambda result: (self.refresh_models(), messagebox.showinfo("Thông báo", result)),
        )

    def refresh_license_status(self) -> None:
        if self.license_panel is not None:
            self.license_panel.refresh_status()

    def _show_license_problem(self, model_id: str) -> bool:
        try:
            self.controller.validate_license_for_model(model_id)
        except OmniTtsError as exc:
            self.refresh_license_status()
            self._show_license_tab()
            messagebox.showwarning("Bản quyền", str(exc))
            return False
        return True

    def _show_license_tab(self) -> None:
        if self.notebook is None or self.license_panel is None:
            return
        self.notebook.select(self.license_panel)
        self.license_panel.focus_import_button()
        self.root.update_idletasks()

    def _run_background(self, message: str, work, on_success, log_widget: tk.Text | None = None) -> None:
        if self.active_cancel_event is not None:
            messagebox.showinfo("Thông báo", "Đang có tác vụ chạy. Hãy đợi hoặc bấm Hủy.")
            return
        cancel_event = Event()
        self.active_cancel_event = cancel_event
        self.active_log_widget = log_widget
        self.status_var.set(message)
        self.progress_var.set(0.0)
        if log_widget is not None:
            append_log(log_widget, f"Bắt đầu tác vụ: {message}")
        self._set_busy(True)
        self.root.update_idletasks()

        def report_progress(event: ProgressEvent) -> None:
            self._queue_progress(event)

        def runner() -> None:
            try:
                result = work(report_progress, cancel_event)
            except GenerationCancelled:
                self.root.after(0, self._finish_cancelled)
            except OmniTtsError as exc:
                message = f"Lỗi: {exc}"
                self.root.after(0, lambda msg=message: self._finish_error(msg))
            except Exception as exc:
                message = f"Lỗi không mong muốn: {exc}"
                self.root.after(0, lambda msg=message: self._finish_error(msg))
            else:
                self.root.after(0, lambda value=result: self._finish_success(on_success, value))

        threading.Thread(target=runner, daemon=True).start()

    def _queue_progress(self, event: ProgressEvent) -> None:
        self._pending_progress_event = event
        now = time.monotonic()
        if self._pending_progress_after and now - self._last_progress_update < 0.1:
            return
        self._pending_progress_after = True
        self.root.after(0, self._flush_progress)

    def _flush_progress(self) -> None:
        self._pending_progress_after = False
        event = self._pending_progress_event
        if event is None:
            return
        self._pending_progress_event = None
        self._last_progress_update = time.monotonic()
        self._show_progress(event)

    def cancel_current_task(self) -> None:
        if self.active_cancel_event is None:
            return
        self.active_cancel_event.set()
        self.cancel_button.configure(state="disabled")
        self.status_var.set("Đang hủy tác vụ...")

    def _show_progress(self, event: ProgressEvent) -> None:
        self.progress_var.set(event.percent)
        self.status_var.set(f"{event.message} ({event.percent:.0f}%)")
        if self.active_log_widget is not None:
            append_log(self.active_log_widget, f"{event.message} ({event.percent:.0f}%)")

    def _finish_success(self, on_success, result) -> None:
        on_success(result)
        self.progress_var.set(100.0)
        self.status_var.set("Hoàn tất.")
        if self.active_log_widget is not None:
            append_log(self.active_log_widget, "Hoàn tất tác vụ.")
        self._set_busy(False)

    def _finish_cancelled(self) -> None:
        self.status_var.set("Đã hủy tác vụ.")
        if self.active_log_widget is not None:
            append_log(self.active_log_widget, "Đã hủy tác vụ.")
        self._set_busy(False)

    def _finish_error(self, message: str) -> None:
        self.status_var.set(message)
        if self.active_log_widget is not None:
            append_log(self.active_log_widget, message)
        self._set_busy(False)

    def _set_busy(self, busy: bool) -> None:
        self.active_cancel_event = self.active_cancel_event if busy else None
        if not busy:
            self.active_log_widget = None
        state = "disabled" if busy else "normal"
        for button in self.action_buttons:
            button.configure(state=state)
        self.cancel_button.configure(state="normal" if busy else "disabled")
        if busy:
            self._start_busy_tick()
        else:
            self._stop_busy_tick()

    def _start_busy_tick(self) -> None:
        if self._busy_tick_id is not None:
            return
        self._busy_tick()

    def _busy_tick(self) -> None:
        if self.active_cancel_event is None:
            self._busy_tick_id = None
            return
        self.root.update_idletasks()
        self._busy_tick_id = self.root.after(500, self._busy_tick)

    def _stop_busy_tick(self) -> None:
        if self._busy_tick_id is not None:
            self.root.after_cancel(self._busy_tick_id)
            self._busy_tick_id = None


def _set_widgets_state(widgets: list, enabled: bool) -> None:
    state = "normal" if enabled else "disabled"
    for widget in widgets:
        widget.configure(state=state)


def _label_for_value(mapping: dict[str, str | None], value: str | None) -> str | None:
    if value is None:
        return None
    for label, item_value in mapping.items():
        if item_value == value:
            return label
    return None


def _result_output_dirs(results) -> list[Path]:
    dirs: list[Path] = []
    seen: set[Path] = set()
    for result in results:
        paths = list(result.item_audio_paths) if result.item_audio_paths else [result.audio_path]
        for path in paths:
            folder = path.parent
            if folder not in seen:
                dirs.append(folder)
                seen.add(folder)
    return dirs
