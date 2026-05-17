from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from omni_tts_shared.languages import language_choices
from omni_tts_ui_tkinter.dnd import enable_file_drop
from omni_tts_ui_tkinter.panels.contact_panel import ContactPanel
from omni_tts_ui_tkinter.panels.license_panel import LicensePanel
from omni_tts_ui_tkinter.voice_panel import VoiceProfilePanel


class GenerationTabsMixin:
    def _build_text_tab(self, notebook: ttk.Notebook) -> None:
        tab = ttk.Frame(notebook, padding=10)
        tab.columnconfigure(0, weight=1)
        tab.rowconfigure(0, weight=1)
        notebook.add(tab, text="Tạo từ văn bản")

        paned = ttk.Panedwindow(tab, orient="horizontal")
        paned.grid(row=0, column=0, sticky="nsew")

        input_pane = ttk.Frame(paned)
        input_pane.columnconfigure(0, weight=1)
        input_pane.rowconfigure(0, weight=1)
        self.text_input = tk.Text(input_pane, wrap="word", height=18, undo=True)
        self.text_input.grid(row=0, column=0, sticky="nsew", padx=(0, 8))

        side = ttk.Frame(paned)
        side.columnconfigure(0, weight=1)
        side.rowconfigure(1, weight=1)
        paned.add(input_pane, weight=3)
        paned.add(side, weight=2)
        self._remember_pane(paned, "text_pane_sash")

        self.text_generate_button = ttk.Button(
            side,
            text="Tạo audio",
            style="Accent.TButton",
            command=self.generate_from_text,
        )
        self.text_generate_button.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        self.action_buttons.append(self.text_generate_button)

        self._build_common_controls(side).grid(row=1, column=0, sticky="nsew")

        self._build_output_controls(
            tab,
            include_output_stem=True,
            open_command=self.open_text_output_folder,
            button_attr="text_open_folder_button",
        ).grid(row=1, column=0, sticky="ew", pady=(10, 0))
        self._build_log_header(tab, self.clear_text_log).grid(
            row=2, column=0, sticky="ew", pady=(10, 0)
        )
        self.text_log = tk.Text(tab, height=7, state="disabled", wrap="word")
        self.text_log.grid(row=3, column=0, sticky="nsew", pady=(4, 0))

    def _build_file_tab(self, notebook: ttk.Notebook) -> None:
        tab = ttk.Frame(notebook, padding=10)
        tab.columnconfigure(0, weight=1)
        tab.rowconfigure(1, weight=1)
        notebook.add(tab, text="Xử lý file")

        top = ttk.Frame(tab)
        top.grid(row=0, column=0, columnspan=2, sticky="ew")
        ttk.Button(top, text="Thêm file", command=self.add_source_files).pack(side="left")
        ttk.Button(top, text="Xóa danh sách", command=self.clear_source_files).pack(
            side="left", padx=(8, 0)
        )
        ttk.Label(top, text="Hỗ trợ: .txt, .md, .srt").pack(side="left", padx=(14, 0))

        paned = ttk.Panedwindow(tab, orient="horizontal")
        paned.grid(row=1, column=0, sticky="nsew", pady=(8, 0))

        file_pane = ttk.Frame(paned)
        file_pane.columnconfigure(0, weight=1)
        file_pane.rowconfigure(0, weight=1)
        self.file_list = tk.Listbox(file_pane, selectmode="extended", height=14)
        self.file_list.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        enabled = enable_file_drop(self.file_list, self.add_dropped_files)
        hint = "Kéo thả một hoặc nhiều file vào danh sách." if enabled else (
            "Bấm Thêm file để chọn một hoặc nhiều file nguồn."
        )
        ttk.Label(file_pane, text=hint).grid(row=1, column=0, sticky="w", pady=(6, 0))

        right = ttk.Frame(paned)
        right.columnconfigure(0, weight=1)
        right.rowconfigure(1, weight=1)
        paned.add(file_pane, weight=3)
        paned.add(right, weight=2)
        self._remember_pane(paned, "file_pane_sash")

        self.file_generate_button = ttk.Button(
            right,
            text="Tạo audio cho các file",
            style="Accent.TButton",
            command=self.generate_from_files,
        )
        self.file_generate_button.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        self.action_buttons.append(self.file_generate_button)
        self._build_common_controls(right, include_output_stem=False).grid(
            row=1,
            column=0,
            sticky="nsew",
        )

        self._build_output_controls(
            tab,
            include_output_stem=False,
            open_command=self.open_file_output_folder,
            button_attr="file_open_folder_button",
        ).grid(row=2, column=0, sticky="ew", pady=(10, 0))
        self._build_log_header(tab, self.clear_file_log).grid(
            row=3, column=0, sticky="ew", pady=(10, 0)
        )
        self.file_log = tk.Text(tab, height=8, state="disabled", wrap="word")
        self.file_log.grid(row=4, column=0, sticky="nsew", pady=(4, 0))

    def _build_log_header(self, parent: ttk.Frame, clear_command) -> ttk.Frame:
        header = ttk.Frame(parent)
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text="Nhật ký").grid(row=0, column=0, sticky="w")
        ttk.Button(header, text="Xóa nhật ký", command=clear_command).grid(
            row=0, column=1, sticky="e"
        )
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
        ttk.Button(
            controls,
            text="Cài tăng tốc GPU cho model đang chọn",
            command=self.install_gpu_for_selected_model,
        ).pack(side="left", padx=(8, 0))
        ttk.Button(controls, text="Làm mới", command=self.refresh_models).pack(
            side="left", padx=(8, 0)
        )
        ttk.Button(
            controls,
            text="Xem catalog model",
            command=self.controller.open_model_catalog,
        ).pack(side="right")

    def _build_voice_profile_tab(self, notebook: ttk.Notebook) -> None:
        panel = VoiceProfilePanel(notebook, self.controller, self.refresh_voice_profiles)
        notebook.add(panel, text="Profile giọng")

    def _build_license_tab(self, notebook: ttk.Notebook) -> None:
        self.license_panel = LicensePanel(notebook, self.controller, self.status_var.set)
        notebook.add(self.license_panel, text="Bản quyền")

    def _build_contact_tab(self, notebook: ttk.Notebook) -> None:
        tab = ContactPanel(notebook, self.controller.service.settings, self.status_var)
        notebook.add(tab, text="Liên hệ")

    def _build_common_controls(self, parent: ttk.Frame, include_output_stem: bool = True) -> ttk.Notebook:
        controls = ttk.Notebook(parent)

        basic_tab = ttk.Frame(controls, padding=8)
        voice_tab = ttk.Frame(controls, padding=8)
        vieneu_tab = ttk.Frame(controls, padding=8)
        advanced_tab = ttk.Frame(controls, padding=8)
        controls.add(basic_tab, text="Cơ bản")
        controls.add(voice_tab, text="Giọng")
        controls.add(vieneu_tab, text="VieNeu")
        controls.add(advanced_tab, text="Nâng cao")

        ttk.Label(basic_tab, text="Model TTS").pack(anchor="w")
        model_combo = ttk.Combobox(
            basic_tab,
            textvariable=self.model_var,
            values=list(self.model_map.keys()),
            state="readonly",
        )
        model_combo.pack(fill="x", pady=(4, 8))
        model_combo.bind("<<ComboboxSelected>>", lambda _event: self.on_model_changed())

        ttk.Label(basic_tab, textvariable=self.model_info_var, foreground="#333333", wraplength=360).pack(
            anchor="w", pady=(0, 6)
        )
        ttk.Label(basic_tab, textvariable=self.runtime_var, foreground="#555555", wraplength=360).pack(
            anchor="w", pady=(0, 8)
        )

        ttk.Label(basic_tab, text="Ngôn ngữ").pack(anchor="w")
        language_combo = ttk.Combobox(
            basic_tab,
            textvariable=self.language_var,
            values=language_choices(["vi", "en"]),
            state="readonly",
        )
        language_combo.pack(fill="x", pady=(4, 8))
        self.language_combos.append(language_combo)

        ttk.Label(voice_tab, text="Profile giọng").pack(anchor="w")
        profile_combo = ttk.Combobox(
            voice_tab,
            textvariable=self.voice_profile_var,
            values=list(self.voice_profile_map.keys()),
            state="readonly",
        )
        profile_combo.pack(fill="x", pady=(4, 4))
        profile_combo.bind("<<ComboboxSelected>>", lambda _event: self.on_voice_profile_changed())
        self.voice_profile_combos.append(profile_combo)
        self.profile_combos.append(profile_combo)

        compat_label = ttk.Label(voice_tab, textvariable=self.profile_compat_var, foreground="#555555", wraplength=340)
        compat_label.pack(anchor="w", pady=(0, 6))
        self.profile_compat_labels.append(compat_label)

        ttk.Label(voice_tab, text="Preset giọng (khi không clone)").pack(anchor="w")
        speaker_combo = ttk.Combobox(
            voice_tab,
            textvariable=self.speaker_var,
            values=list(self.speaker_map.keys()),
            state="disabled",
        )
        speaker_combo.pack(fill="x", pady=(4, 8))
        speaker_combo.bind("<<ComboboxSelected>>", lambda _event: self.on_voice_preset_changed())
        self.speaker_combos.append(speaker_combo)

        ttk.Label(voice_tab, textvariable=self.voice_source_var, foreground="#444444", wraplength=360).pack(
            anchor="w", pady=(0, 8)
        )

        ttk.Label(vieneu_tab, text="Codec VieNeu").pack(anchor="w")
        codec_combo = ttk.Combobox(
            vieneu_tab,
            textvariable=self.codec_var,
            values=list(self.codec_map.keys()),
            state="disabled",
        )
        codec_combo.pack(fill="x", pady=(4, 8))
        self.codec_combos.append(codec_combo)

        self.sampling_spins.append(
            self._spin(vieneu_tab, "Temperature VieNeu", self.temperature_var, 0.1, 2.0, 0.1)
        )
        self.sampling_spins.append(self._spin(vieneu_tab, "Top-K VieNeu", self.top_k_var, 1, 200, 1))
        ttk.Label(vieneu_tab, text="Cảm xúc VieNeu").pack(anchor="w")
        emotion_combo = ttk.Combobox(
            vieneu_tab,
            textvariable=self.emotion_var,
            values=["natural", "storytelling"],
            state="readonly",
        )
        emotion_combo.pack(fill="x", pady=(4, 8))
        self.emotion_combos.append(emotion_combo)

        self.speed_spins.append(self._spin(advanced_tab, "Tốc độ đọc", self.speed_var, 0.5, 1.8, 0.05))
        self.pitch_spins.append(self._spin(advanced_tab, "Pitch shift", self.pitch_var, -12.0, 12.0, 0.5))
        ttk.Label(advanced_tab, text="Thiết bị xử lý").pack(anchor="w")
        runtime_combo = ttk.Combobox(
            advanced_tab,
            textvariable=self.runtime_target_var,
            values=list(self.runtime_target_map.keys()),
            state="readonly",
        )
        runtime_combo.pack(fill="x", pady=(4, 8))
        self._spin(advanced_tab, "Silence Pad, ms", self.pause_var, 0, 3000, 50)
        self._spin(advanced_tab, "Max Chars mỗi đoạn", self.chunk_var, 60, 800, 20)
        return controls

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

    def _spin(self, parent, label: str, variable: tk.Variable, from_: float, to: float, step: float):
        ttk.Label(parent, text=label).pack(anchor="w")
        spin = ttk.Spinbox(parent, textvariable=variable, from_=from_, to=to, increment=step)
        spin.pack(fill="x", pady=(4, 8))
        return spin
