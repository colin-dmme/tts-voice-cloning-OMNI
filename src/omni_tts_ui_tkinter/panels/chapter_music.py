"""Private local chapter-music choices for Tkinter."""

import secrets
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from omni_tts_core.chapter_music import (
    ChapterMusicLibrary,
    ChapterMusicSelector,
    music_duration_note,
    preview_chapter_music,
)
from omni_tts_core.media_player import MediaPlayerService
from omni_tts_core.music_presets import MusicPresetStore
from omni_tts_shared.epub import ChapterMusicOptions, MusicPoolSelection
from omni_tts_shared.errors import ConfigError, OmniTtsError


class ChapterMusicFrame(ttk.LabelFrame):
    def __init__(
        self, parent, options, *, preview_duration=lambda: 2500, source_only=False
    ):
        super().__init__(
            parent,
            text="Nguồn nhạc cho các nhịp nghỉ"
            if source_only
            else "Nhạc đệm trong khoảng nghỉ",
            padding=8,
        )
        self.source_only = source_only
        self.available = True
        self.library = ChapterMusicLibrary()
        self.preview_duration = preview_duration
        self._fades = (options.fade_in_ms, options.fade_out_ms)
        self.enabled = tk.BooleanVar(value=options.enabled)
        self.volume = tk.IntVar(value=options.volume_percent)
        self.between = tk.BooleanVar(value=options.between_chapters)
        self.after_title = tk.BooleanVar(value=options.after_title)
        self.track = tk.StringVar()
        self.mode_labels = {
            "fixed": "Chọn một bản cố định",
            "random_theme": "Random trong nhóm chủ đề",
            "random_selection": "Random trong tập đã tích",
            "preset": "Random theo preset đã lưu",
        }
        self.mode = tk.StringVar(value=self.mode_labels[options.selection_mode])
        self._pool = MusicPoolSelection(
            **{key: getattr(options, key) for key in MusicPoolSelection.model_fields}
        )
        self._saved_preset = options.preset_id
        self.seed = tk.IntVar(value=options.random_seed)
        self._overrides = dict(options.track_overrides)
        self._saved_theme = options.theme
        self._saved_track = options.track_id
        self.duration_mode = tk.StringVar(
            value="Phát trọn bản nhạc trong thư viện"
            if options.duration_mode == "full_track"
            else "Cắt vừa khoảng nghỉ"
        )
        self.columnconfigure(0, weight=1)
        ttk.Checkbutton(
            self, text="Bật nhạc chuyển chương", variable=self.enabled
        ).grid(row=0, column=0, columnspan=2, sticky="w")
        self.combo = ttk.Combobox(
            self, textvariable=self.track, state="readonly", width=32
        )
        self.combo.grid(row=1, column=0, columnspan=2, sticky="ew", pady=6)
        self.combo.bind("<<ComboboxSelected>>", self._note)
        ttk.Label(self, text="Âm lượng nhạc (%)").grid(row=2, column=0, sticky="w")
        self.volume_spin = ttk.Spinbox(
            self, from_=0, to=100, textvariable=self.volume, width=8
        )
        self.volume_spin.grid(row=2, column=1)
        ttk.Checkbutton(self, text="Phát giữa hai chương", variable=self.between).grid(
            row=3, column=0, columnspan=2, sticky="w"
        )
        ttk.Checkbutton(
            self, text="Phát sau tên chương, trước nội dung", variable=self.after_title
        ).grid(row=4, column=0, columnspan=2, sticky="w")
        ttk.Button(self, text="Nghe thử nhạc", command=self._preview).grid(
            row=5, column=0, sticky="w", pady=6
        )
        ttk.Button(self, text="Thêm nhạc…", command=self._import).grid(row=5, column=1)
        self.note = ttk.Label(self, wraplength=390)
        self.mode_combo = ttk.Combobox(
            self,
            textvariable=self.mode,
            state="readonly",
            values=list(self.mode_labels.values()),
        )
        self.mode_combo.grid(row=6, column=0, columnspan=2, sticky="ew", pady=4)
        self.mode_combo.bind("<<ComboboxSelected>>", self._note)
        self.theme_combo = ttk.Combobox(self, state="readonly")
        self.theme_combo.grid(row=7, column=0, columnspan=2, sticky="ew")
        self.theme_combo.bind("<<ComboboxSelected>>", self._note)
        self.seed_spin = ttk.Spinbox(
            self, from_=0, to=2147483647, textvariable=self.seed, width=12
        )
        self.seed_spin.grid(row=8, column=0, sticky="w", pady=4)
        self.shuffle_button = ttk.Button(
            self,
            text="Đổi lượt trộn",
            command=lambda: self.seed.set(secrets.randbelow(2147483647)),
        )
        self.shuffle_button.grid(row=8, column=1)
        ttk.Label(self, text="Độ dài nhạc").grid(row=9, column=0, sticky="w", pady=4)
        self.duration_combo = ttk.Combobox(
            self,
            textvariable=self.duration_mode,
            state="readonly",
            values=["Cắt vừa khoảng nghỉ", "Phát trọn bản nhạc trong thư viện"],
        )
        self.duration_combo.grid(row=10, column=0, columnspan=2, sticky="ew", pady=4)
        self.duration_combo.bind("<<ComboboxSelected>>", self._note)
        self.note.grid(row=11, column=0, columnspan=2, sticky="w")
        self.preset_combo = ttk.Combobox(self, state="readonly")
        self.preset_combo.grid(row=12, column=0, columnspan=2, sticky="ew", pady=4)
        self.preset_combo.bind("<<ComboboxSelected>>", self._note)
        self.pool_button = ttk.Button(
            self, text="Chọn nhiều nhóm / bài nhạc…", command=self._edit_pool
        )
        self.pool_button.grid(row=13, column=0, columnspan=2, sticky="w", pady=4)
        if source_only:
            for child in self.grid_slaves():
                info = child.grid_info()
                if int(info["row"]) in (0, 3, 4, 9, 10) or (
                    int(info["row"]) == 5 and int(info["column"]) == 0
                ):
                    child.grid_remove()
        self.refresh(options.track_id)

    def set_available(self, available):
        self.available = available
        for child in self.winfo_children():
            if isinstance(child, ttk.Button):
                child.configure(state="normal" if available else "disabled")
        self.mode_combo.configure(state="readonly" if available else "disabled")
        self.volume_spin.configure(state="normal" if available else "disabled")
        self._note()

    def refresh(self, selected=None):
        self.tracks = self.library.list_tracks()
        preset = self._preset_id() if hasattr(self, "presets") else self._saved_preset
        self.presets = [(None, "Chọn preset nhạc…")] + [
            (p.preset_id, p.name) for p in MusicPresetStore(self.library).list_presets()
        ]
        if preset and not any(p[0] == preset for p in self.presets):
            self.presets.append((preset, "Preset đã lưu không còn"))
        self.preset_combo["values"] = [p[1] for p in self.presets]
        self.preset_combo.current(
            next((i for i, p in enumerate(self.presets) if p[0] == preset), 0)
        )
        old_theme = self._theme() if hasattr(self, "groups") else self._saved_theme
        self.groups = [
            {"theme": None, "name": "Chọn nhóm chủ đề…", "count": 0}
        ] + self.library.list_themes()
        if old_theme and not any(g["theme"] == old_theme for g in self.groups):
            self.groups.append(
                {"theme": old_theme, "name": old_theme + " (chưa có nhạc)", "count": 0}
            )
        self.theme_combo["values"] = [
            g["name"] + (f" ({g['count']} bản)" if g["count"] else "")
            for g in self.groups
        ]
        self.theme_combo.current(
            next((i for i, g in enumerate(self.groups) if g["theme"] == old_theme), 0)
        )
        self.combo["values"] = [t.name for t in self.tracks]
        chosen = next(
            (i for i, t in enumerate(self.tracks) if t.track_id == selected),
            -1 if selected else 0,
        )
        if self.tracks:
            if chosen >= 0:
                self.combo.current(chosen)
            else:
                self.combo.set("Nhạc đã lưu không còn — hãy chọn lại")
        self._note()

    def _selected(self):
        index = self.combo.current()
        return self.tracks[index] if 0 <= index < len(self.tracks) else None

    def _theme(self):
        index = self.theme_combo.current()
        return self.groups[index]["theme"] if 0 <= index < len(self.groups) else None

    def _preset_id(self):
        index = self.preset_combo.current()
        return self.presets[index][0] if 0 <= index < len(self.presets) else None

    def _selection_mode(self):
        return next(
            key for key, label in self.mode_labels.items() if label == self.mode.get()
        )

    def _note(self, *_):
        item = self._selected()
        if _ and getattr(_[0], "widget", None) is self.combo and item:
            self._saved_track = item.track_id
        mode = self._selection_mode()
        random_mode = mode != "fixed"
        self.combo.configure(
            state="readonly" if self.available and mode == "fixed" else "disabled"
        )
        self.theme_combo.configure(
            state="readonly"
            if self.available and mode == "random_theme"
            else "disabled"
        )
        self.seed_spin.configure(
            state="normal" if self.available and random_mode else "disabled"
        )
        self.shuffle_button.configure(
            state="normal" if self.available and random_mode else "disabled"
        )
        self.preset_combo.configure(
            state="readonly" if self.available and mode == "preset" else "disabled"
        )
        self.pool_button.configure(
            state="normal"
            if self.available and mode == "random_selection"
            else "disabled"
        )
        text = (
            "Chọn bài/nhóm dùng chung. Loại nghỉ, thời lượng và fade chỉnh theo từng vị trí."
            if self.source_only
            else music_duration_note(
                "full_track"
                if self.duration_mode.get() == "Phát trọn bản nhạc trong thư viện"
                else "fit_pause"
            )
        )
        if random_mode:
            text += " Trộn hết nhóm trước khi lặp. Cùng lượt trộn giữ lựa chọn khi tiếp tục tác vụ."
            if mode in ("random_selection", "preset"):
                try:
                    text += f" {len(ChapterMusicSelector(self.options(), self.library).pool)} bản được chọn."
                except ConfigError as exc:
                    text += " " + str(exc)
        elif item:
            text += f"\n{item.description or 'Chưa có mô tả.'}\nChủ đề: {', '.join(item.themes)}. Tag: {', '.join(item.tags)}."
        if item and item.provenance.get("generated_plan") == "free":
            text += " Mẫu ElevenLabs Free: dùng cá nhân; chưa có quyền thương mại."
        self.note.configure(text=text)

    def options(self):
        item = self._selected()
        random_mode = self._selection_mode() != "fixed"
        track_id = (
            self._saved_track
            if random_mode
            else (
                item.track_id
                if item
                and (
                    self.enabled.get()
                    or self._saved_track
                    or (self.source_only and self.available)
                )
                else None
            )
        )
        return ChapterMusicOptions(
            enabled=self.enabled.get(),
            track_id=track_id,
            duration_mode="full_track"
            if self.duration_mode.get() == "Phát trọn bản nhạc trong thư viện"
            else "fit_pause",
            selection_mode=self._selection_mode(),
            preset_id=self._preset_id(),
            **self._pool.model_dump(),
            theme=self._theme(),
            random_seed=self.seed.get(),
            track_overrides=self._overrides,
            volume_percent=self.volume.get(),
            between_chapters=self.between.get(),
            after_title=self.after_title.get(),
            fade_in_ms=self._fades[0],
            fade_out_ms=self._fades[1],
        )

    def _edit_pool(self):
        win = tk.Toplevel(self)
        win.title("Phối nhiều nhóm và bài nhạc")
        win.transient(self.winfo_toplevel())
        lists = []
        data = [
            (
                "Nhóm chủ đề",
                [(g["theme"], g["name"]) for g in self.library.list_themes()],
                set(self._pool.theme_ids),
            ),
            (
                "Bài thêm riêng",
                [(t.track_id, t.name) for t in self.tracks],
                set(self._pool.track_ids),
            ),
            (
                "Bài loại khỏi random",
                [(t.track_id, t.name) for t in self.tracks],
                set(self._pool.excluded_track_ids),
            ),
        ]
        for column, (caption, items, selected) in enumerate(data):
            ttk.Label(win, text=caption).grid(row=0, column=column, padx=8, pady=6)
            box = tk.Listbox(
                win, selectmode="multiple", exportselection=False, width=33, height=18
            )
            for i, (item_id, name) in enumerate(items):
                box.insert("end", name)
                if item_id in selected:
                    box.selection_set(i)
            box.grid(row=1, column=column, padx=8, sticky="nsew")
            win.columnconfigure(column, weight=1)
            lists.append((box, items))

        def accept():
            values = [[items[i][0] for i in box.curselection()] for box, items in lists]
            pool = MusicPoolSelection(
                theme_ids=values[0], track_ids=values[1], excluded_track_ids=values[2]
            )
            try:
                self.library.selection_tracks(pool)
            except ConfigError as exc:
                messagebox.showwarning("Chưa có tập nhạc hợp lệ", str(exc), parent=win)
                return
            self._pool = pool
            self._note()
            win.destroy()

        ttk.Button(win, text="Dùng tập đã chọn", command=accept).grid(
            row=2, column=0, columnspan=3, pady=10
        )

    def _preview(self):
        try:
            options = self.options()
            selected = ChapterMusicSelector(
                options, self.library, context=secrets.token_hex(8)
            ).choose("preview")
            path = preview_chapter_music(
                selected.track_id,
                duration_ms=self.preview_duration(),
                volume_percent=options.volume_percent,
                fade_in_ms=options.fade_in_ms,
                fade_out_ms=options.fade_out_ms,
                duration_mode=options.duration_mode,
            )
            MediaPlayerService().play_first_available([path])
        except (OmniTtsError, ValueError, OSError, tk.TclError) as exc:
            messagebox.showwarning("Chưa nghe được nhạc", str(exc), parent=self)

    def _import(self):
        filename = filedialog.askopenfilename(
            title="Thêm nhạc (lấy tối đa 30 giây)",
            filetypes=[("Audio", "*.wav *.mp3 *.flac *.ogg *.m4a")],
            parent=self,
        )
        if not filename:
            return
        try:
            track = self.library.import_track(
                Path(filename),
                Path(filename).stem,
                provenance={"provider": "user_import"},
            )
            self.refresh(track.track_id)
            self._saved_track = track.track_id
            self.mode.set("Chọn một bản cố định")
            self._note()
        except (OmniTtsError, ValueError, OSError) as exc:
            messagebox.showerror("Không thêm được nhạc", str(exc), parent=self)
