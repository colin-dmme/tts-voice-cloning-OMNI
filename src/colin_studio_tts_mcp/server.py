"""Colin Studio TTS MCP server over local stdio."""

from __future__ import annotations

import logging
import sys
from dataclasses import asdict
from importlib.metadata import PackageNotFoundError, version
from typing import Any
from pathlib import Path

from mcp.server import MCPServer

from .contracts import (
    FileGenerationInput,
    TextGenerationInput,
    advanced_setting_fields,
)
from .runtime import McpRuntime
from . import __version__
from omni_tts_shared.epub import EpubOptions
from omni_tts_core.text.epub_reader import read_epub
from omni_tts_core.chapter_music import ChapterMusicLibrary, preview_chapter_music as render_chapter_music_preview

# stdout belongs exclusively to the stdio protocol.
logging.basicConfig(stream=sys.stderr, level=logging.INFO)

mcp = MCPServer(
    "Colin Studio TTS",
    instructions=(
        "Điều khiển Colin TTS Studio cục bộ. Hãy gọi list_models và "
        "get_generation_contract trước khi tạo giọng. Các lệnh tạo giọng chạy "
        "nền; dùng get_job để theo dõi."
    ),
)
runtime = McpRuntime()


@mcp.tool()
def health() -> dict[str, Any]:
    """Kiểm tra server và runtime Colin TTS mà không nạp model TTS."""
    controller = runtime.controller
    try:
        package_version = version("omni-tts-local")
    except PackageNotFoundError:
        package_version = controller.service.settings.app_version or "unknown"
    return {
        "status": "ok",
        "server": "colin_studio_tts_mcp",
        "version": __version__,
        "installed_distribution_version": package_version,
        "project_root": str(controller.service.settings.project_root),
        "job_database": str(runtime.database_path),
        "active_jobs": runtime.jobs.active_count(),
        "resident_models": controller.resident_models(),
    }


@mcp.tool()
def list_models(
    query: str = "",
    provider_id: str | None = None,
    installed_only: bool = False,
) -> dict[str, Any]:
    """Liệt kê model TTS cùng trạng thái cài đặt và runtime thực tế."""
    needle = query.strip().casefold()
    items: list[dict[str, Any]] = []
    for status in runtime.controller.service.list_tts_models():
        data = status.model_dump(mode="json")
        searchable = " ".join(str(value) for value in data.values()).casefold()
        if needle and needle not in searchable:
            continue
        if provider_id and data.get("provider") != provider_id:
            continue
        if installed_only and not data.get("installed"):
            continue
        items.append(data)
    return {"count": len(items), "models": items}


@mcp.tool()
def get_generation_contract(model_id: str) -> dict[str, Any]:
    """Đọc capability, form động và giọng cố định của model từ core."""
    service = runtime.controller.service
    descriptor = service.generation_form_descriptor(model_id)
    policy = runtime.controller.control_policy(model_id)
    return {
        "model_id": model_id,
        "provider": service.model_provider(model_id),
        "capabilities": service.model_capabilities(model_id).model_dump(mode="json"),
        "form": descriptor.model_dump(mode="json"),
        "fixed_voices": [
            {"label": label, "voice_id": voice_id}
            for label, voice_id in service.list_voice_presets(
                model_id, include_none=False
            )
            if voice_id
        ],
        "provider_settings": [asdict(setting) for setting in policy.provider_settings],
        "advanced_fields": advanced_setting_fields(),
        "source_formats": ["txt", "md", "srt", "epub"],
        "epub_options_schema": EpubOptions.model_json_schema(),
        "epub_defaults": EpubOptions().model_dump(),
        "epub_note": "Gửi generation.epub trong start_file_generation. Khoảng nghỉ chèn ở audio, SRT dùng cùng timeline; output.mode tách đoạn không áp dụng cho EPUB.",
    }


