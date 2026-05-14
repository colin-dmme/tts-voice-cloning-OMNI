"""
Log Frame Widget - For displaying application logs with color coding.
Ported from Qwen3-TTS app.
"""

import tkinter as tk
from tkinter import ttk
from datetime import datetime


class LogFrame(ttk.LabelFrame):
    """Frame for displaying logs - compact version."""

    MAX_LOG_ENTRIES = 100

    def __init__(self, parent: tk.Widget, **kwargs):
        super().__init__(parent, text="📋 Nhật ký", **kwargs)
        self._setup_ui()

    def _setup_ui(self):
        """Setup the UI components."""
        # Log text widget with scrollbar - compact layout
        log_container = ttk.Frame(self)
        log_container.pack(fill="both", expand=True, padx=8, pady=(4, 4))

        self.log_text = tk.Text(
            log_container,
            wrap="word",
            height=4,
            state="disabled",
            font=("Consolas", 9)
        )
        scrollbar = ttk.Scrollbar(
            log_container,
            orient="vertical",
            command=self.log_text.yview
        )
        self.log_text.configure(yscrollcommand=scrollbar.set)

        self.log_text.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # Clear button inline at bottom
        clear_btn = ttk.Button(
            self,
            text="🗑️ Xóa",
            command=self._clear_log,
            width=8
        )
        clear_btn.pack(side="right", padx=8, pady=(0, 4))

        # Configure text tags for different log levels
        self.log_text.tag_configure("INFO", foreground="black")
        self.log_text.tag_configure("SUCCESS", foreground="green")
        self.log_text.tag_configure("WARNING", foreground="orange")
        self.log_text.tag_configure("ERROR", foreground="red")
        self.log_text.tag_configure("TIME", foreground="gray")

        self._log_count = 0

    def log(self, message: str, level: str = "INFO"):
        """Add a log entry."""
        timestamp = datetime.now().strftime("%H:%M:%S")

        self.log_text.configure(state="normal")

        # Check if we need to remove old entries
        self._log_count += 1
        if self._log_count > self.MAX_LOG_ENTRIES:
            self.log_text.delete("1.0", "2.0")
            self._log_count -= 1

        # Insert timestamp
        self.log_text.insert("end", f"[{timestamp}] ", "TIME")

        # Insert message with appropriate tag
        self.log_text.insert("end", f"{message}\n", level)

        # Scroll to end
        self.log_text.see("end")

        self.log_text.configure(state="disabled")

    def info(self, message: str):
        """Log info message."""
        self.log(message, "INFO")

    def success(self, message: str):
        """Log success message."""
        self.log(message, "SUCCESS")

    def warning(self, message: str):
        """Log warning message."""
        self.log(message, "WARNING")

    def error(self, message: str):
        """Log error message."""
        self.log(message, "ERROR")

    def _clear_log(self):
        """Clear all log entries."""
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")
        self._log_count = 0
        self.info("Log cleared")
