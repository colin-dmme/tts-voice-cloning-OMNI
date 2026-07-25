"""UI-agnostic label/badge/status mapping helpers.

Single source of truth for human-readable strings that any GUI (tkinter,
Qt, gradio) renders for models, runtime devices, setup tasks and results.
Ported from the tkinter controller/app so a GUI never hardcodes these maps.
"""

from __future__ import annotations

from omni_tts_core.model_registry import ModelSpec
from omni_tts_shared.schemas import (
    GenerateSpeechResult,
    ModelStatus,
    RuntimeStatus,
    SetupTaskStatus,
)


# --- Model choice / badges -------------------------------------------------

def model_choice_label(spec: ModelSpec) -> str:
    badges = model_badges(spec.catalog_info)
    if not badges:
        return spec.display_name
    suffix = " ".join(f"[{item}]" for item in badges)
    return f"{spec.display_name} {suffix}"


def model_badges(info: dict) -> list[str]:
    badges: list[str] = []
    origin = origin_badge(str(info.get("origin") or ""))
    category = category_badge(str(info.get("category") or ""))
    variant = str(info.get("variant_badge") or "").strip()
    risk = risk_badge(str(info.get("risk") or ""))
    if origin:
        badges.append(origin)
    elif category:
        badges.append(category)
    if variant:
        badges.append(variant)
    if risk and risk not in badges:
        badges.append(risk)
    return badges


def category_badge(category: str) -> str:
    return {
        "official-cpu": "Official",
        "official-gpu": "Official",
        "community": "Community",
        "experimental": "Debug/Legacy",
        "multilingual": "Multilingual",
        "support": "Support",
    }.get(category, "Custom" if category else "")


def origin_badge(origin: str) -> str:
    return {
        "official": "Official",
        "community": "Community",
        "custom": "Custom",
    }.get(origin, "")


def risk_badge(risk: str) -> str:
    return {
        "test": "Test",
        "checkpoint": "Checkpoint",
        "debug": "Debug",
    }.get(risk, "")


def category_label(category: str) -> str:
    return {
        "official-cpu": "Official",
        "official-gpu": "Official",
        "community": "Community",
        "experimental": "Debug/Legacy",
        "multilingual": "Multilingual",
        "support": "Support",
    }.get(category, "Custom/Unknown" if category else "")


def origin_label(origin: str) -> str:
    return {
        "official": "Official",
        "community": "Community",
        "custom": "Custom",
    }.get(origin, "")


def risk_label(risk: str) -> str:
    return {
        "stable": "Ổn định",
        "test": "Test A/B",
        "checkpoint": "Checkpoint thô",
        "debug": "Debug",
    }.get(risk, "")


def model_choice_info(spec: ModelSpec) -> str:
    info = spec.catalog_info
    category = category_label(str(info.get("category") or ""))
    origin = origin_label(str(info.get("origin") or ""))
    variant = str(info.get("variant") or "").strip()
    base_model = str(info.get("base_model") or "").strip()
    risk = risk_label(str(info.get("risk") or ""))
    highlight = str(info.get("highlight") or "").strip()
    recommend = str(info.get("recommend_for") or "").strip()
    parts = [f"Nguồn: {origin}" if origin else f"Nhóm: {category}"]
    if origin and category and category != origin:
        parts.append(f"Nhóm: {category}")
    if variant:
        parts.append(variant)
    if base_model:
        parts.append(f"Base: {base_model}")
    if risk:
        parts.append(f"Mức: {risk}")
    if highlight:
        parts.append(highlight)
    if recommend:
        parts.append(recommend)
    elif spec.notes:
        parts.append(spec.notes)
    return " · ".join(parts)


# --- Runtime device --------------------------------------------------------

