"""EPUB import and pause controls for the default desktop launcher."""

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from omni_tts_core.text.epub_reader import read_epub
from omni_tts_shared.epub import EPUB_PAUSE_FIELDS, EpubOptions
from omni_tts_shared.errors import ConfigError
from omni_tts_ui_tkinter.panels.chapter_music import ChapterMusicFrame


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
    preview = tk.Text(win, wrap="word", height=16)
    preview.grid(row=2, column=0, sticky="nsew", padx=12, pady=8)

    def show_chapter(_event=None):
        if chapters.curselection():
            chapter = book.chapters[chapters.curselection()[0]]
            preview.configure(state="normal")
            preview.delete("1.0", "end")
            preview.insert(
                "1.0",
                chapter.title
                + "\n\n"
                + "\n\n".join(
                    "[Nghỉ chuyển cảnh]" if b.role == "scene" else b.text
                    for b in chapter.blocks
                ),
            )
            preview.configure(state="disabled")

    chapters.bind("<<ListboxSelect>>", show_chapter)
    chapters.selection_set(0)
    show_chapter()
    right = ttk.Frame(win)
    right.grid(row=1, column=1, rowspan=2, sticky="nsew")
    canvas = tk.Canvas(right, highlightthickness=0)
    bar = ttk.Scrollbar(right, orient="vertical", command=canvas.yview)
    canvas.configure(yscrollcommand=bar.set)
    bar.pack(side="right", fill="y")
    canvas.pack(side="left", fill="both", expand=True)
    panel = ttk.Frame(canvas, padding=12)
    window_id = canvas.create_window((0, 0), window=panel, anchor="nw")
    panel.bind("<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
    canvas.bind("<Configure>", lambda event: canvas.itemconfigure(window_id, width=event.width))
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
    for row, (key, label, _default) in enumerate(EPUB_PAUSE_FIELDS, 5):
        var = tk.DoubleVar(value=getattr(options, key) / 1000)
        pause_vars[key] = var
        ttk.Label(panel, text=label + " (giây)").grid(
            row=row, column=0, sticky="w", pady=8
        )
        ttk.Spinbox(
            panel, from_=0, to=10, increment=0.1, textvariable=var, width=12
        ).grid(row=row, column=1)
    music = ChapterMusicFrame(panel, options.music, preview_duration=lambda: round(pause_vars["chapter_pause_ms"].get() * 1000))
    music.grid(row=9, column=0, columnspan=2, sticky="ew", pady=8)
    srt_var = tk.BooleanVar(value=app.output_srt_var.get())
    ttk.Checkbutton(
        panel, text="Xuất kèm phụ đề .srt khớp audio", variable=srt_var
    ).grid(row=10, column=0, columnspan=2, sticky="w", pady=8)
    ttk.Label(
        panel,
        text="Nghỉ đoạn văn theo cài đặt hiện tại.\nAudio và SRT cùng tính các khoảng lặng.",
        wraplength=390,
    ).grid(row=11, column=0, columnspan=2, sticky="w", pady=15)
    if book.warnings:
        ttk.Label(
            panel, text="Lưu ý: " + "\n".join(book.warnings[:3]), wraplength=390
        ).grid(row=12, column=0, columnspan=2)

    def accept():
        try:
            selected = EpubOptions(
                chapter_start=start.get(),
                chapter_end=end.get(),
                read_titles=titles.get(),
                music=music.options(),
                include_volumes=volumes.get(),
                output_mode="chapters"
                if output.get() == "Mỗi chương một file"
                else "merged",
                **{k: round(v.get() * 1000) for k, v in pause_vars.items()},
            )
            book.select(selected)
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
