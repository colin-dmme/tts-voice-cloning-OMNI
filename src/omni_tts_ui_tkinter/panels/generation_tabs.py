from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from omni_tts_core.ui_presenters import field_limits, model_actions
from omni_tts_core.ui_presenters.control_policy import (
    TUNING_CHATTERBOX,
    TUNING_F5,
    TUNING_VIENEU,
)
from omni_tts_core.ui_presenters.tooltips import tooltip
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
        tab.rowconfigure(1, weight=1)
        tab.rowconfigure(3, weight=0)
        notebook.add(tab, text="Quản lý model")

        # Provider-first classification, same logic as the generation form.
        filter_row = ttk.Frame(tab)
        filter_row.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        ttk.Label(filter_row, text="Nhà cung cấp:").pack(side="left")
        self.model_filter_combo = ttk.Combobox(
            filter_row,
            textvariable=self.model_filter_var,
            values=list(self.model_filter_map.keys()),
            state="readonly",
            width=24,
        )
        self.model_filter_combo.pack(side="left", padx=(6, 12))
        self.model_filter_combo.bind("<<ComboboxSelected>>", lambda _event: self.refresh_model_table())
        attach_tooltip(
            self.model_filter_combo,
            "Lọc bảng theo nhà cung cấp. Bảng luôn nhóm theo nhà cung cấp rồi xếp theo tên.",
        )
        ttk.Label(filter_row, text="Tìm:").pack(side="left")
        search_entry = ttk.Entry(filter_row, textvariable=self.model_search_var, width=28)
        search_entry.pack(side="left", padx=(6, 12))
        self.model_search_var.trace_add("write", lambda *_: self.refresh_model_table())
        ttk.Label(filter_row, textvariable=self.model_summary_var, foreground="#555555").pack(
            side="left"
        )

        columns = ("name", "usage", "provider", "required", "status", "device", "size", "path")
        # extended: Ctrl/Shift click to act on several models at once.
        self.model_table = ttk.Treeview(
            tab, columns=columns, show="headings", height=12, selectmode="extended"
        )
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
        self.model_table.grid(row=1, column=0, sticky="nsew")
        self.model_table.bind("<<TreeviewSelect>>", lambda _event: self._on_model_selection())

        controls = ttk.Frame(tab)
        controls.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        button_specs = [
            (model_actions.DOWNLOAD, "Tải model đang chọn", self.download_selected_model),
            (model_actions.DOWNLOAD_REQUIRED, "Tải model bắt buộc còn thiếu",
             self.download_required_models),
            (model_actions.REMOVE, "Gỡ model đang chọn", self.remove_selected_model),
            (model_actions.INSTALL_WORKER, "Cài worker/môi trường",
             self.install_base_for_selected_model),
            (model_actions.INSTALL_GPU, "Cài GPU/CUDA", self.install_gpu_for_selected_model),
            (model_actions.OPEN_STORAGE, "Mở nơi lưu", self.open_selected_model_storage),
            (model_actions.REFRESH, "Làm mới", self.refresh_models),
        ]
        for index, (action, label, command) in enumerate(button_specs):
            button = ttk.Button(controls, text=label, command=command)
            button.pack(side="left", padx=(0 if index == 0 else 8, 0))
            self.model_action_buttons[action] = button
        catalog_button = ttk.Button(
            controls,
            text="Xem catalog model",
            command=self.controller.open_model_catalog,
        )
        catalog_button.pack(side="right")
        self.model_action_buttons[model_actions.CATALOG] = catalog_button
        self.update_model_action_states()

        setup_frame = ttk.LabelFrame(tab, text="Kiểm tra máy và model đang chọn", padding=8)
        setup_frame.grid(row=3, column=0, sticky="ew", pady=(10, 0))
        setup_frame.columnconfigure(0, weight=1)
        setup_columns = ("scope", "item", "status", "action", "detail")
        self.setup_table = ttk.Treeview(
            setup_frame,
            columns=setup_columns,
            show="headings",
            height=7,
        )
        setup_headings = {
            "scope": "Nhóm",
            "item": "Mục",
            "status": "Trạng thái",
            "action": "Có thể bấm",
            "detail": "Chi tiết",
        }
        for column, label in setup_headings.items():
            self.setup_table.heading(column, text=label)
        self.setup_table.column("scope", width=98, stretch=False)
        self.setup_table.column("item", width=190, stretch=False)
        self.setup_table.column("status", width=105, stretch=False)
        self.setup_table.column("action", width=130, stretch=False)
        self.setup_table.column("detail", width=620)
        self.setup_table.grid(row=0, column=0, sticky="ew")

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
        punctuation_tab = ttk.Frame(controls, padding=8)
        vieneu_tab = ttk.Frame(controls, padding=8)
        f5_tab = ttk.Frame(controls, padding=8)
        chatterbox_tab = ttk.Frame(controls, padding=8)
        gpu_tab = ttk.Frame(controls, padding=8)
        controls.add(basic_tab, text="Cơ bản")
        controls.add(advanced_tab, text="Nâng cao")
        controls.add(punctuation_tab, text="Dấu câu")
        controls.add(vieneu_tab, text="VieNeu")
        controls.add(f5_tab, text="F5-TTS")
        controls.add(chatterbox_tab, text="Chatterbox")
        # Bảo vệ GPU is global (every CUDA provider), so it is its own tab rather
        # than a page inside Chatterbox as it used to be.
        controls.add(gpu_tab, text="Bảo vệ GPU")
        # Provider tabs are hidden for models that do not use them; the app layer
        # drives this from `policy.tuning_groups`, the GUI only stores the refs.
        self.tuning_tab_groups.append(
            (
                controls,
                {
                    TUNING_VIENEU: vieneu_tab,
                    TUNING_F5: f5_tab,
                    TUNING_CHATTERBOX: chatterbox_tab,
                },
            )
        )
        self.punctuation_tab_groups.append((controls, punctuation_tab))

        ttk.Label(basic_tab, text="Nhà cung cấp").pack(anchor="w")
        provider_combo = ttk.Combobox(
            basic_tab,
            textvariable=self.provider_var,
            values=list(self.provider_map.keys()),
            state="readonly",
        )
        provider_combo.pack(fill="x", pady=(4, 8))
        provider_combo.bind("<<ComboboxSelected>>", lambda _event: self.on_provider_changed())
        attach_tooltip(provider_combo, tooltip("provider"))
        self.provider_combos.append(provider_combo)

        ttk.Label(basic_tab, text="Model TTS").pack(anchor="w")
        model_combo = ttk.Combobox(
            basic_tab,
            textvariable=self.model_var,
            values=list(self.model_map.keys()),
            state="readonly",
        )
        model_combo.pack(fill="x", pady=(4, 8))
        model_combo.bind("<<ComboboxSelected>>", lambda _event: self.on_model_changed())
        attach_tooltip(model_combo, tooltip("model"))
        self.model_combos.append(model_combo)

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
        attach_tooltip(language_combo, tooltip("language"))
        self.language_combos.append(language_combo)

        ttk.Separator(basic_tab).pack(fill="x", pady=(4, 10))

        voice_controls = ttk.Frame(basic_tab)
        voice_controls.pack(fill="x")
        voice_controls.columnconfigure(0, weight=1)

        voice_mode_frame = ttk.Frame(voice_controls)
        voice_mode_frame.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        ttk.Label(voice_mode_frame, text="Nguồn giọng").pack(anchor="w")
        fixed_mode = ttk.Radiobutton(
            voice_mode_frame,
            text="Giọng cố định",
            value="fixed",
            variable=self.voice_source_mode_var,
            command=self.on_voice_source_mode_changed,
        )
        fixed_mode.pack(side="left", pady=(4, 0))
        profile_mode = ttk.Radiobutton(
            voice_mode_frame,
            text="Clone từ Profile",
            value="profile",
            variable=self.voice_source_mode_var,
            command=self.on_voice_source_mode_changed,
        )
        profile_mode.pack(side="left", padx=(14, 0), pady=(4, 0))
        attach_tooltip(fixed_mode, tooltip("voice_mode_fixed"))
        attach_tooltip(profile_mode, tooltip("voice_mode_profile"))
        self.voice_mode_frames.append(voice_mode_frame)

        profile_frame = ttk.Frame(voice_controls)
        profile_frame.grid(row=1, column=0, sticky="ew")
        profile_label = ttk.Label(profile_frame, text="Profile giọng")
        profile_label.pack(anchor="w")
        profile_combo = ttk.Combobox(
            profile_frame,
            textvariable=self.voice_profile_var,
            values=list(self.voice_profile_map.keys()),
            state="readonly",
        )
        profile_combo.pack(fill="x", pady=(4, 4))
        profile_combo.bind("<<ComboboxSelected>>", lambda _event: self.on_voice_profile_changed())
        self.voice_profile_combos.append(profile_combo)
        self.profile_combos.append(profile_combo)
        self.profile_voice_frames.append(profile_frame)
        self.profile_voice_labels.append(profile_label)
        attach_tooltip(profile_label, tooltip("voice_profile"))

        compat_label = ttk.Label(profile_frame, textvariable=self.profile_compat_var, foreground="#555555", wraplength=340)
        compat_label.pack(anchor="w", pady=(0, 6))
        self.profile_compat_labels.append(compat_label)

        fixed_frame = ttk.Frame(voice_controls)
        fixed_frame.grid(row=2, column=0, sticky="ew")
        fixed_label = ttk.Label(fixed_frame, text="Giọng cố định")
        fixed_label.pack(anchor="w")
        speaker_combo = ttk.Combobox(
            fixed_frame,
            textvariable=self.speaker_var,
            values=list(self.speaker_map.keys()),
            state="disabled",
        )
        speaker_combo.pack(fill="x", pady=(4, 8))
        speaker_combo.bind("<<ComboboxSelected>>", lambda _event: self.on_voice_preset_changed())
        self.speaker_combos.append(speaker_combo)
        self.fixed_voice_frames.append(fixed_frame)
        self.fixed_voice_labels.append(fixed_label)
        attach_tooltip(fixed_label, tooltip("voice_fixed"))

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
        attach_tooltip(codec_combo, tooltip("vieneu_codec"))
        self.codec_combos.append(codec_combo)

        self.sampling_spins.append(
            self._field_spin(vieneu_tab, "Temperature VieNeu", self.temperature_var,
                             "temperature", "vieneu_temperature")
        )
        self.sampling_spins.append(
            self._field_spin(vieneu_tab, "Top-K VieNeu", self.top_k_var, "top_k", "vieneu_top_k")
        )
        ttk.Label(vieneu_tab, text="Cảm xúc VieNeu").pack(anchor="w")
        emotion_combo = ttk.Combobox(
            vieneu_tab,
            textvariable=self.emotion_var,
            values=["natural", "storytelling"],
            state="readonly",
        )
        emotion_combo.pack(fill="x", pady=(4, 8))
        attach_tooltip(emotion_combo, tooltip("vieneu_emotion"))
        self.emotion_combos.append(emotion_combo)

        self._build_f5_controls(f5_tab)
        self._build_chatterbox_controls(chatterbox_tab)
        self._build_gpu_safety_controls(gpu_tab)
        self._build_punctuation_controls(punctuation_tab)

        self.speed_spins.append(
            self._field_spin(advanced_tab, "Tốc độ đọc", self.speed_var, "speed", "speed")
        )
        self.pitch_spins.append(
            self._field_spin(advanced_tab, "Pitch shift", self.pitch_var, "pitch_shift", "pitch")
        )
        ttk.Label(advanced_tab, text="Thiết bị xử lý").pack(anchor="w")
        runtime_combo = ttk.Combobox(
            advanced_tab,
            textvariable=self.runtime_target_var,
            values=list(self.runtime_target_map.keys()),
            state="readonly",
        )
        runtime_combo.pack(fill="x", pady=(4, 8))
        self.runtime_target_combos.append(runtime_combo)
        attach_tooltip(runtime_combo, tooltip("device"))
        self._field_spin(advanced_tab, "Nghỉ giữa chunk kỹ thuật, ms",
                         self.chunk_pause_var, "chunk_pause_ms", "chunk_pause")
        self._field_spin(advanced_tab, "Nghỉ giữa đoạn trong file tổng, ms",
                         self.paragraph_pause_var, "paragraph_pause_ms", "paragraph_pause")
        self._field_spin(advanced_tab, "Max ký tự mỗi đoạn nhỏ", self.chunk_var,
                         "max_chunk_chars", "max_chunk")
        return controls

    def _build_punctuation_controls(self, parent: ttk.Frame) -> None:
        note = ttk.Label(
            parent,
            text=(
                "Chỉ hiện với provider đã có implementation kiểm thử. "
                "Đặt 0 ms để bỏ nghỉ ở một loại dấu."
            ),
            wraplength=350,
            foreground="#555555",
        )
        note.pack(anchor="w", pady=(0, 8))
        attach_tooltip(note, tooltip("punctuation_section"))
        enabled = ttk.Checkbutton(
            parent,
            text="ACTIVE · Áp dụng ngắt nghỉ theo dấu câu",
            variable=self.punctuation_pause_enabled_var,
            command=self._sync_punctuation_controls,
        )
        enabled.pack(anchor="w", pady=(0, 8))
        attach_tooltip(enabled, tooltip("punctuation_section"))
        self.punctuation_enable_checks.append(enabled)
        for label, variable, field, tooltip_key in (
            ("Cuối câu · . ? ! (ms)", self.pause_var,
             "sentence_pause_ms", "sentence_pause"),
            ("Dấu phẩy · , (ms)", self.comma_pause_var,
             "comma_pause_ms", "comma_pause"),
            ("Chấm phẩy / hai chấm · ; : (ms)", self.clause_pause_var,
             "clause_pause_ms", "clause_pause"),
            ("Dấu ba chấm · … / ... (ms)", self.ellipsis_pause_var,
             "ellipsis_pause_ms", "ellipsis_pause"),
        ):
            self.punctuation_controls.append(
                self._field_spin(parent, label, variable, field, tooltip_key)
            )
        reset = ttk.Button(
            parent,
            text="Đặt lại ngắt nghỉ mặc định",
            command=self._apply_punctuation_defaults,
        )
        reset.pack(fill="x", pady=(2, 0))
        attach_tooltip(reset, tooltip("punctuation_reset"))
        self.punctuation_reset_buttons.append(reset)

    def _build_f5_controls(self, parent: ttk.Frame) -> None:
        for label, variable, field, tooltip_key in (
            ("NFE step", self.f5_nfe_step_var, "f5_nfe_step", "f5_nfe"),
            ("CFG strength", self.f5_cfg_strength_var, "f5_cfg_strength", "f5_cfg"),
            ("Sway sampling coef", self.f5_sway_sampling_coef_var,
             "f5_sway_sampling_coef", "f5_sway"),
            ("Cross-fade duration, giây", self.f5_cross_fade_duration_var,
             "f5_cross_fade_duration", "f5_crossfade"),
            ("Target RMS", self.f5_target_rms_var, "f5_target_rms", "f5_rms"),
            ("Fix duration, giây (0 = tự động)", self.f5_fix_duration_var,
             "f5_fix_duration", "f5_fix_duration"),
        ):
            self.f5_controls.append(
                self._field_spin(parent, label, variable, field, tooltip_key)
            )
        ttk.Label(parent, text="Seed (trống = random)").pack(anchor="w")
        seed_entry = ttk.Entry(parent, textvariable=self.f5_seed_var)
        seed_entry.pack(fill="x", pady=(4, 8))
        attach_tooltip(seed_entry, tooltip("f5_seed"))
        self.f5_controls.append(seed_entry)
        silence_check = ttk.Checkbutton(
            parent,
            text="Remove silence",
            variable=self.f5_remove_silence_var,
            command=self.save_preferences,
        )
        silence_check.pack(anchor="w", pady=(2, 8))
        attach_tooltip(silence_check, tooltip("f5_remove_silence"))
        self.f5_controls.append(silence_check)

    def _build_chatterbox_controls(self, parent: ttk.Frame) -> None:
        ttk.Label(
            parent,
            text="Clone voice tiếng Anh bằng Profile >=5 giây. Có thể dùng tag như [laugh], [chuckle], [sigh].",
            wraplength=340,
            foreground="#444444",
        ).pack(anchor="w", pady=(0, 8))
        for label, variable, field, tooltip_key in (
            ("Temperature", self.chatterbox_temperature_var,
             "chatterbox_temperature", "chatterbox_temperature"),
            ("Top-P", self.chatterbox_top_p_var, "chatterbox_top_p", "chatterbox_top_p"),
            ("Top-K", self.chatterbox_top_k_var, "chatterbox_top_k", "chatterbox_top_k"),
            ("Repetition penalty", self.chatterbox_repetition_penalty_var,
             "chatterbox_repetition_penalty", "chatterbox_repetition"),
        ):
            self.chatterbox_controls.append(
                self._field_spin(parent, label, variable, field, tooltip_key)
            )
        ttk.Label(parent, text="Seed (trống = random)").pack(anchor="w")
        seed_entry = ttk.Entry(parent, textvariable=self.chatterbox_seed_var)
        seed_entry.pack(fill="x", pady=(4, 8))
        attach_tooltip(seed_entry, tooltip("chatterbox_seed"))
        self.chatterbox_controls.append(seed_entry)
        loudness_check = ttk.Checkbutton(
            parent,
            text="Normalize loudness",
            variable=self.chatterbox_norm_loudness_var,
            command=self.save_preferences,
        )
        loudness_check.pack(anchor="w", pady=(2, 8))
        attach_tooltip(loudness_check, tooltip("chatterbox_norm_loudness"))
        self.chatterbox_controls.append(loudness_check)
        tag_label = ttk.Label(parent, text="Tags: [laugh] [chuckle] [sigh] [gasp] [cough] [whisper] [breath]")
        tag_label.pack(anchor="w", pady=(4, 0))
        attach_tooltip(tag_label, tooltip("chatterbox_tags"))
        self.chatterbox_controls.append(tag_label)

    def _build_gpu_safety_controls(self, parent: ttk.Frame) -> None:
        """GPU protection applies to every CUDA provider, so it is never gated on
        Chatterbox — only on whether this model actually runs on CUDA."""
        ttk.Label(parent, textvariable=self.gpu_scope_var, wraplength=340,
                  foreground="#444444").pack(anchor="w", pady=(0, 8))

        hardware_label = ttk.Label(
            parent,
            text=self.controller.gpu_temperature_guidance(),
            wraplength=340,
            foreground="#9A4E00",
        )
        hardware_label.pack(anchor="w", pady=(0, 8))
        attach_tooltip(hardware_label, tooltip("gpu_hardware"))

        safety_check = ttk.Checkbutton(
            parent,
            text="Bật bảo vệ GPU (khuyến nghị)",
            variable=self.gpu_safety_enabled_var,
            command=self.save_preferences,
        )
        safety_check.pack(anchor="w", pady=(0, 8))
        attach_tooltip(safety_check, tooltip("gpu_enabled"))
        self.gpu_safety_controls.append(safety_check)

        for label, variable, field, tooltip_key in (
            ("Nhiệt độ bắt đầu tối đa (°C)", self.gpu_start_temperature_var,
             "gpu_start_temperature_c", "gpu_start_temp"),
            ("Ngưỡng bắt đầu đếm quá nhiệt (°C)", self.gpu_abort_temperature_var,
             "gpu_abort_temperature_c", "gpu_abort_temp"),
            ("Thời gian quá nhiệt liên tục (giây)", self.gpu_abort_temperature_sustain_var,
             "gpu_abort_temperature_sustain_seconds", "gpu_abort_sustain"),
            ("Ngưỡng nguy cấp tạm nghỉ ngay (°C)", self.gpu_emergency_temperature_var,
             "gpu_emergency_temperature_c", "gpu_emergency_temp"),
            ("Thời gian chờ phục hồi tối đa (giây)", self.gpu_cooldown_max_wait_var,
             "gpu_cooldown_max_wait_seconds", "gpu_cooldown_max_wait"),
            ("Nhiệt độ cho phép chạy lại (°C)", self.gpu_resume_temperature_var,
             "gpu_resume_temperature_c", "gpu_resume_temp"),
            ("VRAM trống trước khi chạy (MB)", self.gpu_minimum_free_vram_var,
             "gpu_minimum_free_vram_mb", "gpu_start_vram"),
            ("VRAM trống tối thiểu khi chạy (MB)", self.gpu_runtime_minimum_free_vram_var,
             "gpu_runtime_minimum_free_vram_mb", "gpu_runtime_vram"),
            ("GPU đang dùng tối đa (%)", self.gpu_maximum_utilization_var,
             "gpu_maximum_utilization_percent", "gpu_usage"),
            ("NVENC đang dùng tối đa (%)", self.gpu_maximum_encoder_utilization_var,
             "gpu_maximum_encoder_utilization_percent", "gpu_nvenc"),
        ):
            spin = self._field_spin(parent, label, variable, field, tooltip_key)
            self.gpu_safety_controls.append(spin)
            self.gpu_safety_threshold_controls.append(spin)

        reset_button = ttk.Button(
            parent,
            text="Khôi phục ngưỡng an toàn mặc định",
            command=self._apply_gpu_safety_defaults,
        )
        reset_button.pack(fill="x", pady=(2, 0))
        attach_tooltip(reset_button, tooltip("gpu_reset"))
        self.gpu_safety_controls.append(reset_button)

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

        dir_label = ttk.Label(frame, text="Thư mục xuất riêng")
        dir_label.grid(row=0, column=0, sticky="w", pady=2)
        attach_tooltip(dir_label, tooltip("output_dir"))
        output_row = ttk.Frame(frame)
        output_row.grid(row=0, column=1, sticky="ew", padx=(8, 0), pady=2)
        output_row.columnconfigure(0, weight=1)
        output_entry = ttk.Entry(output_row, textvariable=self.output_dir_var)
        output_entry.grid(row=0, column=0, sticky="ew")
        attach_tooltip(output_entry, tooltip("output_dir"))
        ttk.Button(output_row, text="Chọn", command=self.choose_output_dir).grid(
            row=0, column=1, padx=(6, 0)
        )

        row = 1
        if include_output_stem:
            stem_label = ttk.Label(frame, text="Tên file xuất")
            stem_label.grid(row=row, column=0, sticky="w", pady=2)
            attach_tooltip(stem_label, tooltip("output_stem"))
            stem_entry = ttk.Entry(frame, textvariable=self.output_stem_var)
            stem_entry.grid(row=row, column=1, sticky="ew", padx=(8, 0), pady=2)
            attach_tooltip(stem_entry, tooltip("output_stem"))
            row += 1

        ttk.Label(frame, text="Định dạng audio").grid(row=row, column=0, sticky="w", pady=2)
        format_row = ttk.Frame(frame)
        format_row.grid(row=row, column=1, sticky="w", padx=(8, 0), pady=2)
        format_combo = ttk.Combobox(
            format_row,
            textvariable=self.output_audio_format_var,
            values=list(self.output_audio_format_map.keys()),
            state="readonly",
            width=10,
        )
        format_combo.pack(side="left")
        attach_tooltip(format_combo, tooltip("output_format"))
        ttk.Label(format_row, text="Bitrate MP3").pack(side="left", padx=(12, 4))
        bitrate_combo = ttk.Combobox(
            format_row,
            textvariable=self.mp3_bitrate_var,
            values=[128, 160, 192, 256, 320],
            state="readonly",
            width=8,
        )
        bitrate_combo.pack(side="left")
        attach_tooltip(bitrate_combo, tooltip("output_bitrate"))
        ttk.Label(format_row, text="kbps").pack(side="left", padx=(4, 0))
        self.mp3_bitrate_combos.append(bitrate_combo)
        row += 1

        checks = ttk.Frame(frame)
        checks.grid(row=row, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        overwrite_check = ttk.Checkbutton(
            checks,
            text="Ghi đè file nếu đã tồn tại",
            variable=self.overwrite_var,
            command=self.save_preferences,
        )
        overwrite_check.pack(side="left")
        attach_tooltip(overwrite_check, tooltip("output_overwrite"))
        split_check = ttk.Checkbutton(
            checks,
            text="Tách dòng SRT/đoạn văn thành file riêng",
            variable=self.split_output_var,
            command=self.on_split_output_changed,
        )
        split_check.pack(side="left", padx=(14, 0))
        attach_tooltip(split_check, tooltip("output_split"))
        srt_check = ttk.Checkbutton(
            checks,
            text="Xuất kèm SRT",
            variable=self.output_srt_var,
            command=self.save_preferences,
        )
        srt_check.pack(side="left", padx=(14, 0))
        attach_tooltip(srt_check, tooltip("output_srt"))
        join_check = ttk.Checkbutton(
            checks,
            text="Tạo thêm file audio tổng",
            variable=self.join_split_audio_var,
            command=self.save_preferences,
        )
        join_check.pack(side="left", padx=(14, 0))
        attach_tooltip(join_check, tooltip("output_join"))
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

    def _field_spin(
        self,
        parent,
        label: str,
        variable: tk.Variable,
        field: str,
        tooltip_key: str = "",
    ):
        """Spin box whose range comes from the request schema, not from the GUI."""
        limit = field_limits.limit(field)
        return self._spin(
            parent,
            label,
            variable,
            limit.widget_minimum,
            limit.maximum,
            limit.step,
            tooltip_text=tooltip(tooltip_key) if tooltip_key else "",
        )

    def _spin(
        self,
        parent,
        label: str,
        variable: tk.Variable,
        from_: float,
        to: float,
        step: float,
        tooltip_text: str = "",
    ):
        label_widget = ttk.Label(parent, text=label)
        label_widget.pack(anchor="w")
        spin = ttk.Spinbox(parent, textvariable=variable, from_=from_, to=to, increment=step)
        spin.pack(fill="x", pady=(4, 8))
        if tooltip_text:
            attach_tooltip(label_widget, tooltip_text)
            attach_tooltip(spin, tooltip_text)
        return spin