def runtime_device_label(value: str | None) -> str:
    return {
        "auto-cuda": "Auto → CUDA",
        "auto-cpu": "Auto → CPU",
        "cuda-unavailable": "CUDA chưa sẵn sàng",
        "cuda-partial": "CUDA chưa đủ backend",
        "not-installed": "Chưa cài",
        "missing": "Thiếu model",
        "worker": "Worker",
        "cuda": "CUDA",
        "cpu": "CPU",
        "auto": "Auto",
    }.get(str(value or ""), str(value or "Không rõ"))


def runtime_device_detail(actual_device: str | None, device_name: str) -> str:
    if not device_name:
        return ""
    if actual_device in {"cpu", "auto-cpu", "cuda-unavailable", "cuda-partial"}:
        return ""
    if actual_device in {"cuda", "auto-cuda"} and device_name.startswith("CUDA - "):
        return f" - {device_name.removeprefix('CUDA - ')}"
    return f" - {device_name}"


def runtime_status_text(status: RuntimeStatus) -> str:
    installed = "đã cài" if status.installed else "chưa cài"
    gpu = "có CUDA" if status.gpu_available else "chưa có CUDA"
    device = runtime_device_label(status.actual_device)
    detail = runtime_device_detail(status.actual_device, status.device_name)
    return f"{status.display_name}: {installed}, {gpu}, chạy bằng {device}{detail}. {status.message}"


# --- Model management table -------------------------------------------------

def model_status_label(item: ModelStatus) -> str:
    if item.worker_installed is False:
        return "Chưa cài worker"
    if item.hf_cached is False:
        return "Thiếu HF cache"
    if item.installed:
        return "Sẵn sàng" if item.worker_installed is not True else "Worker + model OK"
    if item.worker_installed is True:
        return "Worker OK, thiếu model"
    return "Chưa tải"


def format_model_size(item: ModelStatus) -> str:
    total = item.total_size_mb if item.total_size_mb else item.size_mb
    if total >= 1024:
        return f"{total / 1024:.2f} GB"
    return f"{total:.0f} MB"


# --- Setup task table -------------------------------------------------------

def setup_status_values(item: SetupTaskStatus) -> tuple[str, str, str, str, str]:
    action = item.action_label if item.can_run else ""
    if item.script_name and action:
        action = f"{action} ({item.script_name})"
    return (
        setup_scope_label(item.scope),
        item.label,
        setup_status_label(item.status),
        action,
        short_text(item.detail, 150),
    )


def setup_scope_label(value: str) -> str:
    return {
        "environment": "Máy",
        "storage": "Storage",
        "model": "Model",
        "runtime": "Runtime",
        "worker": "Worker",
        "gpu": "GPU",
    }.get(value, value)


def setup_status_label(value: str) -> str:
    return {
        "ok": "OK",
        "missing": "Thiếu",
        "warning": "Cảnh báo",
        "optional": "Tùy chọn",
        "error": "Lỗi",
    }.get(value, value)


def short_text(value: str, limit: int) -> str:
    text = " ".join((value or "").split())
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"


# --- Generation result ------------------------------------------------------

def format_result(result: GenerateSpeechResult) -> str:
    if result.item_audio_paths:
        joined = "\n".join(str(path) for path in result.item_audio_paths)
        merged_line = ""
        if result.audio_path and result.audio_path not in result.item_audio_paths:
            merged_line = f"\nAudio tổng: {result.audio_path}"
        srt_line = ""
        if result.item_srt_paths:
            srt_joined = "\n".join(str(path) for path in result.item_srt_paths)
            srt_line = f"\nSRT:\n{srt_joined}"
        elif result.srt_path:
            srt_line = f"\nSRT: {result.srt_path}"
        return (
            f"{result.message}\n"
            f"Số đoạn nhỏ: {result.segment_count}, tổng {result.duration_seconds:.1f} giây\n"
            f"Audio:\n{joined}{merged_line}{srt_line}"
        )
    srt_line = f"\nSRT: {result.srt_path}" if result.srt_path else ""
    return (
        f"Hoàn tất {result.segment_count} đoạn, {result.duration_seconds:.1f} giây\n"
        f"Audio: {result.audio_path}{srt_line}"
    )
