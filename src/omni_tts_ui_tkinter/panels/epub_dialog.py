"""EPUB import and pause controls for the default desktop launcher."""

import secrets
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from omni_tts_core.text.epub_content import (
    export_reading_plan,
    format_han_issues,
    format_reading_changes,
    prepare_epub,
    reading_summary,
)
from omni_tts_core.text.epub_reader import read_epub
from omni_tts_shared.epub import EPUB_PAUSE_FIELDS, EpubOptions
from omni_tts_shared.errors import ConfigError
from omni_tts_ui_tkinter.panels.chapter_music import ChapterMusicFrame
from omni_tts_ui_tkinter.panels.epub_break import EpubBreakFrame
from omni_tts_ui_tkinter.panels.epub_content import EpubContentFrame


def import_epub(app):
    if not app._can_edit_file_queue():
        return
    filename = filedialog.askopenfilename(
        title="Nhập sách EPUB", filetypes=[("EPUB", "*.epub")]
    )
    if not filename:
        return
    try:
        book = read_epub(Path(filename))
        options = EpubOptions.model_validate(
            getattr(app, "_epub_options", app.preference_data.get("epub_options", {}))
        )
    except (ValueError, ConfigError) as exc:
        messagebox.showerror("Không nhập được EPUB", str(exc))
        return
    win = tk.Toplevel(app.root)
    win.title("Nhập EPUB — chọn chương và nhịp nghỉ")
    win.geometry("1000x720")
    win.transient(app.root)
    win.grab_set()
    win.columnconfigure(0, weight=1)
    win.columnconfigure(1, weight=1)
    win.rowconfigure(2, weight=1)
    ttk.Label(
        win,
        text=f"{book.title}\n{len(book.chapters)} chương; bỏ bìa và mục lục. Chưa tạo giọng.",
        wraplength=940,
    ).grid(row=0, column=0, columnspan=2, sticky="w", padx=12, pady=12)
    chapters = tk.Listbox(win, exportselection=False, height=10)
    for chapter in book.chapters:
        chapters.insert("end", f"{chapter.index}. {chapter.title}")
    chapters.grid(row=1, column=0, sticky="nsew", padx=12)
    notebook = ttk.Notebook(win)
    notebook.grid(row=2, column=0, sticky="nsew", padx=12, pady=8)
    views = []
    for title in ("Văn bản sẽ đọc", "Bản gốc", "Đã bỏ / đã đổi", "Chữ Hán còn lại"):
        view = tk.Text(notebook, wrap="word", height=16)
        notebook.add(view, text=title)
        views.append(view)
    content_status = tk.StringVar()

    def show_chapter(_event=None):
        if chapters.curselection():
            chapter = book.chapters[chapters.curselection()[0]]
            try:
                plan = prepare_epub(
                    book,
                    EpubOptions(
                        chapter_start=start.get(),
                        chapter_end=end.get(),
                        content=content.options(),
                    ),
                )
                data = plan.chapter_preview(chapter.index, max_chars=500000)
                content_status.set(
                    reading_summary(plan.summary) + "\n" + "\n".join(plan.warnings)
                )
                texts = (
                    data["reading_text"]
                    or "Phần này không nằm trong bản đọc theo phạm vi / bộ lọc.",
                    data["original_text"],
                    format_reading_changes(data),
                    format_han_issues(plan),
                )
                for view, text in zip(views, texts):
                    view.configure(state="normal")
                    view.delete("1.0", "end")
                    view.insert("1.0", text)
                    view.configure(state="disabled")
            except (ValueError, ConfigError, tk.TclError) as exc:
                content_status.set(str(exc))

    chapters.bind("<<ListboxSelect>>", show_chapter)
    chapters.selection_set(0)
    right = ttk.Frame(win)
    right.grid(row=1, column=1, rowspan=2, sticky="nsew")
    canvas = tk.Canvas(right, highlightthickness=0)
    bar = ttk.Scrollbar(right, orient="vertical", command=canvas.yview)
    canvas.configure(yscrollcommand=bar.set)
    bar.pack(side="right", fill="y")
    canvas.pack(side="left", fill="both", expand=True)
    panel = ttk.Frame(canvas, padding=12)
    window_id = canvas.create_window((0, 0), window=panel, anchor="nw")
    panel.bind(
        "<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all"))
    )
    canvas.bind(
        "<Configure>", lambda event: canvas.itemconfigure(window_id, width=event.width)
    )
    start, end = (
        tk.IntVar(value=options.chapter_start),
        tk.IntVar(value=options.chapter_end),
    )
    titles, volumes = (
        tk.BooleanVar(value=options.read_titles),
        tk.BooleanVar(value=options.include_volumes),
    )
    output = tk.StringVar(
        value="Mỗi chương một file"
        if options.output_mode == "chapters"
        else "Ghép một file"
    )
    for row, label, var in [
        (0, "Từ chương (vị trí)", start),
        (1, "Đến chương (0 = hết sách)", end),
    ]:
        ttk.Label(panel, text=label).grid(row=row, column=0, sticky="w", pady=6)
        ttk.Spinbox(
            panel,
            from_=0 if row else 1,
            to=len(book.chapters),
            textvariable=var,
            width=12,
        ).grid(row=row, column=1)
    ttk.Checkbutton(panel, text="Đọc tên chương", variable=titles).grid(
        row=2, column=0, columnspan=2, sticky="w", pady=6
    )
    ttk.Checkbutton(panel, text="Đọc tên quyển", variable=volumes).grid(
        row=3, column=0, columnspan=2, sticky="w", pady=6
    )
    ttk.Label(panel, text="Cách xuất EPUB").grid(row=4, column=0, sticky="w")
    ttk.Combobox(
        panel,
        values=["Mỗi chương một file", "Ghép một file"],
        textvariable=output,
        state="readonly",
        width=22,
    ).grid(row=4, column=1)
    pause_vars = {}
    for row, (key, label, _default) in enumerate(EPUB_PAUSE_FIELDS[2:], 5):
        var = tk.DoubleVar(value=getattr(options, key) / 1000)
        pause_vars[key] = var
        ttk.Label(panel, text=label + " (giây)").grid(
            row=row, column=0, sticky="w", pady=8
        )
        spin = ttk.Spinbox(
            panel, from_=0, to=10, increment=0.1, textvariable=var, width=12
        )
        spin.grid(row=row, column=1)
        if key == "volume_pause_ms":
            volume_spin = spin
    breaks = {}
    for row, kind, title, key in [
        (7, "title", "Sau tên chương, trước nội dung", "title_pause_ms"),
        (8, "chapter", "Giữa hai chương", "chapter_pause_ms"),
    ]:
        boundary = EpubBreakFrame(panel, title, options.break_for(kind))
        boundary.grid(row=row, column=0, columnspan=2, sticky="ew", pady=8)
        breaks[kind] = boundary
        pause_vars[key] = boundary.seconds
    music = ChapterMusicFrame(panel, options.music, source_only=True)
    content = EpubContentFrame(
        panel, options.content.model_dump(), on_change=show_chapter
    )
    content.grid(row=9, column=0, columnspan=2, sticky="ew", pady=8)
    music.grid(row=10, column=0, columnspan=2, sticky="ew", pady=8)

    def sync_controls(*_):
        breaks["title"].set_available(titles.get())
        volume_spin.configure(state="normal" if volumes.get() else "disabled")
        active = any(
            b.kind.get() == "Nhạc"
            and (b.duration_mode.get() == "Phát trọn bản nhạc" or b.seconds.get() > 0)
            for kind, b in breaks.items()
            if kind != "title" or titles.get()
        )
        music.set_available(active)

    for boundary in breaks.values():
        boundary.on_change = sync_controls

    def preview_boundary(kind):
        from omni_tts_core.chapter_music import (
            ChapterMusicSelector,
            preview_chapter_music,
        )
        from omni_tts_core.media_player import MediaPlayerService

        try:
            selected = EpubOptions(
                read_titles=titles.get(),
                music=music.options(),
                breaks={k: b.options() for k, b in breaks.items()},
            )
            settings = selected.music_for(kind)
            if not settings.enabled:
                return
            track = ChapterMusicSelector(settings, context=secrets.token_hex(8)).choose(
                "preview"
            )
            path = preview_chapter_music(
                track.track_id,
                duration_ms=selected.break_for(kind).trigger_ms,
                volume_percent=settings.volume_percent,
                duration_mode=settings.duration_mode,
                fade_in_ms=settings.fade_in_ms,
                fade_out_ms=settings.fade_out_ms,
            )
            MediaPlayerService().play_first_available([path])
        except (ValueError, ConfigError, OSError, tk.TclError) as exc:
            messagebox.showwarning("Chưa nghe được nhịp nghỉ", str(exc), parent=win)

    for kind, boundary in breaks.items():
        boundary.on_preview = lambda kind=kind: preview_boundary(kind)
    titles.trace_add("write", sync_controls)
    volumes.trace_add("write", sync_controls)
    sync_controls()
    srt_var = tk.BooleanVar(value=app.output_srt_var.get())
    ttk.Checkbutton(
        panel, text="Xuất kèm phụ đề .srt khớp audio", variable=srt_var
    ).grid(row=11, column=0, columnspan=2, sticky="w", pady=8)
    ttk.Label(
        panel,
        text="Nghỉ đoạn văn theo cài đặt hiện tại.\nAudio và SRT cùng tính các khoảng lặng.",
        wraplength=390,
    ).grid(row=12, column=0, columnspan=2, sticky="w", pady=15)
    ttk.Label(panel, textvariable=content_status, wraplength=390).grid(
        row=13, column=0, columnspan=2, sticky="w"
    )
    if book.warnings:
        ttk.Label(
            panel, text="Lưu ý: " + "\n".join(book.warnings[:3]), wraplength=390
        ).grid(row=14, column=0, columnspan=2)
    start.trace_add("write", show_chapter)
    end.trace_add("write", show_chapter)
    show_chapter()

    def accept():
        try:
            selected = EpubOptions(
                chapter_start=start.get(),
                chapter_end=end.get(),
                read_titles=titles.get(),
                content=content.options(),
                music=music.options(),
                breaks={kind: boundary.options() for kind, boundary in breaks.items()},
                include_volumes=volumes.get(),
                output_mode="chapters"
                if output.get() == "Mỗi chương một file"
                else "merged",
                **{k: round(v.get() * 1000) for k, v in pause_vars.items()},
            )
            if not prepare_epub(book, selected).chapters:
                raise ConfigError(
                    "Không còn nội dung sau khi lọc; hãy đổi phạm vi / tùy chọn."
                )
        except (ValueError, ConfigError, tk.TclError) as exc:
            messagebox.showwarning("Thiết lập chưa hợp lệ", str(exc), parent=win)
            return
        app._epub_options = selected.model_dump()
        app.output_srt_var.set(srt_var.get())
        app.save_preferences()
        app._start_source_file_import([Path(filename)])
        win.destroy()

    ttk.Button(win, text="Thêm vào hàng đợi", command=accept).grid(
        row=3, column=1, sticky="e", padx=12, pady=12
    )

    def export():
        directory = filedialog.askdirectory(parent=win, title="Lưu bản đọc và nguồn")
        if not directory:
            return
        try:
            plan = prepare_epub(
                book,
                EpubOptions(
                    chapter_start=start.get(),
                    chapter_end=end.get(),
                    content=content.options(),
                ),
            )
            paths = export_reading_plan(plan, Path(directory), Path(filename).stem)
        except (ValueError, ConfigError, OSError, tk.TclError) as exc:
            messagebox.showwarning("Chưa xuất được", str(exc), parent=win)
            return
        messagebox.showinfo(
            "Đã xuất bản đọc", "\n".join(str(p) for p in paths.values()), parent=win
        )

    ttk.Button(win, text="Xuất bản đọc và nguồn…", command=export).grid(
        row=3, column=0, sticky="w", padx=12, pady=12
    )
