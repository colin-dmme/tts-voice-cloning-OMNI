from __future__ import annotations

import gradio as gr

from omni_tts_core.config import AppSettings
from omni_tts_ui_gradio import handlers


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
                        label="File nguồn .srt, .txt, .md",
                        file_count="multiple",
                        type="filepath",
                    )
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
                    sentence_pause_ms = gr.Slider(
                        label="Silence Pad, ms",
                        minimum=0,
                        maximum=2000,
                        value=int(preferences.get("sentence_pause_ms") or settings.generation_defaults.get("sentence_pause_ms", 450)),
                        step=50,
                    )
                    max_chunk_chars = gr.Slider(
                        label="Max Chars mỗi đoạn",
                        minimum=80,
                        maximum=700,
                        value=int(preferences.get("max_chunk_chars") or settings.generation_defaults.get("max_chunk_chars", 220)),
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
                    overwrite = gr.Checkbox(
                        label="Ghi đè file nếu đã tồn tại",
                        value=bool(preferences.get("overwrite", False)),
                    )
                    split_output = gr.Checkbox(
                        label="Tách mỗi dòng SRT/đoạn văn thành một file audio",
                        value=bool(preferences.get("split_output", True)),
                    )
                    output_srt = gr.Checkbox(
                        label="Xuất kèm SRT",
                        value=bool(preferences.get("output_srt", False)),
                    )
                    generate_btn = gr.Button("Tạo audio", variant="primary")

            status = gr.Textbox(label="Trạng thái", interactive=False)
            audio_preview = gr.Audio(label="Nghe thử", type="filepath")
            with gr.Row():
                audio_file = gr.File(label="File WAV")
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
                    sentence_pause_ms,
                    max_chunk_chars,
                    output_stem,
                    output_dir,
                    overwrite,
                    split_output,
                    output_srt,
                ],
                outputs=[status, audio_preview, audio_file, srt_file, zip_file],
            )
            model_id.change(
                handlers.generation_control_updates,
                inputs=[model_id, language],
                outputs=[language, speed, pitch_shift, emotion, voice_profile_id, voice_preset, codec_repo, temperature, top_k],
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
                    "Loại",
                    "Bắt buộc",
                    "Trạng thái",
                    "MB",
                    "Đường dẫn",
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
            with gr.Row():
                download_model_id = gr.Dropdown(
                    label="Model cần tải",
                    choices=handlers.all_model_choices(),
                    value=default_model,
                )
                download_btn = gr.Button("Tải model")
                download_required_btn = gr.Button("Tải các model bắt buộc còn thiếu")
                install_gpu_btn = gr.Button("Cài tăng tốc GPU cho model")
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
            install_gpu_btn.click(
                handlers.install_gpu_for_model,
                inputs=[download_model_id],
                outputs=[model_message, runtime_table],
            )
            refresh_btn.click(handlers.refresh_model_table, outputs=[model_table])
            refresh_btn.click(handlers.refresh_runtime_table, outputs=[runtime_table])
            catalog_btn.click(handlers.get_model_catalog_html, outputs=[catalog_html])

    return app
