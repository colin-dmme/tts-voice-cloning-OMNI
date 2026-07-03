from __future__ import annotations

import os
import threading
import tkinter as tk
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from threading import Event
from tkinter import filedialog, messagebox, ttk

from omni_tts_core.file_queue import (
    STATUS_LABELS,
    FileQueueItem,
    FileQueueOutputManifest,
    FileQueueStatus,
    FileQueueStore,
    settings_fingerprint,
)
from omni_tts_core.text.source_reader import SUPPORTED_TEXT_EXTENSIONS, count_source_text_chars
from omni_tts_core.progress import ProgressCallback, ProgressEvent, check_cancel
from omni_tts_shared.errors import GenerationCancelled, OmniTtsError
from omni_tts_shared.languages import LANGUAGE_CODES, LANGUAGE_LABELS, language_choices
from omni_tts_shared.voice_presets import NO_VOICE_PRESET_LABEL
from omni_tts_shared.vieneu_codecs import NO_CODEC_LABEL
from omni_tts_ui_tkinter.controller import (
    FileGenerationEvent,
    FileGenerationOutcome,
    TkinterController,
    format_result,
)
from omni_tts_ui_tkinter.panels.generation_tabs import GenerationTabsMixin
from omni_tts_ui_tkinter.path_intake import parse_path_text
from omni_tts_ui_tkinter.preferences import TkinterPreferences
from omni_tts_ui_tkinter.state import UiSettings
from omni_tts_ui_tkinter.widgets import (
    append_log,
    browse_directory,
    browse_file,
    clear_log,
)


FILE_FILTERS: dict[str, FileQueueStatus | None] = {
    "Tất cả": None,
    **{label: status for status, label in STATUS_LABELS.items()},
}

RESULT_PATH_KIND_LABELS = {
    "all": "tất cả kết quả",
    "split_dirs": "thư mục file lẻ",
    "split_audio": "file audio lẻ",
    "merged_audio": "file gộp",
    "srt": "SRT",
}

RESULT_PATH_KIND_SLUGS = {
    "all": "all-results",
    "split_dirs": "split-folders",
    "split_audio": "split-audio",
    "merged_audio": "merged-audio",
    "srt": "srt",
}

RESULT_PATH_SCOPE_SLUGS = {
    "selected": "selected-queue",
    "all_done": "all-done-queues",
}


@dataclass(frozen=True)
class SourceImportResult:
    added_items: tuple[FileQueueItem, ...]
    duplicates: int
    skipped: tuple[str, ...]
    total: int

    @property
    def added_count(self) -> int:
        return len(self.added_items)


