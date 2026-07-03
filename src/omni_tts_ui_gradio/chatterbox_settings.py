from __future__ import annotations

import gradio as gr


def default_setting(service, model_id: str, key: str, fallback):
    return service.default_chatterbox_settings(model_id).get(key, fallback)


def control_updates(service, model_id: str):
    active = service.supports_chatterbox_settings(model_id)
    defaults = service.default_chatterbox_settings(model_id)
    return (
        gr.update(value=defaults["chatterbox_temperature"], interactive=active),
        gr.update(value=defaults["chatterbox_top_p"], interactive=active),
        gr.update(value=defaults["chatterbox_top_k"], interactive=active),
        gr.update(value=defaults["chatterbox_repetition_penalty"], interactive=active),
        gr.update(value=None, interactive=active),
        gr.update(value=defaults["chatterbox_norm_loudness"], interactive=active),
    )


def request_kwargs(
    service,
    model_id: str,
    temperature,
    top_p,
    top_k,
    repetition_penalty,
    seed,
    norm_loudness,
) -> dict:
    if not service.supports_chatterbox_settings(model_id):
        return {}
    return {
        "chatterbox_temperature": float(temperature),
        "chatterbox_top_p": float(top_p),
        "chatterbox_top_k": int(top_k),
        "chatterbox_repetition_penalty": float(repetition_penalty),
        "chatterbox_seed": optional_int(seed),
        "chatterbox_norm_loudness": bool(norm_loudness),
    }


def optional_int(value) -> int | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return int(float(text))
    except ValueError:
        return None
