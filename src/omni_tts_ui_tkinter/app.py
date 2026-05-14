"""
Main Window - The primary application window.
Composes all widget frames into a complete UI.
Adapted from Qwen3-TTS app to work with omni_tts_core.
"""
from __future__ import annotations

import os
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from typing import Optional, Callable
from pathlib import Path

# Try to import TkinterDnD for drag-drop support
try:
    from tkinterdnd2 import TkinterDnD
    DND_AVAILABLE = True
except ImportError:
    DND_AVAILABLE = False

from omni_tts_ui_tkinter.panels.model_frame import ModelFrame
from omni_tts_ui_tkinter.panels.voice_frame import VoiceFrame
from omni_tts_ui_tkinter.panels.batch_frame import BatchFrame
from omni_tts_ui_tkinter.panels.trim_frame import TrimSettingsFrame
from omni_tts_ui_tkinter.panels.log_frame import LogFrame
from omni_tts_ui_tkinter.voice_panel import VoiceProfilePanel
from omni_tts_ui_tkinter.controller import AppController
from omni_tts_ui_tkinter.config_manager import ConfigManager

import logging

logger = logging.getLogger(__name__)


class TkinterApp:
    """Main application window."""

    TITLE = "Colin TTS Local"
    MIN_WIDTH = 900
    MIN_HEIGHT = 800

    def __init__(self, root=None, controller: AppController = None):
        # Create config manager
        self.config_manager = ConfigManager()

        # Create controller
        self.controller = controller or AppController(self.config_manager)

        # Create root window
        if root is not None:
            self.root = root
        elif DND_AVAILABLE:
            self.root = TkinterDnD.Tk()
        else:
            self.root = tk.Tk()

        self.root.title(self.TITLE)
        self.root.minsize(self.MIN_WIDTH, self.MIN_HEIGHT)

        # Set window icon
        icon_path = Path(__file__).parent.parent.parent / "app" / "icon.ico"
        if icon_path.exists():
            try:
                self.root.iconbitmap(str(icon_path))
            except Exception:
                pass

        # Restore geometry
        geo = self.config_manager.config.window
        self.root.geometry(f"{geo.width}x{geo.height}+{geo.x}+{geo.y}")

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        self._setup_style()
        self._setup_ui()

        # Connect controller to view
        self.controller.set_view(self)

        logger.info("TkinterApp initialized")

    def _setup_style(self):
        style = ttk.Style()
        available_themes = style.theme_names()
        if "clam" in available_themes:
            style.theme_use("clam")
        style.configure("TLabelframe.Label", font=("Segoe UI", 10, "bold"))
        style.configure("TLabel", font=("Segoe UI", 9))
        style.configure("TButton", font=("Segoe UI", 9))
        # Treeview styling
        style.configure("Treeview", font=("Segoe UI", 9), rowheight=22)
        style.configure("Treeview.Heading", font=("Segoe UI", 9, "bold"))

    def _setup_ui(self):
        main_container = ttk.Frame(self.root, padding=10)
        main_container.pack(fill="both", expand=True)

        self.notebook = ttk.Notebook(main_container)
        self.notebook.pack(fill="both", expand=True)

        # Tab 1: Main TTS
        main_tab = ttk.Frame(self.notebook)
        self.notebook.add(main_tab, text="🎵 Text-to-Speech")
        self._setup_main_tab(main_tab)

        # Tab 2: Trim Settings
        trim_tab = ttk.Frame(self.notebook)
        self.notebook.add(trim_tab, text="✂️ Trim Settings")
        self._setup_trim_tab(trim_tab)

        # Tab 3: Model Management
        model_mgmt_tab = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(model_mgmt_tab, text="📦 Quản lý model")
        self._setup_model_mgmt_tab(model_mgmt_tab)

        # Tab 4: Voice Profiles
        self._setup_voice_profile_tab(self.notebook)

    def _setup_main_tab(self, parent):
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(2, weight=1)  # Batch frame expands

        # Get model choices from controller
        model_choices = self.controller.model_choices()

        # Voice Frame (includes model selection)
        self.voice_frame = VoiceFrame(parent, model_choices=model_choices)
        self.voice_frame.grid(row=0, column=0, sticky="ew", pady=(0, 6))

        # Model Status Frame (compact)
        self.model_frame = ModelFrame(parent)
        self.model_frame.grid(row=1, column=0, sticky="ew", pady=(0, 6))
        # Hide model frame buttons for now - the batch engine handles loading
        self.model_frame.load_btn.pack_forget()
        self.model_frame.unload_btn.pack_forget()
        self.model_frame.set_status_text("Model sẽ tự động tải khi cần")
        self.model_frame.status_indicator.config(text="🟡")

        # Batch Frame (expandable)
        self.batch_frame = BatchFrame(parent)
        self.batch_frame.grid(row=2, column=0, sticky="nsew", pady=(0, 6))

        # Log Frame
        self.log_frame = LogFrame(parent)
        self.log_frame.grid(row=3, column=0, sticky="ew")

    def _setup_trim_tab(self, parent):
        parent.columnconfigure(0, weight=1)
        self.trim_frame = TrimSettingsFrame(parent)
        self.trim_frame.pack(fill="x", padx=10, pady=10)

        info_text = """
Khi bật Trim, phần mềm sẽ tự động:
• Cắt bỏ khoảng lặng đầu/cuối mỗi file audio
• Tạo 2 phiên bản output với padding khác nhau:
  - Folder 1: dùng Padding #1 (25ms mặc định)
  - Folder 2: dùng Padding #2 (100ms mặc định)
"""
        ttk.Label(parent, text=info_text, foreground="gray").pack(anchor="w", padx=10)

    def _setup_model_mgmt_tab(self, tab):
        """Setup model management tab (kept from original app)."""
        tab.columnconfigure(0, weight=1)
        tab.rowconfigure(0, weight=1)

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
        ttk.Button(controls, text="Tải model đang chọn", command=self._download_selected_model).pack(
            side="left"
        )
        ttk.Button(
            controls,
            text="Tải model bắt buộc còn thiếu",
            command=self._download_required_models,
        ).pack(side="left", padx=(8, 0))
        ttk.Button(controls, text="Làm mới", command=self._refresh_models).pack(
            side="left", padx=(8, 0)
        )

        self._refresh_models()

    def _setup_voice_profile_tab(self, notebook):
        """Setup voice profile management tab."""
        panel = VoiceProfilePanel(notebook, self.controller, self._refresh_voice_profiles)
        notebook.add(panel, text="🎤 Profile giọng")

    # ── Model Management ──

    def _refresh_models(self):
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

    def _download_selected_model(self):
        selected = self.model_table.selection()
        if not selected:
            messagebox.showinfo("Thông báo", "Hãy chọn một model trong bảng.")
            return

        model_id = selected[0]
        model_name = self.model_table.set(model_id, "name")
        self.log(f"Đang tải model: {model_name}...", "INFO")
        self._set_download_buttons_state("disabled")

        import threading

        def _worker():
            try:
                result = self.controller.download_model(model_id)
                self.root.after(0, lambda: self._on_download_done(result))
            except Exception as e:
                err_msg = str(e)
                self.root.after(0, lambda: self._on_download_error(err_msg))

        threading.Thread(target=_worker, daemon=True).start()

    def _download_required_models(self):
        self.log("Đang tải các model bắt buộc còn thiếu...", "INFO")
        self._set_download_buttons_state("disabled")

        import threading

        def _worker():
            try:
                result = self.controller.download_required_models()
                self.root.after(0, lambda: self._on_download_done(result))
            except Exception as e:
                err_msg = str(e)
                self.root.after(0, lambda: self._on_download_error(err_msg))

        threading.Thread(target=_worker, daemon=True).start()

    def _on_download_done(self, result_msg: str):
        self._refresh_models()
        self._set_download_buttons_state("normal")
        self.log(result_msg, "SUCCESS")
        messagebox.showinfo("Thông báo", result_msg)

    def _on_download_error(self, err_msg: str):
        self._set_download_buttons_state("normal")
        self.log(f"Lỗi tải model: {err_msg}", "ERROR")
        messagebox.showerror("Lỗi", err_msg)

    def _set_download_buttons_state(self, state: str):
        """Enable/disable all download buttons in model management tab."""
        try:
            for widget in self.model_table.master.winfo_children():
                if isinstance(widget, ttk.Frame):
                    for child in widget.winfo_children():
                        if isinstance(child, ttk.Button):
                            child.configure(state=state)
        except Exception:
            pass

    def _refresh_voice_profiles(self):
        """Callback for voice profile panel - refresh dropdown in voice frame."""
        self.controller._refresh_voice_profiles()

    # ── Window management ──

    def _on_close(self):
        logger.info("Window closing")
        self.controller.on_window_close()
        self.root.destroy()

    def get_geometry(self):
        geo = self.root.geometry()
        size, pos = geo.split("+", 1)
        width, height = map(int, size.split("x"))
        x, y = map(int, pos.split("+"))
        return (x, y, width, height)

    def run(self):
        logger.info("Starting main loop")
        self.root.mainloop()

    def log(self, message, level="INFO"):
        if level == "SUCCESS":
            self.log_frame.success(message)
        elif level == "WARNING":
            self.log_frame.warning(message)
        elif level == "ERROR":
            self.log_frame.error(message)
        else:
            self.log_frame.info(message)
