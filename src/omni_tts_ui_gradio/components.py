from __future__ import annotations

import gradio as gr

from omni_tts_core.config import AppSettings
from omni_tts_ui_gradio import handlers


def build_app() -> gr.Blocks:
    settings = AppSettings()
    choices = handlers.model_choices()
    default_model = settings.generation_defaults.get("default_model_id", "omnivoice_vietnamese")
    default_language = settings.generation_defaults.get("default_language", "vi")

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
                    voice_profile_id = gr.Dropdown(
                        label="Profile giọng",
                        choices=handlers.voice_profile_choices(),
                        value="",
                    )
                    speed = gr.Slider(
                        label="Tốc độ đọc",
                        minimum=0.5,
                        maximum=1.8,
                        value=1.0,
                        step=0.05,
                    )
                    emotion = gr.Dropdown(
                        label="Cảm xúc VieNeu",
                        choices=[("Tự nhiên", "natural"), ("Kể chuyện", "storytelling")],
                        value="natural",
                    )
                    sentence_pause_ms = gr.Slider(
                        label="Nghỉ giữa câu, ms",
                        minimum=0,
                        maximum=2000,
                        value=settings.generation_defaults.get("sentence_pause_ms", 450),
                        step=50,
                    )
                    max_chunk_chars = gr.Slider(
                        label="Độ dài mỗi đoạn",
                        minimum=80,
                        maximum=700,
                        value=settings.generation_defaults.get("max_chunk_chars", 220),
                        step=20,
                    )
                    split_output = gr.Checkbox(
                        label="Tách mỗi dòng SRT/đoạn văn thành một file audio",
                        value=True,
                    )
                    output_srt = gr.Checkbox(
                        label="Xuất kèm SRT",
                        value=False,
                    )
                    generate_btn = gr.Button("Tạo audio", variant="primary")

            status = gr.Textbox(label="Trạng thái", interactive=False)
            audio_preview = gr.Audio(label="Nghe thử", type="filepath")
            with gr.Row():
                audio_file = gr.File(label="File WAV")
                srt_file = gr.File(label="File SRT")

            generate_btn.click(
                handlers.generate_speech,
                inputs=[
                    text,
                    language,
                    model_id,
                    voice_profile_id,
                    reference_audio,
                    reference_text,
                    speed,
                    emotion,
                    sentence_pause_ms,
                    max_chunk_chars,
                    split_output,
                    output_srt,
                ],
                outputs=[status, audio_preview, audio_file, srt_file],
            )
            model_id.change(
                handlers.generation_control_updates,
                inputs=[model_id, language],
                outputs=[language, speed, emotion, voice_profile_id],
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
                refresh_btn = gr.Button("Làm mới")
            model_message = gr.Textbox(label="Thông báo", interactive=False)

            download_btn.click(
                handlers.download_selected_model,
                inputs=[download_model_id],
                outputs=[model_message, model_table],
            )
            download_required_btn.click(
                handlers.download_required_models,
                outputs=[model_message, model_table],
            )
            refresh_btn.click(handlers.refresh_model_table, outputs=[model_table])
            refresh_btn.click(handlers.refresh_runtime_table, outputs=[runtime_table])

    return app
