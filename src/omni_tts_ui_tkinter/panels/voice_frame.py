"""
Voice Frame Widget - Model selection, language, speed, and voice profile settings.
Adapted from Qwen3-TTS to work with omni_tts_core model registry.
"""

import tkinter as tk
from tkinter import ttk
from typing import Callable, Optional
import os
import logging

from omni_tts_shared.languages import LANGUAGE_LABELS, LANGUAGE_CODES

logger = logging.getLogger(__name__)


class VoiceFrame(ttk.LabelFrame):
    """Frame for voice settings with model selection and voice profile options."""

    def __init__(self, parent: tk.Widget, model_choices: list = None, **kwargs):
        super().__init__(parent, text="⚙️ Cài đặt giọng nói", **kwargs)

        # Callbacks
        self.on_model_change = None
        self.on_language_change = None
        self.on_speed_change = None
        self.on_profile_change = None

        # Model choices: list of (display_name, model_id)
        self._model_choices = model_choices or []

        # Voice profiles: list of {profile_id, name, audio_path, transcript, project}
        self._profile_map = {}  # display_label -> profile_id
        self._profiles = {}  # profile_id -> profile object

        self._setup_ui()

    def _setup_ui(self):
        self.columnconfigure(1, weight=1)
        row = 0

        # Model selector
        ttk.Label(self, text="Model:").grid(row=row, column=0, sticky="w", padx=10, pady=5)
        self.model_var = tk.StringVar()
        self.model_combo = ttk.Combobox(self, textvariable=self.model_var, state="readonly", width=50)
        display_names = [mc[0] for mc in self._model_choices]
        self.model_combo["values"] = display_names
        if display_names:
            self.model_combo.current(0)
        self.model_combo.grid(row=row, column=1, sticky="ew", padx=10, pady=5)
        self.model_combo.bind("<<ComboboxSelected>>", self._on_model_changed)
        row += 1

        # Language selector
        ttk.Label(self, text="Ngôn ngữ:").grid(row=row, column=0, sticky="w", padx=10, pady=5)
        self.language_var = tk.StringVar(value="Tiếng Việt")
        self.language_combo = ttk.Combobox(self, textvariable=self.language_var, state="readonly", width=30)
        self.language_combo["values"] = list(LANGUAGE_LABELS.values())
        self.language_combo.grid(row=row, column=1, sticky="ew", padx=10, pady=5)
        self.language_combo.bind("<<ComboboxSelected>>", self._on_language_changed)
        row += 1

        # Speed slider
        ttk.Label(self, text="Tốc độ:").grid(row=row, column=0, sticky="w", padx=10, pady=5)
        speed_frame = ttk.Frame(self)
        speed_frame.grid(row=row, column=1, sticky="ew", padx=10, pady=5)
        speed_frame.columnconfigure(0, weight=1)
        self.speed_var = tk.DoubleVar(value=1.0)
        self.speed_slider = ttk.Scale(speed_frame, from_=0.5, to=2.0, orient="horizontal",
                                       variable=self.speed_var, command=self._on_speed_changed)
        self.speed_slider.grid(row=0, column=0, sticky="ew")
        self.speed_value_label = ttk.Label(speed_frame, text="1.00x", width=6)
        self.speed_value_label.grid(row=0, column=1, padx=(10, 0))
        row += 1

        # Voice Profile selector
        ttk.Label(self, text="Profile giọng:").grid(row=row, column=0, sticky="w", padx=10, pady=(5, 10))
        profile_f = ttk.Frame(self)
        profile_f.grid(row=row, column=1, sticky="ew", padx=10, pady=(5, 10))
        profile_f.columnconfigure(0, weight=1)
        self.profile_var = tk.StringVar(value="Không dùng profile")
        self.profile_combo = ttk.Combobox(
            profile_f, textvariable=self.profile_var, state="readonly", width=40
        )
        self.profile_combo["values"] = ["Không dùng profile"]
        self.profile_combo.grid(row=0, column=0, sticky="ew")
        self.profile_combo.bind("<<ComboboxSelected>>", self._on_profile_selected)

        # Profile info label (shows audio path)
        self.profile_info_var = tk.StringVar(value="")
        self.profile_info_label = ttk.Label(
            profile_f, textvariable=self.profile_info_var,
            foreground="gray", font=("Segoe UI", 8)
        )
        self.profile_info_label.grid(row=1, column=0, sticky="w", pady=(2, 0))

    # ── Event handlers ──

    def _on_model_changed(self, event=None):
        if self.on_model_change:
            self.on_model_change(self.get_selected_model_id())

    def _on_language_changed(self, event=None):
        if self.on_language_change:
            self.on_language_change(self.get_language_code())

    def _on_speed_changed(self, value=None):
        speed = round(self.speed_var.get() * 20) / 20
        self.speed_var.set(speed)
        self.speed_value_label.config(text=f"{speed:.2f}x")
        if self.on_speed_change:
            self.on_speed_change(speed)

    def _on_profile_selected(self, event=None):
        """Handle voice profile dropdown selection."""
        selected = self.profile_var.get()
        if selected == "Không dùng profile":
            self.profile_info_var.set("")
            if self.on_profile_change:
                self.on_profile_change(None)
        else:
            profile_id = self._profile_map.get(selected)
            if profile_id and profile_id in self._profiles:
                profile = self._profiles[profile_id]
                audio_path = str(profile.audio_path) if profile.audio_path else ""
                self.profile_info_var.set(f"🔊 {audio_path}")
            if self.on_profile_change:
                self.on_profile_change(profile_id)

    # ── Getters ──

    def get_selected_model_id(self) -> str:
        idx = self.model_combo.current()
        if 0 <= idx < len(self._model_choices):
            return self._model_choices[idx][1]
        return ""

    def get_selected_model_display(self) -> str:
        return self.model_var.get()

    def get_language_code(self) -> str:
        return LANGUAGE_CODES.get(self.language_var.get(), "vi")

    def get_language_label(self) -> str:
        return self.language_var.get()

    def get_speed(self) -> float:
        return round(self.speed_var.get() * 20) / 20

    def get_selected_profile_id(self) -> str:
        """Return selected profile_id or empty string if 'no profile'."""
        selected = self.profile_var.get()
        if selected == "Không dùng profile":
            return ""
        return self._profile_map.get(selected, "")

    def get_ref_audio(self) -> str:
        """Get reference audio path from selected profile."""
        profile_id = self.get_selected_profile_id()
        if profile_id and profile_id in self._profiles:
            return str(self._profiles[profile_id].audio_path or "")
        return ""

    def get_ref_text(self) -> str:
        """Get reference text from selected profile."""
        profile_id = self.get_selected_profile_id()
        if profile_id and profile_id in self._profiles:
            return self._profiles[profile_id].transcript or ""
        return ""

    # ── Setters ──

    def set_model_by_id(self, model_id: str):
        for i, (display, mid) in enumerate(self._model_choices):
            if mid == model_id:
                self.model_combo.current(i)
                return

    def set_language(self, lang_code: str):
        label = LANGUAGE_LABELS.get(lang_code, lang_code)
        self.language_var.set(label)

    def set_language_choices(self, codes: list[str]):
        """Update available language choices."""
        labels = [LANGUAGE_LABELS.get(c, c) for c in codes]
        self.language_combo["values"] = labels

    def set_speed(self, val: float):
        self.speed_var.set(val)
        self.speed_value_label.config(text=f"{val:.2f}x")

    def set_profile_by_id(self, profile_id: str):
        """Select a profile by its ID."""
        if not profile_id:
            self.profile_var.set("Không dùng profile")
            self.profile_info_var.set("")
            return
        for label, pid in self._profile_map.items():
            if pid == profile_id:
                self.profile_var.set(label)
                self._on_profile_selected()
                return

    def update_model_choices(self, choices: list):
        """Update model choices list. Each item is (display_name, model_id)."""
        self._model_choices = choices
        display_names = [mc[0] for mc in choices]
        current = self.model_var.get()
        self.model_combo["values"] = display_names
        # Try to keep current selection
        if current in display_names:
            self.model_combo.set(current)
        elif display_names:
            self.model_combo.current(0)

    def update_profiles(self, profiles: list):
        """
        Update the voice profile dropdown.
        profiles: list of VoiceProfile objects with profile_id, name, audio_path, transcript, project
        """
        current_id = self.get_selected_profile_id()

        self._profile_map = {}
        self._profiles = {}

        labels = ["Không dùng profile"]
        for profile in profiles:
            label = profile.name
            if profile.project:
                label = f"{profile.name} - {profile.project}"
            self._profile_map[label] = profile.profile_id
            self._profiles[profile.profile_id] = profile
            labels.append(label)

        self.profile_combo["values"] = labels

        # Try to restore selection
        if current_id:
            restored = False
            for label, pid in self._profile_map.items():
                if pid == current_id:
                    self.profile_var.set(label)
                    restored = True
                    break
            if not restored:
                self.profile_var.set("Không dùng profile")
                self.profile_info_var.set("")
        else:
            self.profile_var.set("Không dùng profile")

        logger.info(f"Updated {len(profiles)} voice profiles")
