"""Colin Studio TTS MCP server over local stdio."""

from __future__ import annotations

import logging
import sys
from dataclasses import asdict
from importlib.metadata import PackageNotFoundError, version
from typing import Any

from mcp.server import MCPServer

from .contracts import (
    FileGenerationInput,
    TextGenerationInput,
    advanced_setting_fields,
)
from .runtime import McpRuntime


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
        "version": package_version,
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
        "advanced_fields": advanced_setting_fields(),
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
def start_text_generation(request: TextGenerationInput) -> dict[str, Any]:
    """Xếp tác vụ tạo giọng từ văn bản và trả job_id ngay."""
    runtime.controller.service.registry.get(request.model_id)
    return runtime.jobs.start_text(request)


@mcp.tool()
def start_file_generation(request: FileGenerationInput) -> dict[str, Any]:
    """Xếp tác vụ tạo giọng từ tối đa 100 file TXT, Markdown hoặc SRT."""
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
