from __future__ import annotations

import gradio as gr

from omni_tts_core.config import AppSettings
from omni_tts_shared.epub import EpubOptions
from omni_tts_ui_gradio import handlers


def _preferred_int(preferences: dict, defaults: dict, key: str, default: int, legacy_key: str | None = None) -> int:
    value = preferences.get(key)
    if value is None and legacy_key is not None:
        value = preferences.get(legacy_key)
    if value is None:
        value = defaults.get(key)
    if value is None and legacy_key is not None:
        value = defaults.get(legacy_key)
    return int(default if value is None else value)


def build_app() -> gr.Blocks:
    settings = AppSettings()
    choices = handlers.model_choices()
    preferences = handlers.ui_preferences()
    available_model_ids = {value for _label, value in choices}
    preferred_model = str(preferences.get("model_id") or settings.generation_defaults.get("default_model_id", "omnivoice_vietnamese"))
    default_model = preferred_model if preferred_model in available_model_ids else settings.generation_defaults.get("default_model_id", "omnivoice_vietnamese")
    default_language = str(preferences.get("language") or settings.generation_defaults.get("default_language", "vi"))
    default_codec = str(preferences.get("codec_repo") or handlers.default_codec_repo(default_model))
    if default_codec not in {value for _label, value in handlers.codec_choices_for_model(default_model)}:
        default_codec = handlers.default_codec_repo(default_model)
    default_profile = str(preferences.get("voice_profile_id") or "")
    if default_profile not in {value for _label, value in handlers.voice_profile_choices()}:
        default_profile = ""
    f5_active = handlers.model_supports_f5_settings(default_model)
    f5_nfe_default = int(preferences.get("f5_nfe_step") or handlers.default_f5_setting(default_model, "f5_nfe_step", 32))
    f5_cfg_default = float(
        preferences.get("f5_cfg_strength") or handlers.default_f5_setting(default_model, "f5_cfg_strength", 2.0)
    )
    f5_sway_default = float(
        preferences.get("f5_sway_sampling_coef")
        if preferences.get("f5_sway_sampling_coef") is not None
        else handlers.default_f5_setting(default_model, "f5_sway_sampling_coef", -1.0)
    )
    f5_crossfade_default = float(
        preferences.get("f5_cross_fade_duration")
        or handlers.default_f5_setting(default_model, "f5_cross_fade_duration", 0.15)
    )
    f5_rms_default = float(
        preferences.get("f5_target_rms") or handlers.default_f5_setting(default_model, "f5_target_rms", 0.1)
    )
    chatterbox_active = handlers.model_supports_chatterbox_settings(default_model)
    chatterbox_temperature_default = float(
        preferences.get("chatterbox_temperature")
        or handlers.default_chatterbox_setting(default_model, "chatterbox_temperature", 0.8)
    )
    chatterbox_top_p_default = float(
        preferences.get("chatterbox_top_p")
        or handlers.default_chatterbox_setting(default_model, "chatterbox_top_p", 0.95)
    )
    chatterbox_top_k_default = int(
        preferences.get("chatterbox_top_k")
        or handlers.default_chatterbox_setting(default_model, "chatterbox_top_k", 1000)
    )
    chatterbox_repetition_default = float(
        preferences.get("chatterbox_repetition_penalty")
        or handlers.default_chatterbox_setting(default_model, "chatterbox_repetition_penalty", 1.2)
    )

    with gr.Blocks(title=settings.app_name) as app:
        gr.Markdown(f"# {settings.app_name}")
        gr.Markdown(handlers.startup_notice())

        with gr.Tab("Tạo giọng đọc"):
            with gr.Row():
                with gr.Column(scale=2):
                    text = gr.Textbox(
                        label="Nội dung cần đọc",
                        lines=12,
                        placeholder="Nhập nội dung tiếng Việt hoặc tiếng Anh...",
                    )
                    source_files = gr.File(
                        label="File nguồn .srt, .txt, .md, .epub",
                        file_count="multiple",
                        type="filepath",
                    )
                    with gr.Accordion("Đọc sách EPUB — chương và khoảng nghỉ", open=False):
                        gr.Markdown("Chọn chương theo vị trí. Đến chương = 0 là hết sách. Bật Xuất kèm SRT ở Đầu ra; phụ đề dùng cùng timeline với audio.")
                        epub_saved = preferences.get("epub_options", {})
                        epub_start = gr.Number(label="Từ chương", value=epub_saved.get("chapter_start", 1), precision=0, minimum=1)
                        epub_end = gr.Number(label="Đến chương (0 = hết sách)", value=epub_saved.get("chapter_end", 0), precision=0, minimum=0)
                        epub_titles = gr.Checkbox(label="Đọc tên chương", value=epub_saved.get("read_titles", True))
                        epub_volumes = gr.Checkbox(label="Đọc tên quyển", value=epub_saved.get("include_volumes", True))
                        epub_mode = gr.Dropdown(label="Cách xuất EPUB", choices=[("Mỗi chương một file", "chapters"), ("Ghép một file", "merged")], value=epub_saved.get("output_mode", "chapters"))
                        saved_epub = EpubOptions.model_validate(epub_saved)
                        boundary_controls = {}
                        for kind, caption in [('title', 'Sau tên chương, trước nội dung'), ('chapter', 'Giữa hai chương')]:
                            boundary = saved_epub.break_for(kind)
                            available = kind != 'title' or saved_epub.read_titles
                            updates = handlers.epub_break_updates(available, boundary.mode, boundary.duration_mode, boundary.duration_ms/1000)
                            with gr.Group():
                                gr.Markdown('### ' + caption)
                                type_control = gr.Dropdown(label='Loại nghỉ', choices=[('Không nghỉ','none'),('Khoảng lặng','silence'),('Nhạc','music')],value=boundary.mode,interactive=updates[0]['interactive'])
                                duration_control = gr.Dropdown(label='Độ dài nhạc',choices=[('Số giây cố định','fit_pause'),('Phát trọn bản nhạc','full_track')],value=boundary.duration_mode,interactive=updates[1]['interactive'])
                                seconds_control = gr.Slider(0,10,value=boundary.duration_ms/1000,step=.1,label='Số giây cố định',interactive=updates[2]['interactive'])
                                fade_in_control = gr.Slider(0,2,value=boundary.fade_in_ms/1000,step=.01,label='Fade-in — nhạc vào dần (giây)',interactive=updates[3]['interactive'])
                                fade_out_control = gr.Slider(0,3,value=boundary.fade_out_ms/1000,step=.01,label='Fade-out — nhạc tắt dần (giây)',interactive=updates[4]['interactive'])
                                preview_control = gr.Button('Nghe thử nhịp này',interactive=updates[5]['interactive'])
                                note_control = gr.Markdown(updates[6])
                                audio_control = gr.Audio(label='Nhịp nghỉ nghe thử',type='filepath')
                            boundary_controls[kind] = [type_control,duration_control,seconds_control,fade_in_control,fade_out_control,preview_control,note_control,audio_control]
                        title_kind,title_duration,epub_title_pause,title_fade_in,title_fade_out,_,_,_ = boundary_controls['title']
                        chapter_kind,chapter_duration,epub_chapter_pause,chapter_fade_in,chapter_fade_out,_,_,_ = boundary_controls['chapter']
                        epub_scene_pause = gr.Slider(0, 10, value=epub_saved.get("scene_pause_ms", 1200) / 1000, step=0.1, label="Nghỉ chuyển cảnh (giây)")
                        epub_volume_pause = gr.Slider(0, 10, value=epub_saved.get("volume_pause_ms", 1800) / 1000, step=0.1, label="Nghỉ sau tên quyển (giây)",interactive=saved_epub.include_volumes)
                        epub_volumes.change(lambda enabled:gr.update(interactive=enabled),inputs=[epub_volumes],outputs=[epub_volume_pause])
                        gr.Markdown('### Nguồn nhạc cho các nhịp nghỉ')
                        music_saved = epub_saved.get("music", {})
                        music_choices = handlers.chapter_music_choices()
                        music_selected = music_saved.get("track_id") or (music_choices[0][1] if music_choices else None)
                        music_enabled = gr.State(music_saved.get('enabled',False))
                        music_mode = gr.Dropdown(label="Cách chọn nhạc", choices=[("Chọn một bản cố định", "fixed"), ("Random trong nhóm chủ đề", "random_theme"),('Random trong tập đã tích','random_selection'),('Random theo preset đã lưu','preset')], value=music_saved.get("selection_mode", "fixed"))
                        music_preset = gr.Dropdown(label='Preset nhạc',choices=handlers.chapter_music_preset_choices(),value=music_saved.get('preset_id'))
                        music_theme_ids = gr.CheckboxGroup(label='Phối nhiều nhóm chủ đề',choices=handlers.chapter_music_themes(),value=music_saved.get('theme_ids',[]))
                        music_track_ids = gr.CheckboxGroup(label='Các bài thêm riêng',choices=music_choices,value=music_saved.get('track_ids',[]))
                        music_excluded_ids = gr.CheckboxGroup(label='Bỏ các bài này khỏi tập random',choices=music_choices,value=music_saved.get('excluded_track_ids',[]))
                        music_theme = gr.Dropdown(label="Nhóm chủ đề cho random", choices=handlers.chapter_music_themes(), value=music_saved.get("theme"))
                        music_seed = gr.Number(label="Lượt trộn (giữ số để tiếp tục, đổi số để trộn lại)", value=music_saved.get("random_seed", 0), minimum=0, maximum=2147483647, precision=0)
                        music_track = gr.Dropdown(label="Bản nhạc cho chế độ cố định", choices=music_choices, value=music_selected)
                        music_volume = gr.Slider(0, 100, value=music_saved.get("volume_percent", 30), step=1, label="Âm lượng nhạc (%)")
                        music_duration_mode = gr.State(music_saved.get('duration_mode','fit_pause'))
                        music_between = gr.State(music_saved.get('between_chapters',True))
                        music_after_title = gr.State(music_saved.get('after_title',False))
                        note_inputs=[music_track,music_mode,music_theme,music_preset,music_theme_ids,music_track_ids,music_excluded_ids]
                        music_note = gr.Markdown(handlers.music_selection_note(music_selected,music_saved.get('selection_mode','fixed'),music_saved.get('theme'),
                            music_saved.get('preset_id'),music_saved.get('theme_ids',[]),music_saved.get('track_ids',[]),music_saved.get('excluded_track_ids',[])))
                        for music_control in note_inputs:
                            music_control.change(handlers.music_selection_note,inputs=note_inputs,outputs=[music_note])
                        music_upload = gr.File(label="Thêm nhạc cá nhân (tự lấy tối đa 30 giây)", type="filepath", file_types=[".wav", ".mp3", ".flac", ".ogg", ".m4a"])
                        music_upload.change(handlers.import_epub_music, inputs=[music_upload], outputs=[music_track])
                        for kind, controls in boundary_controls.items():
                            available_control = epub_titles if kind == 'title' else gr.State(True)
                            boundary_inputs = [available_control,controls[0],controls[1],controls[2]]
                            for control in [available_control,controls[0],controls[1],controls[2]]:
                                if not isinstance(control,gr.State):
                                    control.change(handlers.epub_break_updates,inputs=boundary_inputs,outputs=controls[:7])
                            controls[5].click(handlers.preview_epub_music,
                                inputs=[music_track,controls[2],music_volume,music_mode,music_theme,music_seed,controls[1],controls[3],controls[4],
                                        music_preset,music_theme_ids,music_track_ids,music_excluded_ids],outputs=[controls[7]])
                        source_inputs=[epub_titles,title_kind,title_duration,epub_title_pause,chapter_kind,chapter_duration,epub_chapter_pause,music_mode]
                        source_outputs=[music_mode,music_track,music_theme,music_seed,music_volume,music_upload,music_preset,music_theme_ids,music_track_ids,music_excluded_ids]
                        for control in source_inputs:
                            control.change(handlers.epub_music_source_updates,inputs=source_inputs,outputs=source_outputs)
                        initial_source_updates=handlers.epub_music_source_updates(saved_epub.read_titles,
                            saved_epub.break_for('title').mode,saved_epub.break_for('title').duration_mode,saved_epub.break_for('title').duration_ms/1000,
                            saved_epub.break_for('chapter').mode,saved_epub.break_for('chapter').duration_mode,saved_epub.break_for('chapter').duration_ms/1000,
                            music_saved.get('selection_mode','fixed'))
                        for control,update in zip(source_outputs,initial_source_updates):
                            control.interactive=update['interactive']
                        with gr.Accordion("Nội dung đưa vào giọng đọc", open=True):
                            content_saved = saved_epub.content
                            content_skip_references = gr.Checkbox(label="Bỏ nguồn / tài liệu tham khảo",value=content_saved.skip_references)
                            content_url_mode = gr.Dropdown(label="Đường link",choices=[("Không đọc URL / DOI","skip"),("Chỉ đọc tên miền","domain"),("Đọc nguyên địa chỉ","read")],value=content_saved.url_mode)
                            content_read_notes = gr.Checkbox(label="Giữ ghi chú giải thích",value=content_saved.read_notes)
                            content_han_mode = gr.Dropdown(label="Chữ Hán",choices=[("Dùng nghĩa Việt sẵn có + cảnh báo","prefer_vietnamese"),("Giữ và cảnh báo","warn"),("Giữ, không cảnh báo","keep")],value=content_saved.han_mode)
                            content_frontmatter = gr.Checkbox(label="Đọc giới thiệu / thuật ngữ",value=content_saved.include_frontmatter)
                            content_appendices = gr.Checkbox(label="Đọc phụ lục nội dung",value=content_saved.include_appendices)
                            content_technical = gr.Checkbox(label="Đọc ghi chú kỹ thuật cuối sách",value=content_saved.include_technical_notes)
                            content_export = gr.Checkbox(label="Xuất nguồn tham khảo riêng cạnh audio",value=content_saved.export_references)
                            content_han_readings = gr.Textbox(label="Cách đọc chữ Hán — mỗi dòng: chữ gốc = cách đọc",value="\n".join(f"{a} = {b}" for a,b in content_saved.han_readings.items()),placeholder="万 = vạn",lines=3)
                            content_inputs = [content_skip_references,content_url_mode,content_read_notes,content_han_mode,content_frontmatter,content_appendices,content_technical,content_export,content_han_readings]
                        content_preview_index = gr.Number(label="Vị trí phần muốn xem",value=1,minimum=1,precision=0)
                        epub_preview_button = gr.Button("So sánh bản gốc / bản đọc — không tạo giọng")
                        content_status = gr.Textbox(label="Kết quả lọc và lưu ý",interactive=False,lines=3)
                        with gr.Tabs():
                            with gr.Tab("Văn bản sẽ đọc"):
                                epub_preview = gr.Textbox(label="Bản đọc sau lọc",lines=12,interactive=False)
                            with gr.Tab("Bản gốc"):
                                content_original = gr.Textbox(label="Bản gốc",lines=12,interactive=False)
                            with gr.Tab("Đã bỏ / đã đổi"):
                                content_changes = gr.Textbox(label="Chi tiết thay đổi",lines=12,interactive=False)
                        epub_preview_button.click(handlers.preview_epub_content, inputs=[source_files,epub_start,epub_end,content_preview_index,*content_inputs],outputs=[content_status,epub_preview,content_original,content_changes])
                    reference_audio = gr.Audio(
                        label="Giọng mẫu WAV, nên 3-10 giây",
                        type="filepath",
                    )
                    reference_text = gr.Textbox(
                        label="Transcript của giọng mẫu",
                        lines=2,
                        placeholder="Có thể để trống, nhưng điền vào sẽ ổn định hơn.",
                    )
                with gr.Column(scale=1):
                    language = gr.Radio(
                        label="Ngôn ngữ",
                        choices=handlers.language_choices_for_model(default_model),
                        value=handlers.default_language_for_model(default_model, default_language),
                    )
                    model_id = gr.Dropdown(
                        label="Model TTS",
                        choices=choices,
                        value=default_model,
                    )
                    codec_repo = gr.Dropdown(
                        label="Codec VieNeu",
                        choices=handlers.codec_choices_for_model(default_model),
                        value=default_codec,
                        interactive=handlers.model_supports_codec(default_model),
                    )
                    voice_profile_id = gr.Dropdown(
                        label="Profile giọng",
                        choices=handlers.voice_profile_choices(),
                        value=default_profile,
                    )
                    profile_compat_info = gr.Textbox(
                        label="Tương thích profile",
                        interactive=False,
                        lines=1,
                    )
                    voice_preset = gr.Dropdown(
                        label="Preset giọng (khi không clone)",
                        choices=handlers.speaker_choices_for_model(default_model),
                        value=preferences.get("speaker_id") or handlers.default_voice_preset_id(default_model) or "",
                        interactive=handlers.has_voice_presets(default_model),
                    )
                    speed = gr.Slider(
                        label="Tốc độ đọc",
                        minimum=0.5,
                        maximum=1.8,
                        value=float(preferences.get("speed", 1.0) or 1.0),
                        step=0.05,
                    )
                    pitch_shift = gr.Slider(
                        label="Pitch shift",
                        minimum=-12.0,
                        maximum=12.0,
                        value=float(preferences.get("pitch_shift", 0.0) or 0.0),
                        step=0.5,
                        interactive=handlers.model_supports_pitch_shift(default_model),
                    )
                    emotion = gr.Dropdown(
                        label="Cảm xúc VieNeu",
                        choices=[("Tự nhiên", "natural"), ("Kể chuyện", "storytelling")],
                        value=str(preferences.get("emotion") or "natural"),
                    )
                    runtime_target = gr.Dropdown(
                        label="Thiết bị xử lý",
                        choices=handlers.runtime_target_choices(),
                        value=str(preferences.get("runtime_target") or "auto"),
                    )
                    temperature = gr.Slider(
                        label="Temperature VieNeu",
                        minimum=0.1,
                        maximum=2.0,
                        value=float(preferences.get("temperature") or handlers.default_temperature(default_model)),
                        step=0.1,
                        interactive=handlers.model_supports_sampling(default_model),
                    )
                    top_k = gr.Slider(
                        label="Top-K VieNeu",
                        minimum=1,
                        maximum=200,
                        value=int(preferences.get("top_k") or handlers.default_top_k(default_model)),
                        step=1,
                        interactive=handlers.model_supports_sampling(default_model),
                    )
                    f5_nfe_step = gr.Slider(
                        label="F5 NFE step",
                        minimum=4,
                        maximum=128,
                        value=f5_nfe_default,
                        step=1,
                        interactive=f5_active,
                        info="Số bước suy luận. 16 nhanh hơn, 32 cân bằng, 48-64 có thể tốt hơn nhưng chậm hơn.",
                    )
                    f5_cfg_strength = gr.Slider(
                        label="F5 CFG strength",
                        minimum=0.0,
                        maximum=10.0,
                        value=f5_cfg_default,
                        step=0.1,
                        interactive=f5_active,
                        info="Độ bám vào giọng mẫu/prompt. Mặc định 2.0; tăng quá cao dễ mất tự nhiên.",
                    )
                    f5_sway_sampling_coef = gr.Slider(
                        label="F5 Sway sampling coef",
                        minimum=-5.0,
                        maximum=5.0,
                        value=f5_sway_default,
                        step=0.1,
                        interactive=f5_active,
                        info="Hệ số lấy mẫu riêng của F5. Mặc định -1.0; chỉ đổi khi A/B test.",
                    )
                    f5_cross_fade_duration = gr.Slider(
                        label="F5 Cross-fade duration",
                        minimum=0.0,
                        maximum=2.0,
                        value=f5_crossfade_default,
                        step=0.05,
                        interactive=f5_active,
                        info="Số giây cross-fade khi ghép audio. 0.15 thường làm mối nối bớt gắt.",
                    )
                    f5_target_rms = gr.Slider(
                        label="F5 Target RMS",
                        minimum=0.01,
                        maximum=1.0,
                        value=f5_rms_default,
                        step=0.01,
                        interactive=f5_active,
                        info="Mức âm lượng chuẩn hóa reference audio. Mặc định 0.1.",
                    )
                    f5_fix_duration = gr.Number(
                        label="F5 Fix duration",
                        value=float(preferences.get("f5_fix_duration") or 0.0),
                        precision=2,
                        interactive=f5_active,
                        info="Ép thời lượng đầu ra; để 0 để F5 tự tính.",
                    )
                    f5_seed = gr.Number(
                        label="F5 Seed",
                        value=preferences.get("f5_seed"),
                        precision=0,
                        interactive=f5_active,
                        info="Để trống để random. Điền số nếu muốn chạy lại gần giống kết quả cũ.",
                    )
                    f5_remove_silence = gr.Checkbox(
                        label="F5 Remove silence",
                        value=bool(preferences.get("f5_remove_silence", False)),
                        interactive=f5_active,
                        info="Cắt khoảng lặng sau khi sinh; gọn hơn nhưng có thể làm mất nhịp nghỉ tự nhiên.",
                    )
                    chatterbox_temperature = gr.Slider(
                        label="Chatterbox Temperature",
                        minimum=0.1,
                        maximum=2.0,
                        value=chatterbox_temperature_default,
                        step=0.05,
                        interactive=chatterbox_active,
                        info="Độ ngẫu nhiên của Chatterbox Turbo. 0.8 là mặc định; tăng thì đa dạng hơn nhưng dễ lệch.",
                    )
                    chatterbox_top_p = gr.Slider(
                        label="Chatterbox Top-P",
                        minimum=0.05,
                        maximum=1.0,
                        value=chatterbox_top_p_default,
                        step=0.01,
                        interactive=chatterbox_active,
                        info="Giữ nhóm token có tổng xác suất cao nhất. Mặc định 0.95; giảm khi audio quá ngẫu nhiên.",
                    )
                    chatterbox_top_k = gr.Slider(
                        label="Chatterbox Top-K",
                        minimum=1,
                        maximum=2000,
                        value=chatterbox_top_k_default,
                        step=10,
                        interactive=chatterbox_active,
                        info="Số token tối đa mỗi bước. Mặc định 1000 theo Turbo; giảm mạnh có thể kém tự nhiên.",
                    )
                    chatterbox_repetition_penalty = gr.Slider(
                        label="Chatterbox Repetition penalty",
                        minimum=1.0,
                        maximum=3.0,
                        value=chatterbox_repetition_default,
                        step=0.05,
                        interactive=chatterbox_active,
                        info="Phạt lặp token. Mặc định 1.2 theo bản Turbo mới; tăng nhẹ nếu nghe bị lặp.",
                    )
                    chatterbox_seed = gr.Number(
                        label="Chatterbox Seed",
                        value=preferences.get("chatterbox_seed"),
                        precision=0,
                        interactive=chatterbox_active,
                        info="Để trống để random. Điền số nếu muốn chạy lại gần giống kết quả cũ.",
                    )
                    chatterbox_norm_loudness = gr.Checkbox(
                        label="Chatterbox Normalize loudness",
                        value=bool(preferences.get("chatterbox_norm_loudness", True)),
                        interactive=chatterbox_active,
                        info="Chuẩn hóa độ lớn audio mẫu trước khi clone; nên bật nếu mẫu quá nhỏ hoặc quá lớn.",
                    )
                    sentence_pause_ms = gr.Slider(
                        label="Nghỉ giữa câu/chunk, ms",
                        minimum=0,
                        maximum=2000,
                        value=_preferred_int(preferences, settings.generation_defaults, "sentence_pause_ms", 450),
                        step=50,
                    )
                    paragraph_pause_ms = gr.Slider(
                        label="Nghỉ giữa đoạn trong file tổng, ms",
                        minimum=0,
                        maximum=10000,
                        value=_preferred_int(
                            preferences,
                            settings.generation_defaults,
                            "paragraph_pause_ms",
                            0,
                            legacy_key="srt_file_padding_ms",
                        ),
                        step=50,
                    )
                    max_chunk_chars = gr.Slider(
                        label="Max ký tự mỗi đoạn nhỏ",
                        minimum=80,
                        maximum=700,
                        value=_preferred_int(preferences, settings.generation_defaults, "max_chunk_chars", 220),
                        step=20,
                    )
                    output_stem = gr.Textbox(
                        label="Tên file xuất",
                        value=str(preferences.get("output_stem") or ""),
                        placeholder="Để trống để tự đặt theo nội dung/file nguồn",
                    )
                    output_dir = gr.Textbox(
                        label="Thư mục xuất trên máy thuê",
                        value=str(preferences.get("output_dir") or ""),
                        placeholder="Để trống để lưu vào outputs/jobs",
                    )
                    output_audio_format = gr.Dropdown(
                        label="Định dạng audio",
                        choices=[("WAV PCM 16-bit", "wav"), ("MP3", "mp3")],
                        value=str(preferences.get("output_audio_format") or settings.generation_defaults.get("output_audio_format", "wav")),
                    )
                    mp3_bitrate_kbps = gr.Dropdown(
                        label="Bitrate MP3",
                        choices=[128, 160, 192, 256, 320],
                        value=int(preferences.get("mp3_bitrate_kbps") or settings.generation_defaults.get("mp3_bitrate_kbps", 192)),
                    )
                    overwrite = gr.Checkbox(
                        label="Ghi đè file nếu đã tồn tại",
                        value=bool(preferences.get("overwrite", False)),
                    )
                    split_output = gr.Checkbox(
                        label="Tách dòng SRT/đoạn văn thành file riêng",
                        value=bool(preferences.get("split_output", True)),
                    )
                    output_srt = gr.Checkbox(
                        label="Xuất kèm SRT",
                        value=bool(preferences.get("output_srt", False)),
                    )
                    join_split_output_audio = gr.Checkbox(
                        label="Nối thêm file tổng",
                        value=bool(preferences.get("join_split_output_audio", False)),
                    )
                    generate_btn = gr.Button("Tạo audio", variant="primary")

            status = gr.Textbox(label="Trạng thái", interactive=False)
            audio_preview = gr.Audio(label="Nghe thử", type="filepath")
            with gr.Row():
                audio_file = gr.File(label="File audio")
                srt_file = gr.File(label="File SRT")
                zip_file = gr.File(label="Tải toàn bộ ZIP")

            generate_btn.click(
                handlers.generate_speech,
                inputs=[
                    text,
                    source_files,
                    language,
                    model_id,
                    codec_repo,
                    voice_profile_id,
                    reference_audio,
                    reference_text,
                    voice_preset,
                    speed,
                    pitch_shift,
                    emotion,
                    runtime_target,
                    temperature,
                    top_k,
                    f5_nfe_step,
                    f5_cfg_strength,
                    f5_sway_sampling_coef,
                    f5_cross_fade_duration,
                    f5_target_rms,
                    f5_fix_duration,
                    f5_seed,
                    f5_remove_silence,
                    chatterbox_temperature,
                    chatterbox_top_p,
                    chatterbox_top_k,
                    chatterbox_repetition_penalty,
                    chatterbox_seed,
                    chatterbox_norm_loudness,
                    sentence_pause_ms,
                    paragraph_pause_ms,
                    max_chunk_chars,
                    output_stem,
                    output_dir,
                    output_audio_format,
                    mp3_bitrate_kbps,
                    overwrite,
                    split_output,
                    output_srt,
                    join_split_output_audio,
                    epub_start, epub_end, epub_titles, epub_volumes, epub_mode,
                    epub_title_pause, epub_chapter_pause, epub_scene_pause, epub_volume_pause,
                    music_enabled, music_track, music_volume, music_between, music_after_title,
                    music_mode, music_theme, music_seed,
                    music_duration_mode,
                    title_kind,title_duration,title_fade_in,title_fade_out,
                    chapter_kind,chapter_duration,chapter_fade_in,chapter_fade_out,
                    music_preset,music_theme_ids,music_track_ids,music_excluded_ids,
                    *content_inputs,
                ],
                outputs=[status, audio_preview, audio_file, srt_file, zip_file],
            )
            model_id.change(
                handlers.generation_control_updates,
                inputs=[model_id, language],
                outputs=[
                    language,
                    speed,
                    pitch_shift,
                    emotion,
                    voice_profile_id,
                    voice_preset,
                    codec_repo,
                    temperature,
                    top_k,
                    f5_nfe_step,
                    f5_cfg_strength,
                    f5_sway_sampling_coef,
                    f5_cross_fade_duration,
                    f5_target_rms,
                    f5_fix_duration,
                    f5_seed,
                    f5_remove_silence,
                    chatterbox_temperature,
                    chatterbox_top_p,
                    chatterbox_top_k,
                    chatterbox_repetition_penalty,
                    chatterbox_seed,
                    chatterbox_norm_loudness,
                ],
            )
            voice_profile_id.change(
                handlers.profile_changed_updates,
                inputs=[voice_profile_id, model_id],
                outputs=[voice_preset],
            )
            voice_preset.change(
                handlers.speaker_changed_updates,
                inputs=[voice_preset, model_id],
                outputs=[voice_profile_id],
            )
            voice_profile_id.change(
                handlers.profile_compat_update,
                inputs=[voice_profile_id, model_id],
                outputs=[profile_compat_info],
            )
            model_id.change(
                handlers.profile_compat_update,
                inputs=[voice_profile_id, model_id],
                outputs=[profile_compat_info],
            )

        with gr.Tab("Profile giọng"):
            profile_table = gr.Dataframe(
                headers=[
                    "ID",
                    "Tên",
                    "Ngôn ngữ",
                    "Thời lượng",
                    "Dự án",
                    "File giọng mẫu",
                ],
                value=handlers.voice_profile_table(),
                interactive=False,
                wrap=True,
            )
            edit_profile_id = gr.Dropdown(
                label="Profile cần sửa/xóa",
                choices=[item for item in handlers.voice_profile_choices() if item[1]],
                value=None,
            )
            profile_id_hidden = gr.Textbox(label="Profile ID", visible=False)
            with gr.Row():
                load_profile_btn = gr.Button("Nạp profile")
                new_profile_btn = gr.Button("Tạo mới")
                delete_profile_btn = gr.Button("Xóa profile")
                refresh_profile_btn = gr.Button("Làm mới")
            profile_name = gr.Textbox(label="Tên profile")
            profile_audio = gr.Audio(label="File giọng mẫu", type="filepath")
            profile_language = gr.Dropdown(
                label="Ngôn ngữ",
                choices=handlers.LANGUAGE_PROFILE_CHOICES,
                value="vi",
            )
            profile_project = gr.Textbox(label="Dự án")
            profile_transcript = gr.Textbox(label="Transcript", lines=4)
            profile_notes = gr.Textbox(label="Ghi chú", lines=3)
            save_profile_btn = gr.Button("Lưu profile", variant="primary")
            profile_message = gr.Textbox(label="Thông báo", interactive=False)

            load_profile_btn.click(
                handlers.load_voice_profile_form,
                inputs=[edit_profile_id],
                outputs=[
                    profile_id_hidden,
                    profile_name,
                    profile_audio,
                    profile_transcript,
                    profile_language,
                    profile_project,
                    profile_notes,
                ],
            )
            new_profile_btn.click(
                handlers.clear_voice_profile_form,
                outputs=[
                    profile_id_hidden,
                    profile_name,
                    profile_audio,
                    profile_transcript,
                    profile_language,
                    profile_project,
                    profile_notes,
                ],
            )
            save_profile_btn.click(
                handlers.save_voice_profile,
                inputs=[
                    profile_id_hidden,
                    profile_name,
                    profile_audio,
                    profile_transcript,
                    profile_language,
                    profile_project,
                    profile_notes,
                ],
                outputs=[profile_message, profile_table, voice_profile_id, edit_profile_id, profile_id_hidden],
            )
            delete_profile_btn.click(
                handlers.delete_voice_profile,
                inputs=[edit_profile_id],
                outputs=[profile_message, profile_table, voice_profile_id, edit_profile_id, profile_id_hidden],
            )
            refresh_profile_btn.click(
                handlers.refresh_voice_profile_controls,
                outputs=[profile_table, voice_profile_id, edit_profile_id],
            )

        with gr.Tab("Quản lý model"):
            model_table = gr.Dataframe(
                headers=[
                    "Tên",
                    "Dùng để làm gì",
                    "Provider",
                    "Bắt buộc",
                    "Trạng thái",
                    "Dung lượng",
                    "Kiểu lưu",
                    "Nơi lưu",
                    "HF repo",
                ],
                value=handlers.refresh_model_table(),
                interactive=False,
                wrap=True,
            )
            runtime_table = gr.Dataframe(
                headers=[
                    "Model",
                    "Provider",
                    "Cài đặt",
                    "GPU khả dụng",
                    "Thiết bị thực tế",
                    "Tên thiết bị",
                    "Ghi chú",
                ],
                value=handlers.refresh_runtime_table(),
                interactive=False,
                wrap=True,
            )
            setup_table = gr.Dataframe(
                headers=[
                    "Nhóm",
                    "Mục",
                    "Trạng thái",
                    "Có thể bấm",
                    "Chi tiết",
                ],
                value=handlers.refresh_setup_table(default_model),
                interactive=False,
                wrap=True,
            )
            with gr.Row():
                download_model_id = gr.Dropdown(
                    label="Model cần tải",
                    choices=handlers.all_model_choices(),
                    value=default_model,
                )
                download_btn = gr.Button("Tải model")
                download_required_btn = gr.Button("Tải các model bắt buộc còn thiếu")
                preview_remove_btn = gr.Button("Xem trước gỡ")
                remove_model_btn = gr.Button("Xác nhận gỡ")
                install_base_btn = gr.Button("Cài worker/môi trường")
                install_gpu_btn = gr.Button("Cài GPU/CUDA")
                refresh_btn = gr.Button("Làm mới")
                catalog_btn = gr.Button("Xem catalog model")
            model_message = gr.Textbox(label="Thông báo", interactive=False)
            catalog_html = gr.HTML(visible=False)

            download_btn.click(
                handlers.download_selected_model,
                inputs=[download_model_id],
                outputs=[model_message, model_table],
            )
            download_required_btn.click(
                handlers.download_required_models,
                outputs=[model_message, model_table],
            )
            preview_remove_btn.click(
                handlers.preview_remove_model,
                inputs=[download_model_id],
                outputs=[model_message, model_table],
            )
            remove_model_btn.click(
                handlers.remove_selected_model,
                inputs=[download_model_id],
                outputs=[model_message, model_table],
            )
            install_gpu_btn.click(
                handlers.install_gpu_for_model,
                inputs=[download_model_id],
                outputs=[model_message, setup_table, runtime_table],
            )
            install_base_btn.click(
                handlers.install_base_for_model,
                inputs=[download_model_id],
                outputs=[model_message, setup_table, runtime_table],
            )
            refresh_btn.click(handlers.refresh_model_table, outputs=[model_table])
            refresh_btn.click(handlers.refresh_runtime_table, outputs=[runtime_table])
            refresh_btn.click(handlers.refresh_setup_table, inputs=[download_model_id], outputs=[setup_table])
            download_model_id.change(
                handlers.refresh_setup_table,
                inputs=[download_model_id],
                outputs=[setup_table],
            )
            catalog_btn.click(handlers.get_model_catalog_html, outputs=[catalog_html])

    return app
