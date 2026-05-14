"""
Batch Processing Frame - UI for multi-file batch TTS generation.
Supports importing multiple text/srt files from different folders.
Per-file voice profile and speed settings.
Ported from Qwen3-TTS app.
"""

import os
import re
import tkinter as tk
from tkinter import ttk, filedialog
from typing import Callable, Optional, List

import logging

logger = logging.getLogger(__name__)

# Column definitions: (col_id, heading, default_width, min_width, anchor)
COLUMNS = [
    ("name",    "Tên file",    180, 100, "w"),
    ("folder",  "Thư mục",    200, 100, "w"),
    ("lines",   "Dòng",        50,  35, "center"),
    ("voice",   "Profile",    120,  70, "center"),
    ("speed",   "Tốc độ",      60,  45, "center"),
    ("status",  "Trạng thái",  80,  50, "center"),
]
COLUMN_IDS = tuple(c[0] for c in COLUMNS)
NO_PROFILE_LABEL = "— mặc định —"


class BatchFrame(ttk.LabelFrame):
    """Frame for multi-file batch TTS processing."""

    def __init__(self, parent: tk.Widget, **kwargs):
        super().__init__(parent, text="📁 Danh sách file", **kwargs)
        self.on_start = None
        self.on_stop = None
        self.on_input_files_change = None
        self.on_column_resize = None  # callback(col_widths: dict)
        self._is_processing = False
        self._file_list: List[dict] = []
        self._file_counter = 0

        # Per-file defaults
        self._default_speed = 1.0
        self._default_voice_profile_id = ""

        # Voice profile choices: list of (label, profile_id)
        self._profile_choices: list[tuple[str, str]] = []

        # Inline edit widget reference
        self._edit_widget = None

        # Column resize tracking
        self._col_resize_after_id = None

        self._setup_ui()
        self._setup_drag_drop()

    def _setup_ui(self):
        # ── Top toolbar ──
        toolbar = ttk.Frame(self)
        toolbar.pack(fill="x", padx=8, pady=(8, 4))

        ttk.Button(toolbar, text="➕ Thêm file", command=self._browse_files, width=12).pack(side="left")
        ttk.Button(toolbar, text="📂 Thêm folder", command=self._browse_folder, width=12).pack(side="left", padx=(4, 0))
        ttk.Button(toolbar, text="🗑️ Xóa chọn", command=self._remove_selected, width=10).pack(side="left", padx=(4, 0))
        ttk.Button(toolbar, text="❌ Xóa hết", command=self._clear_all, width=10).pack(side="left", padx=(4, 0))

        self.file_count_label = ttk.Label(toolbar, text="0 files", foreground="gray")
        self.file_count_label.pack(side="right")

        # ── Checkbox row ──
        cb_frame = ttk.Frame(self)
        cb_frame.pack(fill="x", padx=8, pady=(0, 4))

        self.select_all_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(cb_frame, text="Chọn tất cả", variable=self.select_all_var,
                         command=self._toggle_select_all).pack(side="left")

        # ── File list (Treeview) ──
        tree_frame = ttk.Frame(self)
        tree_frame.pack(fill="both", expand=True, padx=8, pady=(0, 4))

        self.file_tree = ttk.Treeview(
            tree_frame, columns=COLUMN_IDS, show="headings",
            height=6, selectmode="extended"
        )
        for col_id, heading, width, minw, anchor in COLUMNS:
            self.file_tree.heading(col_id, text=heading, anchor="w" if anchor == "w" else "center")
            self.file_tree.column(col_id, width=width, minwidth=minw, anchor=anchor)

        tree_scroll = ttk.Scrollbar(tree_frame, orient="vertical", command=self.file_tree.yview)
        self.file_tree.configure(yscrollcommand=tree_scroll.set)

        self.file_tree.pack(side="left", fill="both", expand=True)
        tree_scroll.pack(side="right", fill="y")

        # Double-click to edit voice/speed
        self.file_tree.bind("<Double-1>", self._on_tree_double_click)
        self.file_tree.bind("<Button-1>", self._dismiss_edit_widget)

        # Track column resizes via separator drag
        self.file_tree.bind("<ButtonRelease-1>", self._on_possible_column_resize)

        # ── Options row ──
        options_frame = ttk.Frame(self)
        options_frame.pack(fill="x", padx=8, pady=4)
        ttk.Label(options_frame, text="Bắt đầu từ câu:").pack(side="left")
        self.start_index = ttk.Spinbox(options_frame, from_=1, to=9999, width=5)
        self.start_index.set(1)
        self.start_index.pack(side="left", padx=(4, 16))
        self.auto_retry_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(options_frame, text="Auto Retry", variable=self.auto_retry_var).pack(side="left")
        self.auto_close_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(options_frame, text="Tự tắt khi xong", variable=self.auto_close_var).pack(side="left", padx=(12, 0))

        # ── Progress row ──
        progress_frame = ttk.Frame(self)
        progress_frame.pack(fill="x", padx=8, pady=4)
        self.progress_var = tk.DoubleVar(value=0)
        self.progress_bar = ttk.Progressbar(progress_frame, variable=self.progress_var, maximum=100, mode='determinate')
        self.progress_bar.pack(fill="x", expand=True)

        # Status label
        self.status_label = ttk.Label(self, text="Sẵn sàng")
        self.status_label.pack(anchor="w", padx=8)

        # ── Buttons row ──
        button_frame = ttk.Frame(self)
        button_frame.pack(fill="x", padx=8, pady=(4, 8))
        self.start_btn = ttk.Button(button_frame, text="▶️ Bắt đầu", command=self._on_start)
        self.start_btn.pack(side="left")
        self.stop_btn = ttk.Button(button_frame, text="⏹️ Dừng", command=self._on_stop, state="disabled")
        self.stop_btn.pack(side="left", padx=(8, 0))

    # ══════════════════════════════════════════════════════
    # ── Column resize persistence ──
    # ══════════════════════════════════════════════════════

    def _on_possible_column_resize(self, event=None):
        """Debounced column resize callback."""
        if self._col_resize_after_id:
            self.after_cancel(self._col_resize_after_id)
        self._col_resize_after_id = self.after(500, self._emit_column_widths)

    def _emit_column_widths(self):
        """Emit current column widths via callback."""
        self._col_resize_after_id = None
        if self.on_column_resize:
            widths = {}
            for col_id in COLUMN_IDS:
                widths[col_id] = self.file_tree.column(col_id, "width")
            self.on_column_resize(widths)

    def set_column_widths(self, widths: dict):
        """Restore saved column widths."""
        if not widths:
            return
        for col_id, w in widths.items():
            if col_id in COLUMN_IDS:
                try:
                    self.file_tree.column(col_id, width=int(w))
                except Exception:
                    pass

    def get_column_widths(self) -> dict:
        """Get current column widths."""
        return {col_id: self.file_tree.column(col_id, "width") for col_id in COLUMN_IDS}

    # ══════════════════════════════════════════════════════
    # ── Select all ──
    # ══════════════════════════════════════════════════════

    def _toggle_select_all(self):
        """Toggle select all items in the treeview."""
        if self.select_all_var.get():
            all_items = self.file_tree.get_children()
            self.file_tree.selection_set(all_items)
        else:
            self.file_tree.selection_remove(self.file_tree.selection())

    # ══════════════════════════════════════════════════════
    # ── Inline editing (double-click on Voice / Speed) ──
    # ══════════════════════════════════════════════════════

    def _on_tree_double_click(self, event):
        if self._is_processing:
            return

        region = self.file_tree.identify_region(event.x, event.y)
        if region != "cell":
            return

        column_id = self.file_tree.identify_column(event.x)
        iid = self.file_tree.identify_row(event.y)
        if not iid:
            return

        col_idx = int(column_id.replace("#", "")) - 1
        if col_idx < 0 or col_idx >= len(COLUMN_IDS):
            return
        col_name = COLUMN_IDS[col_idx]

        if col_name == "voice":
            self._edit_voice_cell(iid, column_id)
        elif col_name == "speed":
            self._edit_speed_cell(iid, column_id)

    def _edit_voice_cell(self, iid, column_id):
        """Show dropdown to select voice profile for this file."""
        self._dismiss_edit_widget()

        bbox = self.file_tree.bbox(iid, column_id)
        if not bbox:
            return
        x, y, w, h = bbox

        current_voice = self.file_tree.set(iid, "voice")
        profile_labels = [NO_PROFILE_LABEL] + [pc[0] for pc in self._profile_choices]
        combo = ttk.Combobox(self.file_tree, values=profile_labels, state="readonly",
                             width=max(12, w // 8))
        if current_voice in profile_labels:
            combo.set(current_voice)
        else:
            combo.set(NO_PROFILE_LABEL)

        combo.place(x=x, y=y, width=w, height=h)
        combo.focus_set()

        def on_select(event=None):
            new_label = combo.get()
            if new_label == NO_PROFILE_LABEL:
                profile_id = ""
                display = NO_PROFILE_LABEL
            else:
                profile_id = ""
                for lbl, pid in self._profile_choices:
                    if lbl == new_label:
                        profile_id = pid
                        break
                display = new_label

            self.file_tree.set(iid, "voice", display)
            for f in self._file_list:
                if f.get("iid") == iid:
                    f["voice_profile_id"] = profile_id
                    break
            self._dismiss_edit_widget()

        combo.bind("<<ComboboxSelected>>", on_select)
        combo.bind("<Escape>", lambda e: self._dismiss_edit_widget())
        combo.bind("<FocusOut>", lambda e: self._dismiss_edit_widget())

        self._edit_widget = combo

    def _edit_speed_cell(self, iid, column_id):
        self._dismiss_edit_widget()

        bbox = self.file_tree.bbox(iid, column_id)
        if not bbox:
            return
        x, y, w, h = bbox

        current_speed = self.file_tree.set(iid, "speed")
        current_val = current_speed.replace("x", "").strip()

        entry_var = tk.StringVar(value=current_val)
        entry = ttk.Entry(self.file_tree, textvariable=entry_var, justify="center")
        entry.place(x=x, y=y, width=w, height=h)
        entry.focus_set()
        entry.select_range(0, tk.END)

        def on_confirm(event=None):
            try:
                new_speed = float(entry_var.get())
                new_speed = max(0.5, min(2.0, new_speed))
                new_speed = round(new_speed * 20) / 20
                self.file_tree.set(iid, "speed", f"{new_speed:.2f}x")
                for f in self._file_list:
                    if f.get("iid") == iid:
                        f["speed"] = new_speed
                        break
            except ValueError:
                pass
            self._dismiss_edit_widget()

        entry.bind("<Return>", on_confirm)
        entry.bind("<Escape>", lambda e: self._dismiss_edit_widget())
        entry.bind("<FocusOut>", lambda e: on_confirm())

        self._edit_widget = entry

    def _dismiss_edit_widget(self, event=None):
        if self._edit_widget is not None:
            try:
                self._edit_widget.destroy()
            except Exception:
                pass
            self._edit_widget = None

    # ══════════════════════════════════════════════════
    # ── File management ──
    # ══════════════════════════════════════════════════

    def _browse_files(self):
        fps = filedialog.askopenfilenames(
            title="Chọn file Text/SRT",
            filetypes=[("Text/Subtitle", "*.srt;*.txt;*.md"), ("All", "*.*")]
        )
        if fps:
            self._add_files(list(fps))

    def _browse_folder(self):
        folder = filedialog.askdirectory(title="Chọn thư mục chứa file")
        if folder:
            files = []
            for f in sorted(os.listdir(folder)):
                if f.lower().endswith(('.txt', '.srt', '.md')):
                    files.append(os.path.join(folder, f))
            if files:
                self._add_files(files)

    def _add_files(self, file_paths: List[str]):
        existing_paths = {f["path"] for f in self._file_list}
        added = 0
        for fp in file_paths:
            fp = fp.strip()
            if not fp or fp in existing_paths:
                continue
            if not os.path.isfile(fp):
                continue

            line_count = self._count_lines(fp)

            entry = {
                "path": fp,
                "name": os.path.basename(fp),
                "folder": os.path.dirname(fp),
                "lines": line_count,
                "status": "⏳",
                "voice_profile_id": self._default_voice_profile_id,
                "speed": self._default_speed,
            }
            self._file_list.append(entry)
            self._file_counter += 1

            iid = f"file_{self._file_counter}"
            entry["iid"] = iid

            voice_display = self._profile_label_for(entry["voice_profile_id"])
            speed_display = f"{entry['speed']:.2f}x"

            self.file_tree.insert("", "end", iid=iid, values=(
                entry["name"],
                self._shorten_path(entry["folder"]),
                str(line_count),
                voice_display,
                speed_display,
                entry["status"]
            ))
            existing_paths.add(fp)
            added += 1

        if added > 0:
            self._update_file_count()
            if self.on_input_files_change:
                self.on_input_files_change(self.get_input_files())

    def _profile_label_for(self, profile_id: str) -> str:
        """Get display label for a profile_id."""
        if not profile_id:
            return NO_PROFILE_LABEL
        for label, pid in self._profile_choices:
            if pid == profile_id:
                return label
        return NO_PROFILE_LABEL

    def _count_lines(self, fp: str) -> int:
        try:
            with open(fp, 'r', encoding='utf-8') as f:
                return sum(1 for line in f if line.strip())
        except Exception:
            return 0

    def _shorten_path(self, path: str, max_len: int = 40) -> str:
        if len(path) <= max_len:
            return path
        parts = path.replace("\\", "/").split("/")
        if len(parts) <= 2:
            return path
        return parts[0] + "/.../" + "/".join(parts[-2:])

    def _remove_selected(self):
        selected = self.file_tree.selection()
        if not selected:
            return
        for iid in selected:
            self.file_tree.delete(iid)
            self._file_list = [f for f in self._file_list if f.get("iid") != iid]
        self._update_file_count()
        if self.on_input_files_change:
            self.on_input_files_change(self.get_input_files())

    def _clear_all(self):
        for item in self.file_tree.get_children():
            self.file_tree.delete(item)
        self._file_list.clear()
        self._update_file_count()
        if self.on_input_files_change:
            self.on_input_files_change([])

    def _update_file_count(self):
        count = len(self._file_list)
        self.file_count_label.config(text=f"{count} file{'s' if count != 1 else ''}")

    # ── Drag-drop ──

    def _setup_drag_drop(self):
        try:
            self.drop_target_register('DND_Files')
            self.dnd_bind('<<Drop>>', self._on_drop)
            self.file_tree.drop_target_register('DND_Files')
            self.file_tree.dnd_bind('<<Drop>>', self._on_drop)
        except Exception:
            pass

    def _on_drop(self, event):
        raw = event.data
        files = []
        if '{' in raw:
            files = re.findall(r'\{([^}]+)\}', raw)
            remaining = re.sub(r'\{[^}]+\}', '', raw).strip()
            if remaining:
                files.extend(remaining.split())
        else:
            files = raw.strip().split('\n') if '\n' in raw else raw.strip().split()

        valid_files = []
        for fp in files:
            fp = fp.strip()
            if fp.lower().endswith(('.srt', '.txt', '.md')):
                valid_files.append(fp)

        if valid_files:
            self._add_files(valid_files)

    def _on_start(self):
        if self.on_start:
            self.on_start()

    def _on_stop(self):
        if self.on_stop:
            self.on_stop()

    # ══════════════════════════════════════════════════
    # ── Voice profiles & defaults ──
    # ══════════════════════════════════════════════════

    def set_default_speed(self, speed: float):
        self._default_speed = speed

    def set_default_voice_profile(self, profile_id: str):
        self._default_voice_profile_id = profile_id

    def update_profile_choices(self, profiles: list):
        """
        Update available voice profiles for per-file selection.
        profiles: list of VoiceProfile objects with profile_id, name, project
        """
        self._profile_choices = []
        for profile in profiles:
            label = profile.name
            if profile.project:
                label = f"{profile.name} - {profile.project}"
            self._profile_choices.append((label, profile.profile_id))

    def update_all_speeds(self, speed: float):
        self._default_speed = speed
        speed_display = f"{speed:.2f}x"
        for f in self._file_list:
            f["speed"] = speed
            iid = f.get("iid")
            if iid and self.file_tree.exists(iid):
                self.file_tree.set(iid, "speed", speed_display)

    def update_all_voice_profiles(self, profile_id: str):
        """Set voice profile for all files."""
        self._default_voice_profile_id = profile_id
        label = self._profile_label_for(profile_id)
        for f in self._file_list:
            f["voice_profile_id"] = profile_id
            iid = f.get("iid")
            if iid and self.file_tree.exists(iid):
                self.file_tree.set(iid, "voice", label)

    # ══════════════════════════════════════════════════
    # ── Getters ──
    # ══════════════════════════════════════════════════

    def get_input_files(self) -> List[str]:
        return [f["path"] for f in self._file_list]

    def get_file_settings(self) -> List[dict]:
        return [
            {
                "path": f["path"],
                "voice_profile_id": f.get("voice_profile_id", ""),
                "speed": f.get("speed", self._default_speed),
            }
            for f in self._file_list
        ]

    def get_start_index(self) -> int:
        try:
            return int(self.start_index.get())
        except ValueError:
            return 1

    def get_auto_retry(self) -> bool:
        return self.auto_retry_var.get()

    def get_auto_close(self) -> bool:
        return self.auto_close_var.get()

    # ══════════════════════════════════════════════════
    # ── Setters ──
    # ══════════════════════════════════════════════════

    def set_auto_close(self, val: bool):
        self.auto_close_var.set(val)

    def update_file_status(self, file_path: str, status: str):
        for f in self._file_list:
            if f["path"] == file_path:
                f["status"] = status
                iid = f.get("iid")
                if iid and self.file_tree.exists(iid):
                    self.file_tree.set(iid, "status", status)
                    self.file_tree.see(iid)
                break

    def reset_all_status(self):
        for f in self._file_list:
            f["status"] = "⏳"
            iid = f.get("iid")
            if iid and self.file_tree.exists(iid):
                self.file_tree.set(iid, "status", "⏳")

    def set_processing(self, is_processing: bool):
        self._is_processing = is_processing
        if is_processing:
            self.start_btn.config(state="disabled")
            self.stop_btn.config(state="normal")
        else:
            self.start_btn.config(state="normal")
            self.stop_btn.config(state="disabled")
            self.progress_var.set(0)

    def set_progress(self, current: int, total: int, message: str = ""):
        if total > 0:
            self.progress_var.set((current / total) * 100)
        self.status_label.config(text=message if message else f"Đang xử lý: {current}/{total}")

    def set_status(self, message: str):
        self.status_label.config(text=message)