class TkinterApp(GenerationTabsMixin):
    def __init__(self, root) -> None:
        self.root = root
        self.controller = TkinterController()
        self.preferences = TkinterPreferences()
        self.file_queue_store = FileQueueStore()
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
        self.source_file_items: dict[str, FileQueueItem] = {}
        self._file_progress_cache: dict[str, int] = {}
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
        self.f5_controls: list = []
        self.chatterbox_controls: list = []
        self.emotion_combos: list[ttk.Combobox] = []
        self.profile_compat_labels: list[ttk.Label] = []
        self._preference_trace_ready = False
        self._model_refresh_running = False
        self._busy_tick_id: str | None = None
        self._geometry_save_id: str | None = None
        self._remembered_panes: list[tuple[ttk.Panedwindow, str]] = []
        self._last_progress_update = 0.0
        self._pending_progress_after = False
        self._pending_progress_event: ProgressEvent | None = None
        self._init_vars()
        self._configure_root()
        self._build_layout()
        self._restore_source_file_queue()
        self._sync_mp3_bitrate_state()
        self._sync_join_split_audio_state()
        self._prepare_initial_model_view()
        self._bind_preference_traces()
        self.root.after(500, self.refresh_models)

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
        self.file_summary_var = tk.StringVar(value="Chưa có file.")
        self.file_filter_var = tk.StringVar(value="Tất cả")
        self.file_search_var = tk.StringVar()
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
        f5_defaults = self.controller.default_f5_settings(model_id)
        self.f5_nfe_step_var = tk.IntVar(
            value=int(self.preference_data.get("f5_nfe_step") or f5_defaults["f5_nfe_step"])
        )
        self.f5_cfg_strength_var = tk.DoubleVar(
            value=float(self.preference_data.get("f5_cfg_strength") or f5_defaults["f5_cfg_strength"])
        )
        self.f5_sway_sampling_coef_var = tk.DoubleVar(
            value=float(
                self.preference_data.get("f5_sway_sampling_coef")
                if self.preference_data.get("f5_sway_sampling_coef") is not None
                else f5_defaults["f5_sway_sampling_coef"]
            )
        )
        self.f5_cross_fade_duration_var = tk.DoubleVar(
            value=float(
                self.preference_data.get("f5_cross_fade_duration")
                or f5_defaults["f5_cross_fade_duration"]
            )
        )
        self.f5_target_rms_var = tk.DoubleVar(
            value=float(self.preference_data.get("f5_target_rms") or f5_defaults["f5_target_rms"])
        )
        self.f5_remove_silence_var = tk.BooleanVar(
            value=bool(self.preference_data.get("f5_remove_silence", f5_defaults["f5_remove_silence"]))
        )
        self.f5_seed_var = tk.StringVar(value=_optional_text(self.preference_data.get("f5_seed")))
        self.f5_fix_duration_var = tk.DoubleVar(
            value=float(self.preference_data.get("f5_fix_duration") or 0.0)
        )
        chatterbox_defaults = self.controller.default_chatterbox_settings(model_id)
        self.chatterbox_temperature_var = tk.DoubleVar(
            value=float(
                self.preference_data.get("chatterbox_temperature")
                or chatterbox_defaults["chatterbox_temperature"]
            )
        )
        self.chatterbox_top_p_var = tk.DoubleVar(
            value=float(self.preference_data.get("chatterbox_top_p") or chatterbox_defaults["chatterbox_top_p"])
        )
        self.chatterbox_top_k_var = tk.IntVar(
            value=int(self.preference_data.get("chatterbox_top_k") or chatterbox_defaults["chatterbox_top_k"])
        )
        self.chatterbox_repetition_penalty_var = tk.DoubleVar(
            value=float(
                self.preference_data.get("chatterbox_repetition_penalty")
                or chatterbox_defaults["chatterbox_repetition_penalty"]
            )
        )
        self.chatterbox_seed_var = tk.StringVar(value=_optional_text(self.preference_data.get("chatterbox_seed")))
        self.chatterbox_norm_loudness_var = tk.BooleanVar(
            value=bool(
                self.preference_data.get(
                    "chatterbox_norm_loudness",
                    chatterbox_defaults["chatterbox_norm_loudness"],
                )
            )
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
        if not self._can_edit_file_queue():
            return
        paths = filedialog.askopenfilenames(
            title="Chọn file nguồn",
            filetypes=[("Text/SRT", "*.txt *.md *.srt"), ("Tất cả", "*.*")],
        )
        self._start_source_file_import([Path(path) for path in paths])

    def add_clipboard_source_files(self) -> None:
        if not self._can_edit_file_queue():
            return
        try:
            raw_text = self.root.clipboard_get()
        except tk.TclError:
            messagebox.showinfo("Dán từ clipboard", "Clipboard không có đường dẫn dạng text.")
            return
        paths = self._parse_source_path_input(raw_text)
        if not paths:
            messagebox.showwarning("Dán từ clipboard", "Chưa tìm thấy đường dẫn file hợp lệ.")
            return
        self._start_source_file_import(paths)

    def add_pasted_source_files(self) -> None:
        self.add_clipboard_source_files()

    def add_dropped_files(self, paths: list[Path]) -> None:
        if not self._can_edit_file_queue():
            return
        self._start_source_file_import(paths)

    def clear_source_files(self) -> None:
        if not self._can_edit_file_queue():
            return
        if not self.source_file_items:
            return
        if not messagebox.askyesno(
            "Xóa toàn bộ",
            f"Xóa {len(self.source_file_items)} file khỏi danh sách?",
        ):
            return
        self.file_queue_store.clear()
        self._reload_source_file_queue()

    def remove_selected_source_files(self) -> None:
        if not self._can_edit_file_queue():
            return
        item_ids = self._selected_source_item_ids()
        if not item_ids:
            messagebox.showinfo("Xóa file", "Hãy chọn ít nhất một file trong danh sách.")
            return
        self.file_queue_store.delete(item_ids)
        self._reload_source_file_queue()

    def remove_filtered_source_files(self) -> None:
        if not self._can_edit_file_queue():
            return
        item_ids = [
            item.item_id
            for item in self.source_file_items.values()
            if self._source_item_matches_filter(item)
        ]
        if not item_ids:
            messagebox.showinfo("Xóa theo bộ lọc", "Bộ lọc hiện tại không có file.")
            return
        if not messagebox.askyesno(
            "Xóa theo bộ lọc",
            f"Xóa {len(item_ids)} file đang khớp bộ lọc?",
        ):
            return
        self.file_queue_store.delete(item_ids)
        self._reload_source_file_queue()

    def reset_selected_source_files(self) -> None:
        if not self._can_edit_file_queue():
            return
        item_ids = self._selected_source_item_ids()
        if not item_ids:
            messagebox.showinfo("Đặt lại trạng thái", "Hãy chọn ít nhất một file.")
            return
        self.file_queue_store.reset(item_ids)
        self._reload_source_file_queue(select_ids=item_ids)

    def _can_edit_file_queue(self) -> bool:
        if self.active_cancel_event is None:
            return True
        messagebox.showinfo(
            "Danh sách đang chạy",
            "Hãy đợi tác vụ hoàn tất hoặc bấm Hủy trước khi sửa danh sách.",
        )
        return False

    def select_all_visible_source_files(self, _event=None) -> str:
        children = self.file_list.get_children()
        if children:
            self.file_list.selection_set(children)
        return "break"

    def _add_source_paths(self, paths: list[Path]) -> None:
        self._start_source_file_import(paths)

    def _start_source_file_import(self, paths: list[Path]) -> None:
        if not paths:
            return
        if self.active_cancel_event is not None:
            self._can_edit_file_queue()
            return
        total = len(paths)
        self._run_background(
            f"Đang thêm {self._format_count(total)} file vào danh sách...",
            lambda progress, cancel: self._import_source_paths(paths, progress, cancel),
            self._handle_source_import_result,
        )

    def _import_source_paths(
        self,
        paths: list[Path],
        progress: ProgressCallback | None,
        cancel_event: Event | None,
    ) -> SourceImportResult:
        entries: list[tuple[Path, int]] = []
        skipped: list[str] = []
        total = len(paths)
        for index, path in enumerate(paths, start=1):
            check_cancel(cancel_event)
            normalized = path.expanduser().resolve(strict=False)
            if not normalized.exists() or not normalized.is_file():
                skipped.append(f"{normalized} (không tìm thấy file)")
            elif normalized.suffix.lower() not in SUPPORTED_TEXT_EXTENSIONS:
                skipped.append(f"{normalized} (chưa hỗ trợ định dạng này)")
            else:
                try:
                    char_count = count_source_text_chars(normalized)
                except Exception as exc:
                    skipped.append(f"{normalized} (không đọc được: {exc})")
                else:
                    entries.append((normalized, char_count))

            if progress is not None and (index == total or index % 25 == 0):
                progress(
                    ProgressEvent(
                        f"Đang kiểm tra file {self._format_count(index)}/{self._format_count(total)}",
                        index,
                        total + 1,
                    )
                )

        check_cancel(cancel_event)
        if progress is not None:
            progress(ProgressEvent("Đang ghi vào danh sách", total, total + 1))
        added_items, duplicates = self.file_queue_store.add_many(entries)
        return SourceImportResult(
            added_items=tuple(added_items),
            duplicates=duplicates,
            skipped=tuple(skipped),
            total=total,
        )

    def _handle_source_import_result(self, result: SourceImportResult) -> str:
        self._reload_source_file_queue(
            select_ids=[item.item_id for item in result.added_items]
        )
        if result.skipped:
            messagebox.showwarning(
                "Một số file chưa được thêm",
                "\n".join(self._format_source_import_skips(result.skipped)),
            )
        elif result.duplicates and result.added_count == 0:
            messagebox.showinfo("Thêm file", "Các file này đã có trong danh sách.")
        return self._source_import_summary(result)

    def _parse_source_path_input(self, value: str) -> list[Path]:
        return parse_path_text(value, self.root.tk.splitlist)

    def _source_import_summary(self, result: SourceImportResult) -> str:
        parts = [f"Đã thêm {self._format_count(result.added_count)} file"]
        if result.duplicates:
            parts.append(f"trùng {self._format_count(result.duplicates)}")
        if result.skipped:
            parts.append(f"bỏ qua {self._format_count(len(result.skipped))}")
        return "; ".join(parts) + "."

    def _format_source_import_skips(self, skipped: tuple[str, ...]) -> list[str]:
        lines = list(skipped[:8])
        remaining = len(skipped) - len(lines)
        if remaining > 0:
            lines.append(f"... và {self._format_count(remaining)} file khác.")
        return lines

    def _source_file_key(self, path: Path) -> str:
        return str(path.resolve(strict=False)).casefold()

    def _restore_source_file_queue(self) -> None:
        self.file_queue_store.recover_and_validate()
        self._reload_source_file_queue()
        self.file_search_var.trace_add("write", lambda *_args: self._refresh_source_file_list())

    def _reload_source_file_queue(self, select_ids: list[str] | None = None) -> None:
        self.source_file_items = {
            item.item_id: item
            for item in self.file_queue_store.list_items()
        }
        self._refresh_source_file_list(select_ids=select_ids)

    def _refresh_source_file_list(self, select_ids: list[str] | None = None) -> None:
        previous_selection = set(select_ids or self.file_list.selection())
        for item_id in self.file_list.get_children():
            self.file_list.delete(item_id)
        for item in sorted(self.source_file_items.values(), key=lambda value: value.position):
            if not self._source_item_matches_filter(item):
                continue
            self.file_list.insert(
                "",
                "end",
                iid=item.item_id,
                values=self._source_item_values(item),
                tags=(item.status.value,),
            )
        visible_selection = [
            item_id for item_id in previous_selection
            if self.file_list.exists(item_id)
        ]
        if visible_selection:
            self.file_list.selection_set(visible_selection)
        self._refresh_source_file_summary()

    def _source_item_matches_filter(self, item: FileQueueItem) -> bool:
        selected_status = FILE_FILTERS.get(self.file_filter_var.get())
        if selected_status is not None and item.status != selected_status:
            return False
        search = self.file_search_var.get().strip().casefold()
        if not search:
            return True
        haystack = f"{item.source_path.name} {item.source_path.parent}".casefold()
        return search in haystack

    def _source_item_values(self, item: FileQueueItem) -> tuple[str, ...]:
        detail = item.last_error if item.status == FileQueueStatus.FAILED else item.status_detail
        if item.status == FileQueueStatus.DONE and item.output_paths:
            detail = item.output_paths[0].name
        return (
            STATUS_LABELS[item.status],
            item.source_path.name,
            item.source_path.parent.name or str(item.source_path.parent),
            self._format_count(item.char_count),
            f"{item.progress_percent:.0f}%",
            str(item.attempt_count),
            _short_display(detail, 90),
        )

    def _selected_source_item_ids(self) -> list[str]:
        return [
            item_id
            for item_id in self.file_list.selection()
            if item_id in self.source_file_items
        ]

    def _source_items_for_run(self, mode: str) -> list[FileQueueItem]:
        if mode == "selected":
            item_ids = self._selected_source_item_ids()
            return [
                self.source_file_items[item_id]
                for item_id in item_ids
                if self.source_file_items[item_id].status != FileQueueStatus.RUNNING
            ]
        if mode == "failed":
            statuses = {FileQueueStatus.FAILED}
        else:
            statuses = {FileQueueStatus.PENDING}
        return [
            item
            for item in sorted(self.source_file_items.values(), key=lambda value: value.position)
            if item.status in statuses
        ]

    def _refresh_source_file_summary(self) -> None:
        count = len(self.source_file_items)
        if count == 0:
            self.file_summary_var.set("Chưa có file.")
            return
        total_chars = sum(item.char_count for item in self.source_file_items.values())
        status_counts = {
            status: sum(1 for item in self.source_file_items.values() if item.status == status)
            for status in FileQueueStatus
        }
        visible_count = len(self.file_list.get_children())
        status_summary = " • ".join(
            f"{STATUS_LABELS[status]}: {value}"
            for status, value in status_counts.items()
            if value
        )
        self.file_summary_var.set(
            f"{visible_count}/{count} file • {self._format_count(total_chars)} ký tự"
            f"{f' • {status_summary}' if status_summary else ''}"
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
        model_id = self._current_model_id()
        supports_f5 = self.controller.model_supports_f5_settings(model_id)
        supports_chatterbox = self.controller.model_supports_chatterbox_settings(model_id)
        return UiSettings(
            language=LANGUAGE_CODES.get(self.language_var.get(), "vi"),
            model_id=model_id,
            voice_profile_id=self._selected_profile_id(),
            reference_audio_path=Path(ref_audio_text) if ref_audio_text else None,
            reference_text=self.ref_text_var.get().strip(),
            speaker_id=None if self._selected_profile_id() else self._selected_speaker_id(),
            speed=float(self.speed_var.get()),
            pitch_shift=float(self.pitch_var.get()),
            emotion=self.emotion_var.get(),
            runtime_target=self._selected_runtime_target(),
            codec_repo=self._selected_codec_repo() if self.controller.model_supports_codec(model_id) else None,
            temperature=float(self.temperature_var.get()) if self.controller.model_supports_sampling(model_id) else None,
            top_k=int(self.top_k_var.get()) if self.controller.model_supports_sampling(model_id) else None,
            f5_nfe_step=int(self.f5_nfe_step_var.get()) if supports_f5 else None,
            f5_cfg_strength=float(self.f5_cfg_strength_var.get()) if supports_f5 else None,
            f5_sway_sampling_coef=float(self.f5_sway_sampling_coef_var.get()) if supports_f5 else None,
            f5_cross_fade_duration=float(self.f5_cross_fade_duration_var.get()) if supports_f5 else None,
            f5_target_rms=float(self.f5_target_rms_var.get()) if supports_f5 else None,
            f5_remove_silence=bool(self.f5_remove_silence_var.get()) if supports_f5 else False,
            f5_seed=_optional_int(self.f5_seed_var.get()) if supports_f5 else None,
            f5_fix_duration=_optional_positive_float(self.f5_fix_duration_var.get()) if supports_f5 else None,
            chatterbox_temperature=(
                float(self.chatterbox_temperature_var.get()) if supports_chatterbox else None
            ),
            chatterbox_top_p=float(self.chatterbox_top_p_var.get()) if supports_chatterbox else None,
            chatterbox_top_k=int(self.chatterbox_top_k_var.get()) if supports_chatterbox else None,
            chatterbox_repetition_penalty=(
                float(self.chatterbox_repetition_penalty_var.get()) if supports_chatterbox else None
            ),
            chatterbox_seed=_optional_int(self.chatterbox_seed_var.get()) if supports_chatterbox else None,
            chatterbox_norm_loudness=(
                bool(self.chatterbox_norm_loudness_var.get()) if supports_chatterbox else True
            ),
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
        model_id = self._current_model_id()
        supports_f5 = self.controller.model_supports_f5_settings(model_id)
        supports_chatterbox = self.controller.model_supports_chatterbox_settings(model_id)
        self.preference_data.update({
            "language": LANGUAGE_CODES.get(self.language_var.get(), "vi"),
            "model_id": model_id,
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
                if self.controller.model_supports_codec(model_id)
                else self.preference_data.get("codec_repo")
            ),
            "temperature": float(self.temperature_var.get()) if self.controller.model_supports_sampling(model_id) else None,
            "top_k": int(self.top_k_var.get()) if self.controller.model_supports_sampling(model_id) else None,
            "f5_nfe_step": int(self.f5_nfe_step_var.get()) if supports_f5 else self.preference_data.get("f5_nfe_step"),
            "f5_cfg_strength": (
                float(self.f5_cfg_strength_var.get()) if supports_f5 else self.preference_data.get("f5_cfg_strength")
            ),
            "f5_sway_sampling_coef": (
                float(self.f5_sway_sampling_coef_var.get())
                if supports_f5
                else self.preference_data.get("f5_sway_sampling_coef")
            ),
            "f5_cross_fade_duration": (
                float(self.f5_cross_fade_duration_var.get())
                if supports_f5
                else self.preference_data.get("f5_cross_fade_duration")
            ),
            "f5_target_rms": (
                float(self.f5_target_rms_var.get()) if supports_f5 else self.preference_data.get("f5_target_rms")
            ),
            "f5_remove_silence": (
                bool(self.f5_remove_silence_var.get())
                if supports_f5
                else self.preference_data.get("f5_remove_silence", False)
            ),
            "f5_seed": _optional_int(self.f5_seed_var.get()) if supports_f5 else self.preference_data.get("f5_seed"),
            "f5_fix_duration": (
                _optional_positive_float(self.f5_fix_duration_var.get())
                if supports_f5
                else self.preference_data.get("f5_fix_duration")
            ),
            "chatterbox_temperature": (
                float(self.chatterbox_temperature_var.get())
                if supports_chatterbox
                else self.preference_data.get("chatterbox_temperature")
            ),
            "chatterbox_top_p": (
                float(self.chatterbox_top_p_var.get())
                if supports_chatterbox
                else self.preference_data.get("chatterbox_top_p")
            ),
            "chatterbox_top_k": (
                int(self.chatterbox_top_k_var.get())
                if supports_chatterbox
                else self.preference_data.get("chatterbox_top_k")
            ),
            "chatterbox_repetition_penalty": (
                float(self.chatterbox_repetition_penalty_var.get())
                if supports_chatterbox
                else self.preference_data.get("chatterbox_repetition_penalty")
            ),
            "chatterbox_seed": (
                _optional_int(self.chatterbox_seed_var.get())
                if supports_chatterbox
                else self.preference_data.get("chatterbox_seed")
            ),
            "chatterbox_norm_loudness": (
                bool(self.chatterbox_norm_loudness_var.get())
                if supports_chatterbox
                else self.preference_data.get("chatterbox_norm_loudness", True)
            ),
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
            self.f5_nfe_step_var,
            self.f5_cfg_strength_var,
            self.f5_sway_sampling_coef_var,
            self.f5_cross_fade_duration_var,
            self.f5_target_rms_var,
            self.f5_remove_silence_var,
            self.f5_seed_var,
            self.f5_fix_duration_var,
            self.chatterbox_temperature_var,
            self.chatterbox_top_p_var,
            self.chatterbox_top_k_var,
            self.chatterbox_repetition_penalty_var,
            self.chatterbox_seed_var,
            self.chatterbox_norm_loudness_var,
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

    def generate_from_files(self, mode: str = "pending") -> None:
        settings = self.current_settings(for_files=True)
        if not self._show_license_problem(settings.model_id):
            return
        fingerprint = settings_fingerprint(asdict(settings))
        selected_ids = self._selected_source_item_ids()
        self.file_queue_store.mark_settings_outdated(fingerprint)
        self._reload_source_file_queue(select_ids=selected_ids)
        items = self._source_items_for_run(mode)
        if not items:
            messages = {
                "selected": "Hãy chọn ít nhất một file để chạy.",
                "failed": "Không có file lỗi để chạy lại.",
                "pending": "Không có file nào đang chờ chạy.",
            }
            messagebox.showinfo("Xử lý file", messages.get(mode, "Không có file để chạy."))
            return
        tasks = [(item.item_id, item.source_path) for item in items]
        self.file_output_dirs = []
        self._set_open_button_state(self.file_open_folder_button, self.file_output_dirs)
        append_log(self.file_log, self._generation_summary(settings, f"Số file sẽ chạy: {len(items)}"))
        for item in items:
            append_log(self.file_log, f"[{STATUS_LABELS[item.status]}] {item.source_path}")
        self._run_background(
            "Đang xử lý danh sách file...",
            lambda progress, cancel: self.controller.generate_files(
                tasks,
                settings,
                progress_callback=progress,
                file_event_callback=lambda event: self._record_file_generation_event(
                    event,
                    fingerprint,
                ),
                cancel_event=cancel,
            ),
            self._log_file_results,
            log_widget=self.file_log,
        )

    def _handle_text_result(self, result) -> None:
        append_log(self.text_log, format_result(result))
        self.text_output_dirs = _result_output_dirs([result])
        self._set_open_button_state(self.text_open_folder_button, self.text_output_dirs)

    def _record_file_generation_event(
        self,
        event: FileGenerationEvent,
        fingerprint: str,
    ) -> None:
        if event.status == FileQueueStatus.RUNNING:
            if event.message == "Đang khởi tạo...":
                self.file_queue_store.mark_running(event.item_id)
                self._file_progress_cache[event.item_id] = 0
            else:
                rounded = int(event.progress_percent)
                if self._file_progress_cache.get(event.item_id) != rounded:
                    self.file_queue_store.update_progress(
                        event.item_id,
                        event.progress_percent,
                        event.message,
                    )
                    self._file_progress_cache[event.item_id] = rounded
        elif event.status == FileQueueStatus.DONE and event.result is not None:
            self.file_queue_store.mark_done(
                event.item_id,
                job_id=event.result.job_id,
                output_paths=_result_output_paths(event.result),
                fingerprint=fingerprint,
                output_manifest=_result_output_manifest(event.result),
                detail=event.result.message,
            )
        elif event.status == FileQueueStatus.FAILED:
            self.file_queue_store.mark_failed(event.item_id, event.error or event.message)
        elif event.status == FileQueueStatus.CANCELLED:
            self.file_queue_store.mark_cancelled(event.item_id)
        self.root.after(0, lambda value=event: self._apply_file_generation_event(value))

    def _apply_file_generation_event(self, event: FileGenerationEvent) -> None:
        previous = self.source_file_items.get(event.item_id)
        try:
            current = self.file_queue_store.get(event.item_id)
        except KeyError:
            return
        self.source_file_items[event.item_id] = current
        status_changed = previous is None or previous.status != current.status
        if status_changed or not self.file_list.exists(event.item_id):
            self._refresh_source_file_list(select_ids=[event.item_id])
            return
        self.file_list.item(
            event.item_id,
            values=self._source_item_values(current),
            tags=(current.status.value,),
        )
        self._refresh_source_file_summary()

    def _log_file_results(self, outcomes: list[FileGenerationOutcome]) -> str:
        successful_results = []
        failed = 0
        for outcome in outcomes:
            if outcome.status == FileQueueStatus.DONE and outcome.result is not None:
                append_log(self.file_log, f"Hoàn tất: {outcome.source_path.name}")
                append_log(self.file_log, format_result(outcome.result))
                successful_results.append(outcome.result)
            else:
                failed += 1
                append_log(
                    self.file_log,
                    f"Lỗi: {outcome.source_path.name}: {outcome.error}",
                )
        self.file_output_dirs = _result_output_dirs(successful_results)
        self._set_open_button_state(self.file_open_folder_button, self.file_output_dirs)
        self._reload_source_file_queue()
        done = len(successful_results)
        return f"Hoàn tất: {done} thành công, {failed} lỗi."

    def copy_result_paths(self, scope: str, kind: str) -> None:
        paths = self._queue_result_paths(scope, kind)
        if not paths:
            self._show_no_result_paths(scope, kind)
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(_path_lines(paths))
        self.status_var.set(
            f"Đã copy {self._format_count(len(paths))} path {RESULT_PATH_KIND_LABELS.get(kind, '')}."
        )

    def export_result_paths(self, scope: str, kind: str) -> None:
        paths = self._queue_result_paths(scope, kind)
        if not paths:
            self._show_no_result_paths(scope, kind)
            return
        target = filedialog.asksaveasfilename(
            title="Export path TXT",
            defaultextension=".txt",
            filetypes=[("Text", "*.txt"), ("Tất cả", "*.*")],
            initialfile=self._default_result_path_export_name(scope, kind),
        )
        if not target:
            return
        try:
            Path(target).write_text(_path_lines(paths) + "\n", encoding="utf-8")
        except OSError as exc:
            messagebox.showerror("Export TXT", f"Không ghi được file TXT: {exc}")
            return
        self.status_var.set(
            f"Đã export {self._format_count(len(paths))} path: {target}"
        )

    def _queue_result_paths(self, scope: str, kind: str) -> tuple[Path, ...]:
        paths: list[Path] = []
        for item in self._queue_result_items(scope):
            manifest = item.output_manifest
            if manifest.is_empty() and item.output_paths:
                manifest = FileQueueOutputManifest.from_flat_paths(item.output_paths)
            paths.extend(manifest.paths_for(kind))
        return _unique_paths(paths)

    def _queue_result_items(self, scope: str) -> list[FileQueueItem]:
        if scope == "selected":
            item_ids = self._selected_source_item_ids()
            return [
                self.source_file_items[item_id]
                for item_id in item_ids
                if self.source_file_items[item_id].status == FileQueueStatus.DONE
            ]
        return [
            item
            for item in sorted(self.source_file_items.values(), key=lambda value: value.position)
            if item.status == FileQueueStatus.DONE
        ]

    def _show_no_result_paths(self, scope: str, kind: str) -> None:
        if scope == "selected" and not self._selected_source_item_ids():
            messagebox.showinfo("Path kết quả", "Hãy chọn ít nhất một queue kết quả.")
            return
        label = RESULT_PATH_KIND_LABELS.get(kind, "kết quả")
        messagebox.showinfo("Path kết quả", f"Không có path {label} phù hợp.")

    def _default_result_path_export_name(self, scope: str, kind: str) -> str:
        scope_slug = RESULT_PATH_SCOPE_SLUGS.get(scope, "queue")
        kind_slug = RESULT_PATH_KIND_SLUGS.get(kind, "paths")
        return f"colin-tts-{scope_slug}-{kind_slug}.txt"

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
        f5_line = ""
        if self.controller.model_supports_f5_settings(settings.model_id):
            seed = settings.f5_seed if settings.f5_seed is not None else "random"
            fix_duration = settings.f5_fix_duration if settings.f5_fix_duration is not None else "tự động"
            f5_line = (
                f"\nF5-TTS: NFE {settings.f5_nfe_step}; CFG {settings.f5_cfg_strength}; "
                f"Sway {settings.f5_sway_sampling_coef}; Cross-fade {settings.f5_cross_fade_duration}s; "
                f"RMS {settings.f5_target_rms}; Seed {seed}; Fix duration {fix_duration}; "
                f"Remove silence: {'Có' if settings.f5_remove_silence else 'Không'}"
            )
        chatterbox_line = ""
        if self.controller.model_supports_chatterbox_settings(settings.model_id):
            seed = settings.chatterbox_seed if settings.chatterbox_seed is not None else "random"
            chatterbox_line = (
                f"\nChatterbox Turbo: Temperature {settings.chatterbox_temperature}; "
                f"Top-P {settings.chatterbox_top_p}; Top-K {settings.chatterbox_top_k}; "
                f"Repetition penalty {settings.chatterbox_repetition_penalty}; Seed {seed}; "
                f"Normalize loudness: {'Có' if settings.chatterbox_norm_loudness else 'Không'}"
            )
        return (
            f"{source}\n"
            f"Model: {self.model_var.get()}; Ngôn ngữ: {self.language_var.get()}; "
            f"Profile: {self.voice_profile_var.get()}; Preset giọng: {self.speaker_var.get()}; "
            f"Codec: {self.codec_var.get()}; Thiết bị xử lý: {self.controller.runtime_target_label(settings.runtime_target)}\n"
            f"Temperature: {settings.temperature or 'mặc định'}; Top-K: {settings.top_k or 'mặc định'}; "
            f"Độ dài đoạn nhỏ: {settings.max_chunk_chars}; "
            f"Nghỉ giữa câu/chunk: {settings.sentence_pause_ms} ms; "
            f"Nghỉ giữa đoạn trong file tổng: {settings.paragraph_pause_ms} ms"
            f"{f5_line}{chatterbox_line}\n"
            f"Tách file: {'Có' if settings.split_output else 'Không'}; "
            f"Định dạng audio: {settings.output_audio_format.upper()}"
            f"{f' {settings.mp3_bitrate_kbps} kbps' if settings.output_audio_format == 'mp3' else ''}; "
            f"Xuất SRT: {'Có' if settings.output_srt else 'Không'}; "
            f"File audio tổng: {'Có' if settings.join_split_output_audio else 'Không'}; "
            f"Ghi đè: {'Có' if settings.overwrite else 'Không'}\n"
            f"Thư mục xuất: {output_dir}; Tên file xuất: {output_stem}"
        )

    def refresh_models(self) -> None:
        if self._model_refresh_running:
            return
        self._model_refresh_running = True
        current_model_id = self._current_model_id()
        self.status_var.set("Đang kiểm tra model/runtime...")

        def worker() -> None:
            try:
                rows = []
                for item in self.controller.all_models():
                    runtime = self.controller.service.runtime_status_for(item.model_id)
                    rows.append(
                        (
                            item.model_id,
                            (
                                item.display_name,
                                _short_text(item.usage, 86),
                                item.provider,
                                "Có" if item.required else "Không",
                                _model_status_label(item),
                                self.controller.runtime_device_label(runtime.actual_device),
                                _format_model_size(item),
                                str(item.storage_path or item.local_path),
                            ),
                        )
                    )
                runtime_text = self.controller.runtime_status_text(current_model_id)
                startup_notice = self.controller.startup_notice()
                setup_rows = [
                    (item.task_id, _setup_status_values(item))
                    for item in self.controller.setup_statuses(current_model_id)
                ]
            except Exception as exc:
                self.root.after(0, lambda err=exc: self._finish_model_refresh_error(err))
                return
            self.root.after(0, lambda: self._apply_model_refresh(rows, runtime_text, startup_notice, setup_rows))

        threading.Thread(target=worker, daemon=True).start()

    def _apply_model_refresh(self, rows, runtime_text: str, startup_notice: str, setup_rows) -> None:
        self._model_refresh_running = False
        for row in self.model_table.get_children():
            self.model_table.delete(row)
        for model_id, values in rows:
            self.model_table.insert(
                "",
                "end",
                iid=model_id,
                values=values,
            )
        self._apply_setup_rows(setup_rows)
        self.model_info_var.set(self.controller.model_choice_info(self._current_model_id()))
        self.runtime_var.set(runtime_text)
        self.refresh_license_status()
        self.status_var.set(startup_notice)
        self.apply_model_capabilities()

    def _finish_model_refresh_error(self, error: Exception) -> None:
        self._model_refresh_running = False
        self.status_var.set(f"Chưa kiểm tra được model/runtime: {error}")

    def refresh_selected_setup(self) -> None:
        model_id = self._selected_model_table_id() or self._current_model_id()

        def worker() -> None:
            try:
                setup_rows = [
                    (item.task_id, _setup_status_values(item))
                    for item in self.controller.setup_statuses(model_id)
                ]
            except Exception as exc:
                setup_rows = [
                    (
                        "setup:error",
                        (
                            "setup",
                            "Kiểm tra setup",
                            "Lỗi",
                            "",
                            str(exc),
                        ),
                    )
                ]
            self.root.after(0, lambda: self._apply_setup_rows(setup_rows))

        threading.Thread(target=worker, daemon=True).start()

    def _apply_setup_rows(self, rows) -> None:
        if not hasattr(self, "setup_table"):
            return
        for row in self.setup_table.get_children():
            self.setup_table.delete(row)
        for task_id, values in rows:
            self.setup_table.insert("", "end", iid=task_id, values=values)

    def _selected_model_table_id(self) -> str | None:
        selected = self.model_table.selection()
        return selected[0] if selected else None

    def _prepare_initial_model_view(self) -> None:
        model_id = self._current_model_id()
        self.model_info_var.set(self.controller.model_choice_info(model_id))
        self.runtime_var.set("Đang kiểm tra runtime/model sau khi giao diện mở...")
        self.status_var.set("Đang mở giao diện; trạng thái model sẽ cập nhật sau vài giây.")
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
        self.refresh_selected_setup()

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

        supports_f5 = self.controller.model_supports_f5_settings(model_id)
        _set_widgets_state(self.f5_controls, supports_f5)
        if supports_f5 and prefer_default_preset:
            self._apply_f5_defaults(model_id)

        supports_chatterbox = self.controller.model_supports_chatterbox_settings(model_id)
        _set_widgets_state(self.chatterbox_controls, supports_chatterbox)
        if supports_chatterbox and prefer_default_preset:
            self._apply_chatterbox_defaults(model_id)

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

    def _apply_f5_defaults(self, model_id: str) -> None:
        defaults = self.controller.default_f5_settings(model_id)
        self.f5_nfe_step_var.set(int(defaults["f5_nfe_step"]))
        self.f5_cfg_strength_var.set(float(defaults["f5_cfg_strength"]))
        self.f5_sway_sampling_coef_var.set(float(defaults["f5_sway_sampling_coef"]))
        self.f5_cross_fade_duration_var.set(float(defaults["f5_cross_fade_duration"]))
        self.f5_target_rms_var.set(float(defaults["f5_target_rms"]))
        self.f5_remove_silence_var.set(bool(defaults["f5_remove_silence"]))
        self.f5_seed_var.set("")
        self.f5_fix_duration_var.set(0.0)

    def _apply_chatterbox_defaults(self, model_id: str) -> None:
        defaults = self.controller.default_chatterbox_settings(model_id)
        self.chatterbox_temperature_var.set(float(defaults["chatterbox_temperature"]))
        self.chatterbox_top_p_var.set(float(defaults["chatterbox_top_p"]))
        self.chatterbox_top_k_var.set(int(defaults["chatterbox_top_k"]))
        self.chatterbox_repetition_penalty_var.set(float(defaults["chatterbox_repetition_penalty"]))
        self.chatterbox_seed_var.set("")
        self.chatterbox_norm_loudness_var.set(bool(defaults["chatterbox_norm_loudness"]))

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

    def remove_selected_model(self) -> None:
        selected = self.model_table.selection()
        if not selected:
            messagebox.showinfo("Thông báo", "Hãy chọn một model trong bảng.")
            return
        model_id = selected[0]
        preview = self.controller.model_removal_preview(model_id)
        if not messagebox.askyesno("Xác nhận gỡ model", f"{preview}\n\nBạn có muốn tiếp tục?"):
            return
        self._run_background(
            "Đang gỡ model...",
            lambda _progress, _cancel: self.controller.remove_model(model_id),
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

    def install_base_for_selected_model(self) -> None:
        selected = self.model_table.selection()
        if not selected:
            messagebox.showinfo("Thông báo", "Hãy chọn một model trong bảng.")
            return
        self._run_background(
            "Đang cài worker/môi trường...",
            lambda _progress, _cancel: self.controller.install_base_for_model(selected[0]),
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
        completion_message = on_success(result)
        self.progress_var.set(100.0)
        self.status_var.set(
            completion_message if isinstance(completion_message, str) else "Hoàn tất."
        )
        if self.active_log_widget is not None:
            append_log(self.active_log_widget, "Hoàn tất tác vụ.")
        self._set_busy(False)

    def _finish_cancelled(self) -> None:
        self._reload_source_file_queue()
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


def _optional_text(value) -> str:
    if value is None:
        return ""
    return str(value)


def _optional_int(value) -> int | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return int(text)
    except ValueError:
        return None


def _optional_positive_float(value) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _label_for_value(mapping: dict[str, str | None], value: str | None) -> str | None:
    if value is None:
        return None
    for label, item_value in mapping.items():
        if item_value == value:
            return label
    return None


def _model_status_label(item) -> str:
    if item.worker_installed is False:
        return "Chưa cài worker"
    if item.hf_cached is False:
        return "Thiếu HF cache"
    if item.installed:
        return "Sẵn sàng" if item.worker_installed is not True else "Worker + model OK"
    if item.worker_installed is True:
        return "Worker OK, thiếu model"
    return "Chưa tải"


def _format_model_size(item) -> str:
    total = item.total_size_mb if item.total_size_mb else item.size_mb
    if total >= 1024:
        return f"{total / 1024:.2f} GB"
    return f"{total:.0f} MB"


def _setup_status_values(item) -> tuple[str, str, str, str, str]:
    action = item.action_label if item.can_run else ""
    if item.script_name and action:
        action = f"{action} ({item.script_name})"
    return (
        _setup_scope_label(item.scope),
        item.label,
        _setup_status_label(item.status),
        action,
        _short_text(item.detail, 150),
    )


def _setup_scope_label(value: str) -> str:
    return {
        "environment": "Máy",
        "storage": "Storage",
        "model": "Model",
        "runtime": "Runtime",
        "worker": "Worker",
        "gpu": "GPU",
    }.get(value, value)


def _setup_status_label(value: str) -> str:
    return {
        "ok": "OK",
        "missing": "Thiếu",
        "warning": "Cảnh báo",
        "optional": "Tùy chọn",
        "error": "Lỗi",
    }.get(value, value)


def _short_text(value: str, limit: int) -> str:
    text = " ".join((value or "").split())
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"


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


def _result_output_paths(result) -> list[Path]:
    paths: list[Path] = []
    for path in (
        list(result.item_audio_paths)
        + list(result.item_srt_paths)
        + [result.audio_path, result.srt_path]
    ):
        if path is not None and path not in paths:
            paths.append(path)
    return paths


def _result_output_manifest(result) -> FileQueueOutputManifest:
    split_audio_paths = _unique_paths(result.item_audio_paths)
    audio_path = Path(result.audio_path) if result.audio_path else None
    merged_audio_path = (
        audio_path
        if audio_path is not None and audio_path not in split_audio_paths
        else None
    )
    srt_paths = _unique_paths([*result.item_srt_paths, result.srt_path])
    return FileQueueOutputManifest(
        split_output_dirs=_unique_paths(path.parent for path in split_audio_paths),
        split_audio_paths=split_audio_paths,
        merged_audio_path=merged_audio_path,
        srt_paths=srt_paths,
        job_dir=result.job_dir,
    )


def _unique_paths(paths) -> tuple[Path, ...]:
    unique: list[Path] = []
    seen: set[str] = set()
    for value in paths:
        if value is None:
            continue
        path = Path(value)
        key = str(path).casefold()
        if key in seen:
            continue
        seen.add(key)
        unique.append(path)
    return tuple(unique)


def _path_lines(paths: tuple[Path, ...]) -> str:
    return "\n".join(str(path) for path in paths)


def _short_display(value: str, limit: int) -> str:
    text = " ".join(str(value or "").split())
    return text if len(text) <= limit else f"{text[: limit - 1]}…"