@mcp.tool()
def list_voices(
    model_id: str,
    query: str = "",
    project: str | None = None,
    tag: str | None = None,
) -> dict[str, Any]:
    """Liệt kê giọng cố định, profile clone và voice design dùng được."""
    service = runtime.controller.service
    fixed = [
        {"voice_id": voice_id, "name": label, "mode": "fixed"}
        for label, voice_id in service.list_voice_presets(
            model_id, include_none=False
        )
        if voice_id
        if not query or query.casefold() in f"{label} {voice_id}".casefold()
    ]
    library = [
        {
            **asdict(item),
            "tags": list(item.tags),
            "voice_id": item.item_id,
            "mode": "profile" if item.kind == "clone" else "design",
        }
        for item in service.selectable_voice_items(
            model_id, query=query, project=project, tag=tag
        )
    ]
    return {"count": len(fixed) + len(library), "voices": fixed + library}


@mcp.tool()
def list_chapter_music() -> dict[str, Any]:
    """Liệt kê thư viện nhạc cục bộ để chọn generation.epub.music.track_id; không gọi provider."""
    tracks = ChapterMusicLibrary().list_tracks()
    return {"count": len(tracks), "tracks": [asdict(t) for t in tracks]}


@mcp.tool()
def preview_chapter_music(track_id: str, duration_ms: int = 2500, volume_percent: int = 30,
                          fade_in_ms: int = 120, fade_out_ms: int = 350) -> dict[str, Any]:
    """Tạo WAV nghe thử nhạc đã trim/fade vừa nhịp nghỉ. Không tạo nhạc mới, không nạp TTS."""
    path = render_chapter_music_preview(track_id, duration_ms=duration_ms, volume_percent=volume_percent,
                                       fade_in_ms=fade_in_ms, fade_out_ms=fade_out_ms)
    return {"track_id": track_id, "duration_ms": duration_ms, "audio_path": str(path)}


@mcp.tool()
def import_chapter_music(source_file: str, name: str) -> dict[str, Any]:
    """Thêm audio người dùng có sẵn vào thư viện riêng; tự trim/normalize, tối đa 30 giây, không tải mạng."""
    track = ChapterMusicLibrary().import_track(Path(source_file), name, provenance={"provider": "user_import"})
    return asdict(track)


@mcp.tool()
def start_text_generation(request: TextGenerationInput) -> dict[str, Any]:
    """Xếp tác vụ tạo giọng từ văn bản và trả job_id ngay."""
    runtime.controller.service.registry.get(request.model_id)
    return runtime.jobs.start_text(request)


@mcp.tool()
def inspect_epub(source_file: str, chapter_start: int = 1, chapter_end: int = 0, limit: int = 50) -> dict[str, Any]:
    """Xem cấu trúc, tên và chữ đầu các chương EPUB; không sinh giọng hoặc nạp model. Chương là vị trí 1-based, end=0 đọc hết."""
    path = Path(source_file)
    if not path.is_absolute() or path.suffix.lower() != ".epub" or not path.is_file():
        raise ValueError("source_file phải là đường dẫn tuyệt đối tới EPUB có sẵn.")
    if path.stat().st_size > 20 * 1024 * 1024:
        raise ValueError("EPUB vượt giới hạn 20 MB của MCP.")
    return read_epub(path).preview(EpubOptions(chapter_start=chapter_start, chapter_end=chapter_end), limit=limit)


@mcp.tool()
def start_file_generation(request: FileGenerationInput) -> dict[str, Any]:
    """Xếp tác vụ từ tối đa 100 file TXT/MD/SRT/EPUB. EPUB dùng generation.epub, có audio và SRT theo chương hoặc bản ghép."""
    runtime.controller.service.registry.get(request.model_id)
    return runtime.jobs.start_files(request)


@mcp.tool()
def get_job(job_id: str) -> dict[str, Any]:
    """Đọc tiến độ, lỗi và đường dẫn kết quả của một MCP job."""
    return runtime.jobs.get(job_id)


@mcp.tool()
def list_jobs(limit: int = 20, status: str | None = None) -> dict[str, Any]:
    """Liệt kê lịch sử MCP job gần nhất, tối đa 100 bản ghi."""
    return runtime.jobs.list(limit, status)


@mcp.tool()
def cancel_job(job_id: str) -> dict[str, Any]:
    """Yêu cầu hủy an toàn một job đang xếp hàng hoặc đang chạy."""
    return runtime.jobs.cancel(job_id)


@mcp.tool()
def retry_job(job_id: str) -> dict[str, Any]:
    """Tạo job mới từ payload đã kiểm tra của một job đã kết thúc."""
    return runtime.jobs.retry(job_id)


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
