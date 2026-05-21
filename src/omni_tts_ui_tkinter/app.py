from __future__ import annotations

import os
import re
import threading
import tkinter as tk
import time
from pathlib import Path
from threading import Event
from tkinter import filedialog, messagebox, ttk
from urllib.parse import unquote, urlparse

from omni_tts_core.text.source_reader import SUPPORTED_TEXT_EXTENSIONS, count_source_text_chars
from omni_tts_core.progress import ProgressEvent
from omni_tts_shared.errors import GenerationCancelled, OmniTtsError
from omni_tts_shared.languages import LANGUAGE_CODES, LANGUAGE_LABELS, language_choices
from omni_tts_shared.voice_presets import NO_VOICE_PRESET_LABEL
from omni_tts_shared.vieneu_codecs import NO_CODEC_LABEL
from omni_tts_ui_tkinter.controller import TkinterController, format_result
from omni_tts_ui_tkinter.panels.generation_tabs import GenerationTabsMixin
from omni_tts_ui_tkinter.preferences import TkinterPreferences
from omni_tts_ui_tkinter.state import UiSettings
from omni_tts_ui_tkinter.widgets import (
    append_log,
    browse_directory,
    browse_file,
    clear_log,
)


class TkinterApp(GenerationTabsMixin):
    def __init__(self, root) -> None:
        self.root = root
        self.controller = TkinterController()
        self.preferences = TkinterPreferences()
        self.preference_data = self.preferences.load()
        self.model_map = dict(self.controller.model_choices())
        self.speaker_map: dict[str, str | None] = {NO_VOICE_PRESET_LABEL: None}
        self.codec_map: dict[str, str | None] = {NO_CODEC_LABEL: None}
        self.voice_profile_map: dict[str, str | None] = {}
        self.voice_profile_combos: list[ttk.Combobox] = []
        self.notebook: ttk.Notebook | None = None
        self.license_panel = None
        self.active_cancel_event: Event | None = None
        self.active_log_widget: tk.Text | None = None
        self.action_buttons: list[ttk.Button] = []
        self.text_output_dirs: list[Path] = []
        self.file_output_dirs: list[Path] = []
        self.source_file_items: dict[str, tuple[Path, int, str]] = {}
        self._source_file_next_id = 0
        self.text_open_folder_button: ttk.Button | None = None
        self.file_open_folder_button: ttk.Button | None = None
        self.language_combos: list[ttk.Combobox] = []
        self.profile_combos: list[ttk.Combobox] = []
        self.speaker_combos: list[ttk.Combobox] = []
        self.codec_combos: list[ttk.Combobox] = []
        self.mp3_bitrate_combos: list[ttk.Combobox] = []
        self.join_split_audio_checks: list[ttk.Checkbutton] = []
        self.output_audio_format_map = {"WAV": "wav", "MP3": "mp3"}
        self.runtime_target_map = dict(self.controller.runtime_target_choices())
        self.sampling_spins: list[ttk.Spinbox] = []
        self.speed_spins: list[ttk.Spinbox] = []
        self.pitch_spins: list[ttk.Spinbox] = []
        self.emotion_combos: list[ttk.Combobox] = []
        self.profile_compat_labels: list[ttk.Label] = []
        self._preference_trace_ready = False
        self._busy_tick_id: str | None = None
        self._geometry_save_id: str | None = None
        self._remembered_panes: list[tuple[ttk.Panedwindow, str]] = []
        self._last_progress_update = 0.0
        self._pending_progress_after = False
        self._pending_progress_event: ProgressEvent | None = None
        self._init_vars()
        self._configure_root()
        self._build_layout()
        self._sync_mp3_bitrate_state()
        self._sync_join_split_audio_state()
        self.refresh_models()
        self._bind_preference_traces()

    def _init_vars(self) -> None:
        model_label = self._model_label_for_id(self.preference_data.get("model_id"))
        model_id = self.model_map.get(model_label, "omnivoice_vietnamese")
        language = str(self.preference_data.get("language") or "vi")
        self.language_var = tk.StringVar(value=LANGUAGE_LABELS.get(language, "Tiếng Việt"))
        self.model_var = tk.StringVar(value=model_label)
        self.voice_profile_var = tk.StringVar(value="Không dùng profile")
        self.speaker_var = tk.StringVar(value=self._speaker_label_for_id(model_id, self.preference_data.get("speaker_id")))
        self.codec_var = tk.StringVar(value=self._codec_label_for_repo(model_id, self.preference_data.get("codec_repo")))
        self.ref_audio_var = tk.StringVar()
        self.ref_text_var = tk.StringVar()
        self.source_path_var = tk.StringVar()
        self.file_summary_var = tk.StringVar(value="Chưa có file.")
        self.output_dir_var = tk.StringVar(value=str(self.preference_data.get("output_dir") or ""))
        self.output_stem_var = tk.StringVar(value=str(self.preference_data.get("output_stem") or ""))
        self.speed_var = tk.DoubleVar(value=float(self.preference_data.get("speed", 1.0)))
        self.pitch_var = tk.DoubleVar(value=float(self.preference_data.get("pitch_shift", 0.0)))
        self.emotion_var = tk.StringVar(value=str(self.preference_data.get("emotion") or "natural"))
        self.runtime_target_var = tk.StringVar(
            value=self._runtime_target_label_for_value(self.preference_data.get("runtime_target"))
        )
        self.temperature_var = tk.DoubleVar(
            value=float(self.preference_data.get("temperature") or self.controller.default_vieneu_temperature(model_id))
        )
        self.top_k_var = tk.IntVar(
            value=int(self.preference_data.get("top_k") or self.controller.default_vieneu_top_k(model_id))
        )
        self.model_info_var = tk.StringVar(value="")
        self.runtime_var = tk.StringVar(value="")
        self.voice_source_var = tk.StringVar(value="")
        self.pause_var = tk.IntVar(value=int(self.preference_data.get("sentence_pause_ms", 450)))
        paragraph_pause = self.preference_data.get(
            "paragraph_pause_ms",
            self.preference_data.get("srt_file_padding_ms", 0),
        )
        self.paragraph_pause_var = tk.IntVar(value=int(paragraph_pause))
        self.chunk_var = tk.IntVar(value=int(self.preference_data.get("max_chunk_chars", 220)))
        self.overwrite_var = tk.BooleanVar(value=bool(self.preference_data.get("overwrite", False)))
        self.split_output_var = tk.BooleanVar(
            value=bool(self.preference_data.get("split_output", True))
        )
        output_format = str(self.preference_data.get("output_audio_format") or "wav").lower()
        self.output_audio_format_var = tk.StringVar(value="MP3" if output_format == "mp3" else "WAV")
        self.mp3_bitrate_var = tk.IntVar(value=int(self.preference_data.get("mp3_bitrate_kbps") or 192))
        self.output_srt_var = tk.BooleanVar(value=bool(self.preference_data.get("output_srt", False)))
        self.join_split_audio_var = tk.BooleanVar(
            value=bool(self.preference_data.get("join_split_output_audio", False))
        )
        self.status_var = tk.StringVar(value=self.controller.startup_notice())
        self.progress_var = tk.DoubleVar(value=0.0)
        self.profile_compat_var = tk.StringVar(value="")

    def _model_label_for_id(self, model_id: str | None) -> str:
        for label, item_id in self.model_map.items():
            if item_id == model_id:
                return label
        return "OmniVoice Vietnamese"

    def _speaker_label_for_id(self, model_id: str, speaker_id: str | None) -> str:
        if not speaker_id:
            return NO_VOICE_PRESET_LABEL
        for label, preset_id in self.controller.voice_preset_choices(model_id):
            if preset_id == speaker_id:
                return label
        return NO_VOICE_PRESET_LABEL

    def _current_model_id(self) -> str:
        return self.model_map.get(self.model_var.get(), "omnivoice_vietnamese")

    def _codec_label_for_repo(self, model_id: str, codec_repo: str | None) -> str:
        valid_repo = self.controller.valid_vieneu_codec_repo(model_id, codec_repo)
        if not valid_repo:
            valid_repo = self.controller.default_vieneu_codec_repo(model_id)
        for label, repo in self.controller.vieneu_codec_choices(model_id):
            if repo == valid_repo:
                return label
        return NO_CODEC_LABEL

    def _selected_profile_id(self) -> str | None:
        return self.voice_profile_map.get(self.voice_profile_var.get())

    def _selected_speaker_id(self) -> str | None:
        return self.speaker_map.get(self.speaker_var.get())

    def _selected_codec_repo(self) -> str | None:
        return self.codec_map.get(self.codec_var.get())

    def _selected_runtime_target(self) -> str:
        return self.runtime_target_map.get(self.runtime_target_var.get(), "auto")

    def _selected_output_audio_format(self) -> str:
        return self.output_audio_format_map.get(self.output_audio_format_var.get(), "wav")

    def _runtime_target_label_for_value(self, value: str | None) -> str:
        target = value or "auto"
        for label, item_value in self.controller.runtime_target_choices():
            if item_value == target:
                return label
        return "Auto (khuyến nghị)"

    def _refresh_codec_choices(self, model_id: str) -> None:
        if self.controller.model_supports_codec(model_id):
            current_repo = self._selected_codec_repo()
            # Fallback: codec_map not yet populated (startup) or was cleared by a non-codec
            # model → restore from the last saved preference so the user's choice is honoured.
            if current_repo is None:
                current_repo = self.preference_data.get("codec_repo")
            self.codec_map = {
                label: repo
                for label, repo in self.controller.vieneu_codec_choices(model_id)
            }
            values = list(self.codec_map.keys())
            for combo in self.codec_combos:
                combo.configure(values=values, state="readonly")
            valid_current = self.controller.valid_vieneu_codec_repo(model_id, current_repo)
            target_repo = valid_current or self.controller.default_vieneu_codec_repo(model_id)
            self.codec_var.set(self._codec_label_for_repo(model_id, target_repo))
            return
        self.codec_map = {NO_CODEC_LABEL: None}
        for combo in self.codec_combos:
            combo.configure(values=[NO_CODEC_LABEL], state="disabled")
        self.codec_var.set(NO_CODEC_LABEL)

    def _refresh_speaker_choices(
        self,
        model_id: str,
        *,
        include_none: bool,
        prefer_default: bool = False,
        allow_empty: bool = False,
    ) -> None:
        current_id = self._selected_speaker_id()
        self.speaker_map = {
            label: preset_id or None
            for label, preset_id in self.controller.voice_preset_choices(model_id, include_none=include_none)
        }
        values = list(self.speaker_map.keys())
        for combo in self.speaker_combos:
            combo.configure(values=values)

        if self._selected_profile_id() or not self.controller.has_voice_presets(model_id):
            self.speaker_var.set(NO_VOICE_PRESET_LABEL)
            return
        valid_current = self.controller.valid_voice_preset_id(model_id, current_id)
        if valid_current and not prefer_default:
            self.speaker_var.set(self._speaker_label_for_id(model_id, valid_current))
            return
        if allow_empty and self.speaker_var.get() == NO_VOICE_PRESET_LABEL and include_none:
            return
        default_id = self.controller.default_voice_preset_id(model_id)
        self.speaker_var.set(self._speaker_label_for_id(model_id, default_id))

    def _configure_root(self) -> None:
        self.root.title(self.controller.service.settings.app_display_name)
        geometry = str(self.preference_data.get("window_geometry") or "").strip()
        self.root.geometry(geometry or "1180x760")
        if self.preference_data.get("window_state") == "zoomed":
            self.root.state("zoomed")
        self.root.minsize(960, 640)
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        style = ttk.Style()
        style.configure("Accent.TButton", font=("Segoe UI", 10, "bold"))
        self.root.bind("<Configure>", self._schedule_geometry_save)
        self.root.bind_all("<ButtonRelease-1>", self._save_all_pane_sashes, add="+")
        self.root.protocol("WM_DELETE_WINDOW", self.close_app)

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

    def _schedule_geometry_save(self, event=None) -> None:
        if event is not None and event.widget is not self.root:
            return
        if self._geometry_save_id is not None:
            self.root.after_cancel(self._geometry_save_id)
        self._geometry_save_id = self.root.after(500, self._save_window_geometry)

    def _save_window_geometry(self) -> None:
        self._geometry_save_id = None
        state = self.root.state()
        if state != "iconic":
            self._save_ui_preference("window_state", state)
        geometry = self.root.geometry()
        if geometry and state != "iconic":
            self._save_ui_preference("window_geometry", geometry)

    def close_app(self) -> None:
        if self._geometry_save_id is not None:
            self.root.after_cancel(self._geometry_save_id)
            self._geometry_save_id = None
        self._save_window_geometry()
        self.root.destroy()

    def _remember_pane(self, paned: ttk.Panedwindow, preference_key: str) -> None:
        self._remembered_panes.append((paned, preference_key))
        paned.bind("<Map>", lambda _event, pane=paned, key=preference_key: self._restore_pane_sash(pane, key), add="+")
        paned.bind("<ButtonRelease-1>", lambda _event, pane=paned, key=preference_key: self._save_pane_sash(pane, key), add="+")
        self.root.after_idle(lambda pane=paned, key=preference_key: self._restore_pane_sash(pane, key))

    def _restore_pane_sash(self, paned: ttk.Panedwindow, preference_key: str, attempts: int = 8) -> None:
        width = paned.winfo_width()
        if width < 100:
            if attempts > 0:
                self.root.after(
                    100,
                    lambda pane=paned, key=preference_key, left=attempts - 1: self._restore_pane_sash(
                        pane,
                        key,
                        left,
                    ),
                )
            return

        ratio_key = preference_key.replace("_sash", "_ratio")
        ratio = self.preference_data.get(ratio_key)
        saved = self.preference_data.get(preference_key)
        position = None
        try:
            if ratio is not None:
                position = int(width * float(ratio))
            elif saved is not None:
                position = int(saved)
        except (TypeError, ValueError):
            position = None
        if position is None:
            return
        position = max(180, min(position, max(180, width - 260)))
        try:
            paned.sashpos(0, position)
        except tk.TclError:
            return

    def _save_pane_sash(self, paned: ttk.Panedwindow, preference_key: str) -> None:
        try:
            position = int(paned.sashpos(0))
        except (tk.TclError, TypeError, ValueError):
            return
        width = paned.winfo_width()
        if width > 0:
            ratio_key = preference_key.replace("_sash", "_ratio")
            self._save_ui_preference(ratio_key, round(position / width, 4))
        self._save_ui_preference(preference_key, position)

    def _save_all_pane_sashes(self, _event=None) -> None:
        for paned, preference_key in self._remembered_panes:
            if paned.winfo_exists() and paned.winfo_ismapped():
                self._save_pane_sash(paned, preference_key)

    def _save_ui_preference(self, key: str, value) -> None:
        if self.preference_data.get(key) == value:
            return
        self.preference_data[key] = value
        self.preferences.save(self.preference_data)

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

    def add_pasted_source_files(self) -> None:
        raw_text = self.source_path_var.get().strip()
        if not raw_text:
            return
        paths = self._parse_source_path_input(raw_text)
        if not paths:
            messagebox.showwarning("Thêm file", "Chưa tìm thấy đường dẫn file hợp lệ.")
            return
        if self._add_source_paths(paths):
            self.source_path_var.set("")

    def add_dropped_files(self, paths: list[Path]) -> None:
        self._add_source_paths(paths)

    def clear_source_files(self) -> None:
        for item_id in self.file_list.get_children():
            self.file_list.delete(item_id)
        self.source_file_items.clear()
        self._refresh_source_file_summary()

    def _add_source_paths(self, paths: list[Path]) -> int:
        existing = {item[2] for item in self.source_file_items.values()}
        added = 0
        skipped: list[str] = []
        duplicates = 0
        for path in paths:
            normalized = path.expanduser()
            key = self._source_file_key(normalized)
            if key in existing:
                duplicates += 1
                continue
            if not normalized.exists() or not normalized.is_file():
                skipped.append(f"{normalized} (không tìm thấy file)")
                continue
            if normalized.suffix.lower() not in SUPPORTED_TEXT_EXTENSIONS:
                skipped.append(f"{normalized} (chưa hỗ trợ định dạng này)")
                continue
            try:
                char_count = count_source_text_chars(normalized)
            except Exception as exc:
                skipped.append(f"{normalized} (không đọc được: {exc})")
                continue

            self._source_file_next_id += 1
            item_id = f"source_file_{self._source_file_next_id}"
            parent_label = normalized.parent.name or str(normalized.parent)
            self.source_file_items[item_id] = (normalized, char_count, key)
            self.file_list.insert(
                "",
                "end",
                iid=item_id,
                values=(normalized.name, parent_label, self._format_count(char_count)),
            )
            existing.add(key)
            added += 1
        self._refresh_source_file_summary()
        if skipped:
            messagebox.showwarning("Một số file chưa được thêm", "\n".join(skipped[:8]))
        elif duplicates and not added:
            messagebox.showinfo("Thêm file", "File này đã có trong danh sách.")
        return added

    def _parse_source_path_input(self, value: str) -> list[Path]:
        paths: list[Path] = []
        normalized = value.replace("\r\n", "\n").replace("\r", "\n")
        for raw_line in normalized.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            for token in self._source_path_tokens(line):
                paths.append(self._source_path_from_text(token))
        return paths

    def _source_path_tokens(self, line: str) -> list[str]:
        stripped = line.strip()
        if self._source_path_from_text(stripped).exists():
            return [stripped]
        quoted = re.findall(r'"([^"]+)"|\'([^\']+)\'', stripped)
        if quoted:
            return [double or single for double, single in quoted]
        if ";" in stripped:
            return [part.strip() for part in stripped.split(";") if part.strip()]
        return [stripped]

    def _source_path_from_text(self, value: str) -> Path:
        text = value.strip().strip('"').strip("'").strip()
        parsed = urlparse(text)
        if parsed.scheme.lower() == "file":
            if parsed.netloc:
                text = f"//{parsed.netloc}{unquote(parsed.path)}"
            else:
                text = unquote(parsed.path)
                if re.match(r"^/[A-Za-z]:", text):
                    text = text[1:]
        return Path(text)

    def _source_file_key(self, path: Path) -> str:
        return str(path.resolve(strict=False)).casefold()

    def _source_file_paths(self) -> list[Path]:
        return [
            self.source_file_items[item_id][0]
            for item_id in self.file_list.get_children()
            if item_id in self.source_file_items
        ]

    def _refresh_source_file_summary(self) -> None:
        count = len(self.source_file_items)
        if count == 0:
            self.file_summary_var.set("Chưa có file.")
            return
        total_chars = sum(item[1] for item in self.source_file_items.values())
        self.file_summary_var.set(
            f"{count} file • tổng {self._format_count(total_chars)} ký tự"
        )

    def _format_count(self, value: int) -> str:
        return f"{value:,}".replace(",", ".")

    def clear_text_log(self) -> None:
        clear_log(self.text_log)

    def clear_file_log(self) -> None:
        clear_log(self.file_log)

    def current_settings(self, for_files: bool = False) -> UiSettings:
        output_dir_text = self.output_dir_var.get().strip()
        ref_audio_text = self.ref_audio_var.get().strip()
        output_stem = None if for_files else self.output_stem_var.get().strip() or None
        split_output = bool(self.split_output_var.get())
        join_split_output_audio = split_output and bool(self.join_split_audio_var.get())
        return UiSettings(
            language=LANGUAGE_CODES.get(self.language_var.get(), "vi"),
            model_id=self._current_model_id(),
            voice_profile_id=self._selected_profile_id(),
            reference_audio_path=Path(ref_audio_text) if ref_audio_text else None,
            reference_text=self.ref_text_var.get().strip(),
            speaker_id=None if self._selected_profile_id() else self._selected_speaker_id(),
            speed=float(self.speed_var.get()),
            pitch_shift=float(self.pitch_var.get()),
            emotion=self.emotion_var.get(),
            runtime_target=self._selected_runtime_target(),
            codec_repo=self._selected_codec_repo() if self.controller.model_supports_codec(self._current_model_id()) else None,
            temperature=float(self.temperature_var.get()) if self.controller.model_supports_sampling(self._current_model_id()) else None,
            top_k=int(self.top_k_var.get()) if self.controller.model_supports_sampling(self._current_model_id()) else None,
            sentence_pause_ms=int(self.pause_var.get()),
            paragraph_pause_ms=int(self.paragraph_pause_var.get()),
            srt_file_padding_ms=int(self.paragraph_pause_var.get()),
            max_chunk_chars=int(self.chunk_var.get()),
            output_dir=Path(output_dir_text) if output_dir_text else None,
            output_stem=output_stem,
            overwrite=bool(self.overwrite_var.get()),
            split_output=split_output,
            output_audio_format=self._selected_output_audio_format(),
            mp3_bitrate_kbps=int(self.mp3_bitrate_var.get()),
            output_srt=bool(self.output_srt_var.get()),
            join_split_output_audio=join_split_output_audio,
        )

    def save_preferences(self) -> None:
        if not self._preference_trace_ready:
            return
        self.preference_data.update({
            "language": LANGUAGE_CODES.get(self.language_var.get(), "vi"),
            "model_id": self._current_model_id(),
            "voice_profile_id": self._selected_profile_id(),
            "speaker_id": None if self._selected_profile_id() else self._selected_speaker_id(),
            "output_dir": self.output_dir_var.get().strip(),
            "output_stem": self.output_stem_var.get().strip(),
            "speed": float(self.speed_var.get()),
            "pitch_shift": float(self.pitch_var.get()),
            "emotion": self.emotion_var.get(),
            "runtime_target": self._selected_runtime_target(),
            # Preserve the last codec the user explicitly chose; don't overwrite it with
            # None just because the currently-selected model doesn't support a codec picker.
            "codec_repo": (
                self._selected_codec_repo()
                if self.controller.model_supports_codec(self._current_model_id())
                else self.preference_data.get("codec_repo")
            ),
            "temperature": float(self.temperature_var.get()) if self.controller.model_supports_sampling(self._current_model_id()) else None,
            "top_k": int(self.top_k_var.get()) if self.controller.model_supports_sampling(self._current_model_id()) else None,
            "sentence_pause_ms": int(self.pause_var.get()),
            "paragraph_pause_ms": int(self.paragraph_pause_var.get()),
            "srt_file_padding_ms": int(self.paragraph_pause_var.get()),
            "max_chunk_chars": int(self.chunk_var.get()),
            "overwrite": bool(self.overwrite_var.get()),
            "split_output": bool(self.split_output_var.get()),
            "output_audio_format": self._selected_output_audio_format(),
            "mp3_bitrate_kbps": int(self.mp3_bitrate_var.get()),
            "output_srt": bool(self.output_srt_var.get()),
            "join_split_output_audio": bool(self.split_output_var.get()) and bool(self.join_split_audio_var.get()),
        })
        self.preferences.save(self.preference_data)

    def _bind_preference_traces(self) -> None:
        variables = [
            self.language_var,
            self.model_var,
            self.voice_profile_var,
            self.speaker_var,
            self.codec_var,
            self.output_dir_var,
            self.output_stem_var,
            self.speed_var,
            self.pitch_var,
            self.emotion_var,
            self.runtime_target_var,
            self.temperature_var,
            self.top_k_var,
            self.pause_var,
            self.paragraph_pause_var,
            self.chunk_var,
            self.overwrite_var,
            self.split_output_var,
            self.output_audio_format_var,
            self.mp3_bitrate_var,
            self.output_srt_var,
            self.join_split_audio_var,
        ]
        for variable in variables:
            variable.trace_add("write", lambda *_args: self.save_preferences())
        self.output_audio_format_var.trace_add("write", lambda *_args: self._sync_mp3_bitrate_state())
        self.split_output_var.trace_add("write", lambda *_args: self._sync_join_split_audio_state())
        self._preference_trace_ready = True
        self.save_preferences()

    def _sync_mp3_bitrate_state(self) -> None:
        state = "readonly" if self._selected_output_audio_format() == "mp3" else "disabled"
        for combo in self.mp3_bitrate_combos:
            combo.configure(state=state)

    def on_split_output_changed(self) -> None:
        self._sync_join_split_audio_state()
        self.save_preferences()

    def _sync_join_split_audio_state(self) -> None:
        split_enabled = bool(self.split_output_var.get())
        if not split_enabled and bool(self.join_split_audio_var.get()):
            self.join_split_audio_var.set(False)
        state = "normal" if split_enabled else "disabled"
        for check in self.join_split_audio_checks:
            check.configure(state=state)

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
        paths = self._source_file_paths()
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
            f"Profile: {self.voice_profile_var.get()}; Preset giọng: {self.speaker_var.get()}; "
            f"Codec: {self.codec_var.get()}; Thiết bị xử lý: {self.controller.runtime_target_label(settings.runtime_target)}\n"
            f"Temperature: {settings.temperature or 'mặc định'}; Top-K: {settings.top_k or 'mặc định'}; "
            f"Độ dài đoạn nhỏ: {settings.max_chunk_chars}; "
            f"Nghỉ giữa câu/chunk: {settings.sentence_pause_ms} ms; "
            f"Nghỉ giữa đoạn trong file tổng: {settings.paragraph_pause_ms} ms\n"
            f"Tách file: {'Có' if settings.split_output else 'Không'}; "
            f"Định dạng audio: {settings.output_audio_format.upper()}"
            f"{f' {settings.mp3_bitrate_kbps} kbps' if settings.output_audio_format == 'mp3' else ''}; "
            f"Xuất SRT: {'Có' if settings.output_srt else 'Không'}; "
            f"File audio tổng: {'Có' if settings.join_split_output_audio else 'Không'}; "
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
                    _model_status_label(item),
                    self.controller.runtime_device_label(runtime.actual_device),
                    item.size_mb,
                    str(item.local_path),
                ),
            )
        self.update_runtime_label()
        self.refresh_license_status()
        self.status_var.set(self.controller.startup_notice())
        self.apply_model_capabilities()

    def update_runtime_label(self) -> None:
        model_id = self._current_model_id()
        self.model_info_var.set(self.controller.model_choice_info(model_id))
        self.runtime_var.set(self.controller.runtime_status_text(model_id))

    def _update_profile_compat(self) -> None:
        profile_id = self._selected_profile_id()
        model_id = self._current_model_id()
        if not profile_id:
            self.profile_compat_var.set("")
            for label in self.profile_compat_labels:
                label.configure(foreground="#555555")
            return
        try:
            compat = self.controller.profile_quality_for_model(profile_id, model_id)
        except Exception:
            self.profile_compat_var.set("")
            return
        self.profile_compat_var.set(compat.message)
        color = {"ok": "#2e7d32", "warn": "#e65100", "error": "#c62828"}.get(compat.status, "#555555")
        for label in self.profile_compat_labels:
            label.configure(foreground=color)

    def on_model_changed(self) -> None:
        self.update_runtime_label()
        self.apply_model_capabilities(prefer_default_preset=True)
        self._update_profile_compat()

    def on_voice_profile_changed(self) -> None:
        if self._selected_profile_id():
            self.speaker_var.set(NO_VOICE_PRESET_LABEL)
        self.apply_model_capabilities()
        self._update_profile_compat()

    def on_voice_preset_changed(self) -> None:
        if self._selected_speaker_id():
            self.voice_profile_var.set("Không dùng profile")
        self.apply_model_capabilities(allow_empty_preset=True)

    def apply_model_capabilities(
        self,
        prefer_default_preset: bool = False,
        allow_empty_preset: bool = False,
    ) -> None:
        model_id = self._current_model_id()
        caps = self.controller.model_capabilities(model_id)
        self._refresh_codec_choices(model_id)
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

        supports_sampling = self.controller.model_supports_sampling(model_id)
        _set_widgets_state(self.sampling_spins, supports_sampling)
        if supports_sampling and prefer_default_preset:
            self.temperature_var.set(self.controller.default_vieneu_temperature(model_id))
            self.top_k_var.set(self.controller.default_vieneu_top_k(model_id))
        elif not supports_sampling:
            self.temperature_var.set(1.0)
            self.top_k_var.set(50)

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

        self._refresh_speaker_choices(
            model_id,
            include_none=caps.supports_voice_profile,
            prefer_default=prefer_default_preset,
            allow_empty=allow_empty_preset,
        )
        speaker_selected = self._selected_speaker_id() is not None

        profile_state = "readonly" if caps.supports_voice_profile and not speaker_selected else "disabled"
        for combo in self.profile_combos:
            combo.configure(state=profile_state)
        if not caps.supports_voice_profile:
            self.voice_profile_var.set("Không dùng profile")

        profile_selected = self._selected_profile_id() is not None
        speaker_state = "readonly" if self.controller.has_voice_presets(model_id) and not profile_selected else "disabled"
        for combo in self.speaker_combos:
            combo.configure(state=speaker_state)
        if self.speaker_var.get() not in self.speaker_map:
            self.speaker_var.set(NO_VOICE_PRESET_LABEL)

        self._update_voice_source_label(caps)
        if caps.requires_voice_profile and self.voice_profile_var.get() == "Không dùng profile":
            self.status_var.set(f"{self.model_var.get()} cần chọn Profile giọng.")
        self.save_preferences()

    def _update_voice_source_label(self, caps) -> None:
        profile = self.voice_profile_var.get()
        preset = self.speaker_var.get()
        if self._selected_profile_id():
            self.voice_source_var.set(f"Nguồn giọng đang dùng: Profile - {profile}")
        elif self._selected_speaker_id():
            self.voice_source_var.set(f"Nguồn giọng đang dùng: Preset - {preset}")
        elif caps.requires_voice_profile:
            self.voice_source_var.set("Nguồn giọng: cần chọn Profile giọng")
        elif caps.supports_voice_presets and caps.supports_voice_profile:
            self.voice_source_var.set("Nguồn giọng: chọn Preset hoặc Profile giọng")
        elif caps.supports_voice_presets:
            self.voice_source_var.set("Nguồn giọng: cần chọn Preset giọng")
        elif caps.supports_voice_profile:
            self.voice_source_var.set("Nguồn giọng: mặc định của model hoặc Profile giọng")
        else:
            self.voice_source_var.set("Nguồn giọng: mặc định của model")

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
        self._update_profile_compat()

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

    def install_gpu_for_selected_model(self) -> None:
        selected = self.model_table.selection()
        if not selected:
            messagebox.showinfo("Thông báo", "Hãy chọn một model trong bảng.")
            return
        self._run_background(
            "Đang cài tăng tốc GPU...",
            lambda _progress, _cancel: self.controller.install_gpu_for_model(selected[0]),
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


def _model_status_label(item) -> str:
    if item.worker_installed is None:
        return "Đã tải" if item.installed else "Chưa tải"
    if not item.worker_installed:
        return "Chưa cài worker"
    if not item.hf_cached:
        return "Worker OK"
    return "Sẵn sàng"


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
