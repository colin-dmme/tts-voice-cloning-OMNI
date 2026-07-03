from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from omni_tts_shared.languages import language_choices
from omni_tts_ui_tkinter.dnd import enable_file_drop
from omni_tts_ui_tkinter.panels.contact_panel import ContactPanel
from omni_tts_ui_tkinter.panels.license_panel import LicensePanel
from omni_tts_ui_tkinter.voice_panel import VoiceProfilePanel
from omni_tts_ui_tkinter.widgets import attach_tooltip


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
        top.columnconfigure(0, weight=1)

        management_row = ttk.Frame(top)
        management_row.grid(row=0, column=0, sticky="ew")
        management_row.columnconfigure(7, weight=1)
        add_file_button = ttk.Button(management_row, text="Thêm file", command=self.add_source_files)
        add_file_button.grid(row=0, column=0, sticky="w")
        self.action_buttons.append(add_file_button)
        clipboard_button = ttk.Button(
            management_row,
            text="Dán từ clipboard",
            command=self.add_clipboard_source_files,
        )
        clipboard_button.grid(row=0, column=1, sticky="w", padx=(8, 0))
        self.action_buttons.append(clipboard_button)
        for column, text, command in (
            (2, "Xóa file chọn", self.remove_selected_source_files),
            (3, "Đặt lại trạng thái", self.reset_selected_source_files),
            (4, "Xóa theo bộ lọc", self.remove_filtered_source_files),
            (5, "Xóa toàn bộ", self.clear_source_files),
        ):
            button = ttk.Button(management_row, text=text, command=command)
            button.grid(row=0, column=column, sticky="w", padx=(8, 0))
            self.action_buttons.append(button)

        run_menu = tk.Menu(management_row, tearoff=False)
        run_menu.add_command(
            label="Chạy các file đang chờ",
            command=lambda: self.generate_from_files("pending"),
        )
        run_menu.add_command(
            label="Chạy file đã chọn",
            command=lambda: self.generate_from_files("selected"),
        )
        run_menu.add_command(
            label="Chạy lại file lỗi",
            command=lambda: self.generate_from_files("failed"),
        )
        run_menu_button = ttk.Menubutton(management_row, text="Chạy", menu=run_menu)
        run_menu_button.grid(row=0, column=6, sticky="w", padx=(8, 0))
        self.action_buttons.append(run_menu_button)

        ttk.Label(management_row, text="Hỗ trợ: .txt, .md, .srt").grid(
            row=0, column=7, sticky="e", padx=(14, 0)
        )

        path_tools_row = ttk.Frame(top)
        path_tools_row.grid(row=1, column=0, sticky="w", pady=(8, 0))
        copy_menu = self._build_result_path_menu(path_tools_row, self.copy_result_paths)
        copy_button = ttk.Menubutton(path_tools_row, text="Copy path", menu=copy_menu)
        copy_button.grid(row=0, column=0, sticky="w")
        self.action_buttons.append(copy_button)
        export_menu = self._build_result_path_menu(path_tools_row, self.export_result_paths)
        export_button = ttk.Menubutton(path_tools_row, text="Export TXT", menu=export_menu)
        export_button.grid(row=0, column=1, sticky="w", padx=(8, 0))
        self.action_buttons.append(export_button)

        filter_row = ttk.Frame(top)
        filter_row.grid(row=2, column=0, sticky="ew", pady=(8, 0))
        filter_row.columnconfigure(3, weight=1)
        ttk.Label(filter_row, text="Trạng thái").grid(row=0, column=0, sticky="w")
        status_filter = ttk.Combobox(
            filter_row,
            textvariable=self.file_filter_var,
            values=[
                "Tất cả",
                "Chờ chạy",
                "Đang chạy",
                "Thành công",
                "Lỗi",
                "Đã hủy",
                "Gián đoạn",
                "Cần chạy lại",
            ],
            state="readonly",
            width=16,
        )
        status_filter.grid(row=0, column=1, sticky="w", padx=(8, 0))
        status_filter.bind("<<ComboboxSelected>>", lambda _event: self._refresh_source_file_list())
        ttk.Label(filter_row, text="Tìm").grid(row=0, column=2, sticky="e", padx=(10, 0))
        ttk.Entry(filter_row, textvariable=self.file_search_var).grid(
            row=0, column=3, sticky="ew", padx=(8, 8)
        )

        paned = ttk.Panedwindow(tab, orient="horizontal")
        paned.grid(row=1, column=0, sticky="nsew", pady=(8, 0))

        file_pane = ttk.Frame(paned)
        file_pane.columnconfigure(0, weight=1)
        file_pane.rowconfigure(0, weight=1)
        list_frame = ttk.Frame(file_pane)
        list_frame.columnconfigure(0, weight=1)
        list_frame.rowconfigure(0, weight=1)
        list_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        columns = ("status", "file", "folder", "chars", "progress", "attempts", "result")
        self.file_list = ttk.Treeview(
            list_frame,
            columns=columns,
            show="headings",
            selectmode="extended",
            height=14,
        )
        self.file_list.heading("status", text="Trạng thái")
        self.file_list.heading("file", text="Tên file")
        self.file_list.heading("folder", text="Thư mục cha")
        self.file_list.heading("chars", text="Ký tự")
        self.file_list.heading("progress", text="Tiến độ")
        self.file_list.heading("attempts", text="Lần chạy")
        self.file_list.heading("result", text="Kết quả / lỗi")
        self.file_list.column("status", width=92, anchor="w", stretch=False)
        self.file_list.column("file", width=250, anchor="w")
        self.file_list.column("folder", width=180, anchor="w")
        self.file_list.column("chars", width=72, anchor="e", stretch=False)
        self.file_list.column("progress", width=70, anchor="e", stretch=False)
        self.file_list.column("attempts", width=68, anchor="center", stretch=False)
        self.file_list.column("result", width=220, anchor="w")
        self.file_list.grid(row=0, column=0, sticky="nsew")
        file_scroll = ttk.Scrollbar(list_frame, orient="vertical", command=self.file_list.yview)
        file_scroll.grid(row=0, column=1, sticky="ns")
        self.file_list.configure(yscrollcommand=file_scroll.set)
        self.file_list.tag_configure("pending", foreground="#444444")
        self.file_list.tag_configure("running", background="#fff4cc", foreground="#7a5200")
        self.file_list.tag_configure("done", background="#e8f5e9", foreground="#1b5e20")
        self.file_list.tag_configure("failed", background="#ffebee", foreground="#b71c1c")
        self.file_list.tag_configure("cancelled", foreground="#6d4c41")
        self.file_list.tag_configure("interrupted", background="#fff3e0", foreground="#e65100")
        self.file_list.tag_configure("outdated", background="#e3f2fd", foreground="#0d47a1")
        self.file_list.bind("<Delete>", lambda _event: self.remove_selected_source_files())
        self.file_list.bind("<Control-a>", self.select_all_visible_source_files)
        enabled = enable_file_drop(self.file_list, self.add_dropped_files)
        hint = (
            "Kéo thả file hoặc dùng các nút phía trên."
            if enabled
            else "Dùng các nút phía trên để thêm file."
        )
        ttk.Label(file_pane, text=hint).grid(row=1, column=0, sticky="w", pady=(6, 0))
        ttk.Label(file_pane, textvariable=self.file_summary_var).grid(
            row=2, column=0, sticky="w", pady=(2, 0)
        )

        right = ttk.Frame(paned)
        right.columnconfigure(0, weight=1)
        right.rowconfigure(1, weight=1)
        paned.add(file_pane, weight=3)
        paned.add(right, weight=2)
        self._remember_pane(paned, "file_pane_sash")

        self.file_generate_button = ttk.Button(
            right,
            text="Chạy các file đang chờ",
            style="Accent.TButton",
            command=lambda: self.generate_from_files("pending"),
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

    def _build_result_path_menu(self, parent: ttk.Frame, callback) -> tk.Menu:
        root_menu = tk.Menu(parent, tearoff=False)
        for scope, scope_label in (
            ("selected", "Dòng đã chọn"),
            ("all_done", "Tất cả queue thành công"),
        ):
            scope_menu = tk.Menu(root_menu, tearoff=False)
            for kind, kind_label in (
                ("all", "Tất cả kết quả"),
                ("split_dirs", "Thư mục file lẻ"),
                ("split_audio", "File audio lẻ"),
                ("merged_audio", "File gộp"),
                ("srt", "SRT"),
            ):
                scope_menu.add_command(
                    label=kind_label,
                    command=lambda selected_scope=scope, selected_kind=kind: callback(
                        selected_scope,
                        selected_kind,
                    ),
                )
            root_menu.add_cascade(label=scope_label, menu=scope_menu)
        return root_menu

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

        columns = ("name", "usage", "provider", "required", "status", "device", "size", "path")
        self.model_table = ttk.Treeview(tab, columns=columns, show="headings", height=12)
        headings = {
            "name": "Tên",
            "usage": "Dùng để làm gì",
            "provider": "Provider",
            "required": "Bắt buộc",
            "status": "Trạng thái",
            "device": "Thiết bị",
            "size": "Dung lượng",
            "path": "Nơi lưu",
        }
        for column, label in headings.items():
            self.model_table.heading(column, text=label)
            if column == "name":
                width = 240
            elif column == "usage":
                width = 320
            elif column == "path":
                width = 380
            elif column == "size":
                width = 92
            else:
                width = 110
            self.model_table.column(column, width=width)
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
            text="Gỡ model đang chọn",
            command=self.remove_selected_model,
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
        advanced_tab = ttk.Frame(controls, padding=8)
        vieneu_tab = ttk.Frame(controls, padding=8)
        f5_tab = ttk.Frame(controls, padding=8)
        chatterbox_tab = ttk.Frame(controls, padding=8)
        controls.add(basic_tab, text="Cơ bản")
        controls.add(advanced_tab, text="Nâng cao")
        controls.add(vieneu_tab, text="VieNeu")
        controls.add(f5_tab, text="F5-TTS")
        controls.add(chatterbox_tab, text="Chatterbox")

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

        ttk.Separator(basic_tab).pack(fill="x", pady=(4, 10))

        ttk.Label(basic_tab, text="Profile giọng").pack(anchor="w")
        profile_combo = ttk.Combobox(
            basic_tab,
            textvariable=self.voice_profile_var,
            values=list(self.voice_profile_map.keys()),
            state="readonly",
        )
        profile_combo.pack(fill="x", pady=(4, 4))
        profile_combo.bind("<<ComboboxSelected>>", lambda _event: self.on_voice_profile_changed())
        self.voice_profile_combos.append(profile_combo)
        self.profile_combos.append(profile_combo)

        compat_label = ttk.Label(basic_tab, textvariable=self.profile_compat_var, foreground="#555555", wraplength=340)
        compat_label.pack(anchor="w", pady=(0, 6))
        self.profile_compat_labels.append(compat_label)

        ttk.Label(basic_tab, text="Preset giọng (khi không clone)").pack(anchor="w")
        speaker_combo = ttk.Combobox(
            basic_tab,
            textvariable=self.speaker_var,
            values=list(self.speaker_map.keys()),
            state="disabled",
        )
        speaker_combo.pack(fill="x", pady=(4, 8))
        speaker_combo.bind("<<ComboboxSelected>>", lambda _event: self.on_voice_preset_changed())
        self.speaker_combos.append(speaker_combo)

        ttk.Label(basic_tab, textvariable=self.voice_source_var, foreground="#444444", wraplength=360).pack(
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

        self._build_f5_controls(f5_tab)
        self._build_chatterbox_controls(chatterbox_tab)

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
        self._spin(advanced_tab, "Nghỉ giữa câu/chunk, ms", self.pause_var, 0, 3000, 50)
        self._spin(advanced_tab, "Nghỉ giữa đoạn trong file tổng, ms", self.paragraph_pause_var, 0, 10000, 50)
        self._spin(advanced_tab, "Max ký tự mỗi đoạn nhỏ", self.chunk_var, 60, 800, 20)
        return controls

    def _build_f5_controls(self, parent: ttk.Frame) -> None:
        f5_tooltips = {
            "nfe": (
                "Số bước suy luận của F5-TTS. 16 nhanh hơn nhưng dễ kém mượt; "
                "32 là mặc định cân bằng; 48-64 có thể tốt hơn nhưng chậm hơn."
            ),
            "cfg": (
                "Độ bám vào prompt/giọng mẫu. Mặc định 2.0. Tăng quá cao có thể làm giọng gắt "
                "hoặc thiếu tự nhiên."
            ),
            "sway": (
                "Hệ số Sway Sampling điều khiển đường lấy mẫu của F5. Mặc định -1.0 theo model; "
                "chỉ đổi khi đang A/B test chất lượng."
            ),
            "crossfade": (
                "Thời gian cross-fade khi F5 phải ghép nhiều phần audio. 0.15 giây thường đủ để "
                "mối nối bớt gắt."
            ),
            "rms": (
                "Mức âm lượng chuẩn hóa của reference audio. Mặc định 0.1; đổi sai có thể làm audio "
                "quá nhỏ hoặc bị nén mạnh."
            ),
            "seed": (
                "Seed cố định giúp chạy lại ra kết quả gần giống. Để trống thì mỗi lần tạo sẽ random."
            ),
            "fix_duration": (
                "Ép tổng thời lượng F5 sinh ra. Để 0 để tự động; chỉ dùng khi cần khớp timing đặc biệt."
            ),
            "silence": (
                "Cắt khoảng lặng sau khi sinh. Có thể gọn file hơn nhưng đôi khi làm mất nhịp nghỉ tự nhiên."
            ),
        }
        self.f5_controls.append(
            self._spin(parent, "NFE step", self.f5_nfe_step_var, 4, 128, 1, tooltip=f5_tooltips["nfe"])
        )
        self.f5_controls.append(
            self._spin(parent, "CFG strength", self.f5_cfg_strength_var, 0.0, 10.0, 0.1, tooltip=f5_tooltips["cfg"])
        )
        self.f5_controls.append(
            self._spin(
                parent,
                "Sway sampling coef",
                self.f5_sway_sampling_coef_var,
                -5.0,
                5.0,
                0.1,
                tooltip=f5_tooltips["sway"],
            )
        )
        self.f5_controls.append(
            self._spin(
                parent,
                "Cross-fade duration, giây",
                self.f5_cross_fade_duration_var,
                0.0,
                2.0,
                0.05,
                tooltip=f5_tooltips["crossfade"],
            )
        )
        self.f5_controls.append(
            self._spin(parent, "Target RMS", self.f5_target_rms_var, 0.01, 1.0, 0.01, tooltip=f5_tooltips["rms"])
        )
        self.f5_controls.append(
            self._spin(
                parent,
                "Fix duration, giây (0 = tự động)",
                self.f5_fix_duration_var,
                0.0,
                120.0,
                0.1,
                tooltip=f5_tooltips["fix_duration"],
            )
        )
        ttk.Label(parent, text="Seed (trống = random)").pack(anchor="w")
        seed_entry = ttk.Entry(parent, textvariable=self.f5_seed_var)
        seed_entry.pack(fill="x", pady=(4, 8))
        attach_tooltip(seed_entry, f5_tooltips["seed"])
        self.f5_controls.append(seed_entry)
        silence_check = ttk.Checkbutton(
            parent,
            text="Remove silence",
            variable=self.f5_remove_silence_var,
            command=self.save_preferences,
        )
        silence_check.pack(anchor="w", pady=(2, 8))
        attach_tooltip(silence_check, f5_tooltips["silence"])
        self.f5_controls.append(silence_check)

    def _build_chatterbox_controls(self, parent: ttk.Frame) -> None:
        chatterbox_tooltips = {
            "temperature": (
                "Độ ngẫu nhiên khi Chatterbox chọn token giọng. Mặc định 0.8; tăng thì đa dạng hơn "
                "nhưng dễ lệch, giảm thì ổn định hơn nhưng có thể đều."
            ),
            "top_p": (
                "Giới hạn nhóm token có tổng xác suất cao nhất. Mặc định 0.95; chỉ giảm khi audio "
                "bị quá ngẫu nhiên hoặc phát âm lạc."
            ),
            "top_k": (
                "Số lựa chọn token tối đa mỗi bước. Mặc định 1000 theo Turbo; giảm mạnh có thể làm "
                "giọng kém tự nhiên."
            ),
            "repetition": (
                "Phạt lặp token để tránh nói lặp/kẹt nhịp. Mặc định 1.2 theo bản Turbo mới; tăng nhẹ "
                "nếu nghe bị lặp từ."
            ),
            "seed": (
                "Seed cố định giúp chạy lại ra kết quả gần giống. Để trống thì mỗi lần tạo sẽ random."
            ),
            "loudness": (
                "Chuẩn hóa độ lớn audio mẫu trước khi clone. Nên bật để giọng mẫu quá nhỏ/quá lớn "
                "không làm lệch kết quả."
            ),
            "tags": (
                "Turbo hiểu tag trong text như [laugh], [chuckle], [sigh], [gasp], [cough], "
                "[whisper], [breath]. Chỉ dùng khi cần hiệu ứng biểu cảm."
            ),
        }
        ttk.Label(
            parent,
            text="Clone voice tiếng Anh bằng Profile >=5 giây. Có thể dùng tag như [laugh], [chuckle], [sigh].",
            wraplength=340,
            foreground="#444444",
        ).pack(anchor="w", pady=(0, 8))
        self.chatterbox_controls.append(
            self._spin(
                parent,
                "Temperature",
                self.chatterbox_temperature_var,
                0.1,
                2.0,
                0.05,
                tooltip=chatterbox_tooltips["temperature"],
            )
        )
        self.chatterbox_controls.append(
            self._spin(
                parent,
                "Top-P",
                self.chatterbox_top_p_var,
                0.05,
                1.0,
                0.01,
                tooltip=chatterbox_tooltips["top_p"],
            )
        )
        self.chatterbox_controls.append(
            self._spin(parent, "Top-K", self.chatterbox_top_k_var, 1, 2000, 10, tooltip=chatterbox_tooltips["top_k"])
        )
        self.chatterbox_controls.append(
            self._spin(
                parent,
                "Repetition penalty",
                self.chatterbox_repetition_penalty_var,
                1.0,
                3.0,
                0.05,
                tooltip=chatterbox_tooltips["repetition"],
            )
        )
        ttk.Label(parent, text="Seed (trống = random)").pack(anchor="w")
        seed_entry = ttk.Entry(parent, textvariable=self.chatterbox_seed_var)
        seed_entry.pack(fill="x", pady=(4, 8))
        attach_tooltip(seed_entry, chatterbox_tooltips["seed"])
        self.chatterbox_controls.append(seed_entry)
        loudness_check = ttk.Checkbutton(
            parent,
            text="Normalize loudness",
            variable=self.chatterbox_norm_loudness_var,
            command=self.save_preferences,
        )
        loudness_check.pack(anchor="w", pady=(2, 8))
        attach_tooltip(loudness_check, chatterbox_tooltips["loudness"])
        self.chatterbox_controls.append(loudness_check)
        tag_label = ttk.Label(parent, text="Tags: [laugh] [chuckle] [sigh] [gasp] [cough] [whisper] [breath]")
        tag_label.pack(anchor="w", pady=(4, 0))
        attach_tooltip(tag_label, chatterbox_tooltips["tags"])
        self.chatterbox_controls.append(tag_label)

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

        ttk.Label(frame, text="Định dạng audio").grid(row=row, column=0, sticky="w", pady=2)
        format_row = ttk.Frame(frame)
        format_row.grid(row=row, column=1, sticky="w", padx=(8, 0), pady=2)
        ttk.Combobox(
            format_row,
            textvariable=self.output_audio_format_var,
            values=list(self.output_audio_format_map.keys()),
            state="readonly",
            width=10,
        ).pack(side="left")
        ttk.Label(format_row, text="Bitrate MP3").pack(side="left", padx=(12, 4))
        bitrate_combo = ttk.Combobox(
            format_row,
            textvariable=self.mp3_bitrate_var,
            values=[128, 160, 192, 256, 320],
            state="readonly",
            width=8,
        )
        bitrate_combo.pack(side="left")
        ttk.Label(format_row, text="kbps").pack(side="left", padx=(4, 0))
        self.mp3_bitrate_combos.append(bitrate_combo)
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
            text="Tách dòng SRT/đoạn văn thành file riêng",
            variable=self.split_output_var,
            command=self.on_split_output_changed,
        ).pack(side="left", padx=(14, 0))
        ttk.Checkbutton(
            checks,
            text="Xuất kèm SRT",
            variable=self.output_srt_var,
            command=self.save_preferences,
        ).pack(side="left", padx=(14, 0))
        join_check = ttk.Checkbutton(
            checks,
            text="Tạo thêm file audio tổng",
            variable=self.join_split_audio_var,
            command=self.save_preferences,
        )
        join_check.pack(side="left", padx=(14, 0))
        self.join_split_audio_checks.append(join_check)

        open_button = ttk.Button(
            checks,
            text="Mở thư mục audio",
            command=open_command,
            state="disabled",
        )
        open_button.pack(side="right")
        setattr(self, button_attr, open_button)
        return frame

    def _spin(
        self,
        parent,
        label: str,
        variable: tk.Variable,
        from_: float,
        to: float,
        step: float,
        tooltip: str = "",
    ):
        label_widget = ttk.Label(parent, text=label)
        label_widget.pack(anchor="w")
        spin = ttk.Spinbox(parent, textvariable=variable, from_=from_, to=to, increment=step)
        spin.pack(fill="x", pady=(4, 8))
        if tooltip:
            attach_tooltip(label_widget, tooltip)
            attach_tooltip(spin, tooltip)
        return spin
