from __future__ import annotations

import gradio as gr


def default_setting(service, model_id: str, key: str, fallback):
    return service.default_f5_settings(model_id).get(key, fallback)


def control_updates(service, model_id: str):
    active = service.supports_f5_settings(model_id)
    defaults = service.default_f5_settings(model_id)
    return (
        gr.update(value=defaults["f5_nfe_step"], interactive=active),
        gr.update(value=defaults["f5_cfg_strength"], interactive=active),
        gr.update(value=defaults["f5_sway_sampling_coef"], interactive=active),
        gr.update(value=defaults["f5_cross_fade_duration"], interactive=active),
        gr.update(value=defaults["f5_target_rms"], interactive=active),
        gr.update(value=0.0, interactive=active),
        gr.update(value=None, interactive=active),
        gr.update(value=defaults["f5_remove_silence"], interactive=active),
    )


def request_kwargs(
    service,
    model_id: str,
    nfe_step,
    cfg_strength,
    sway_sampling_coef,
    cross_fade_duration,
    target_rms,
    fix_duration,
    seed,
    remove_silence,
) -> dict:
    if not service.supports_f5_settings(model_id):
        return {}
    return {
        "f5_nfe_step": int(nfe_step),
        "f5_cfg_strength": float(cfg_strength),
        "f5_sway_sampling_coef": float(sway_sampling_coef),
        "f5_cross_fade_duration": float(cross_fade_duration),
        "f5_target_rms": float(target_rms),
        "f5_fix_duration": optional_positive_float(fix_duration),
        "f5_seed": optional_int(seed),
        "f5_remove_silence": bool(remove_silence),
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


def optional_positive_float(value) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None
