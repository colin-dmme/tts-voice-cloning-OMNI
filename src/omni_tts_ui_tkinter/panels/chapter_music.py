"""Private local chapter-music choices for Tkinter."""

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from omni_tts_core.chapter_music import ChapterMusicLibrary, preview_chapter_music
from omni_tts_core.media_player import MediaPlayerService
from omni_tts_shared.epub import ChapterMusicOptions
from omni_tts_shared.errors import OmniTtsError


class ChapterMusicFrame(ttk.LabelFrame):
    def __init__(self, parent, options, *, preview_duration=lambda: 2500):
        super().__init__(parent, text="Nhạc đệm trong khoảng nghỉ", padding=8)
        self.library = ChapterMusicLibrary()
        self.preview_duration = preview_duration
        self._fades = (options.fade_in_ms, options.fade_out_ms)
        self.enabled = tk.BooleanVar(value=options.enabled)
        self.volume = tk.IntVar(value=options.volume_percent)
        self.between = tk.BooleanVar(value=options.between_chapters)
        self.after_title = tk.BooleanVar(value=options.after_title)
        self.track = tk.StringVar()
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
        ttk.Spinbox(self, from_=0, to=100, textvariable=self.volume, width=8).grid(
            row=2, column=1
        )
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
        self.note.grid(row=6, column=0, columnspan=2, sticky="w")
        self.refresh(options.track_id)

    def refresh(self, selected=None):
        self.tracks = self.library.list_tracks()
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

    def _note(self, *_):
        item = self._selected()
        text = "Tự cắt và fade vừa nhịp nghỉ; SRT giữ nguyên timeline."
        if item and item.provenance.get("generated_plan") == "free":
            text += " Mẫu ElevenLabs Free: dùng cá nhân; chưa có quyền thương mại."
        self.note.configure(text=text)

    def options(self):
        item = self._selected()
        return ChapterMusicOptions(
            enabled=self.enabled.get(),
            track_id=item.track_id if item else None,
            volume_percent=self.volume.get(),
            between_chapters=self.between.get(),
            after_title=self.after_title.get(),
            fade_in_ms=self._fades[0],
            fade_out_ms=self._fades[1],
        )

    def _preview(self):
        try:
            options = self.options()
            path = preview_chapter_music(
                options.track_id,
                duration_ms=self.preview_duration(),
                volume_percent=options.volume_percent,
                fade_in_ms=options.fade_in_ms,
                fade_out_ms=options.fade_out_ms,
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
        except (OmniTtsError, ValueError, OSError) as exc:
            messagebox.showerror("Không thêm được nhạc", str(exc), parent=self)
