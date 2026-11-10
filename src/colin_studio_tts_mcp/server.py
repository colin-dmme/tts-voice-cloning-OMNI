"""Colin Studio TTS MCP server over local stdio."""

from __future__ import annotations

import hashlib
import logging
import sys
from dataclasses import asdict
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any, Literal

import soundfile as sf
from mcp.server import MCPServer

from omni_tts_core.chapter_music import ChapterMusicLibrary
from omni_tts_core.chapter_music import (
    preview_chapter_music as render_chapter_music_preview,
)
from omni_tts_core.text.epub_reader import read_epub
from omni_tts_shared.epub import ChapterMusicOptions, EpubOptions, MusicDurationMode
from omni_tts_shared.narrative_pacing import NarrativePacingOptions

from . import __version__
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
from colin_colab_remote.mcp_tools import register_tools as register_colab_tools
register_colab_tools(mcp)
from colin_remote_compute.mcp_tools import register_tools as register_cpu_tools
register_cpu_tools(mcp)


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
        "pacing_options_schema": NarrativePacingOptions.model_json_schema(),
        "pacing_note": (
            "generation.pacing = Nhịp đọc. enabled=true; scope='pacing_only' giữ ngắt nghỉ cũ và chỉ giãn "
            "thêm, scope='full' để Nhịp đọc quản lý mọi tầng (mỗi tầng đúng một bên làm). Giá trị là tổng "
            "khoảng lặng nghe thấy (ms); layer_ranges={tầng:[min,max]} cho dao động. model_switches cho tùy "
            "chọn riêng của model (xem rhythm.switches). TXT/MD/SRT ghép: đủ tầng và nhạc chuyển; xuất tách: "
            "chỉ tầng trong câu; EPUB: tầng trong câu và giữa đoạn, chương/cảnh/nhạc chương do generation.epub "
            "quản lý. Hook đầu luôn để trơn. Dùng describe_reading_rhythm để biết tầng nào model làm, tầng nào "
            "app làm hoặc bị giới hạn; plan_narrative_pacing để xem trước vị trí nhạc."
        ),
        "rhythm": _rhythm_view(model_id, NarrativePacingOptions(enabled=True, scope="full")).as_dict(),
    }


def _rhythm_view(model_id: str, pacing: NarrativePacingOptions, **context: Any):
    from omni_tts_core.ui_presenters.rhythm_presenter import rhythm_view
    spec = runtime.controller.service.registry.get(model_id)
    return rhythm_view(pacing, spec, **context)


@mcp.tool()
def describe_reading_rhythm(
    model_id: str,
    pacing: NarrativePacingOptions | None = None,
    output_mode: Literal["merged", "split"] = "merged",
    source_kind: Literal["text", "epub"] = "text",
    chunk_join_mode: Literal["auto", "crossfade", "direct", "silence"] = "auto",
    runtime_target: str | None = None,
) -> dict[str, Any]:
    """Nhịp đọc cho một model: mỗi tầng nghỉ do ai làm và vì sao (giống nhãn trong Qt Studio).

    state: model (thư viện/token của model), app (app cắt câu hoặc giãn lặng), model_app_topup (model
    có mức riêng, app chỉ bù), limited (chỉ làm được một phần, xem reason), not_applicable, off.
    Không có pacing thì xem với Nhịp đọc bật, phạm vi 'full'. Gọi trước khi gửi generation.pacing để
    chỉ chỉnh những tầng model/app thực sự làm được."""
    options = pacing or NarrativePacingOptions(enabled=True, scope="full")
    return _rhythm_view(model_id, options, output_mode=output_mode, source_kind=source_kind,
                        chunk_join_mode=chunk_join_mode, runtime_target=runtime_target).as_dict()


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
def list_chapter_music(theme: str | None = None, tag: str | None = None) -> dict[str, Any]:
    """Đọc mô tả/tag và lọc chủ đề nhạc để agent chọn fixed/random_theme; không gọi provider."""
    library = ChapterMusicLibrary()
    tracks = library.list_tracks(theme=theme, tag=tag)
    return {"count": len(tracks), "tracks": [asdict(t) for t in tracks],
            "themes": library.list_themes(), "catalog_path": str(library.catalog),
            "description_path": str(library.root / "MUSIC_CATALOG.md")}


@mcp.tool()
def preview_chapter_music(track_id: str, duration_ms: int = 2500, volume_percent: int = 30,
                          fade_in_ms: int = 120, fade_out_ms: int = 350,
                          duration_mode: MusicDurationMode = "fit_pause") -> dict[str, Any]:
    """Nghe nhạc vừa nhịp nghỉ hoặc full_track phát trọn bản trong thư viện. Không tạo nhạc mới/nạp TTS."""
    path = render_chapter_music_preview(track_id, duration_ms=duration_ms, volume_percent=volume_percent,
                                       fade_in_ms=fade_in_ms, fade_out_ms=fade_out_ms, duration_mode=duration_mode)
    info = sf.info(path)
    return {"track_id": track_id, "duration_ms": info.frames / info.samplerate * 1000,
            "duration_mode": duration_mode, "audio_path": str(path)}


@mcp.tool()
def import_chapter_music(source_file: str, name: str, description: str = "",
                         themes: list[str] | None = None, tags: list[str] | None = None) -> dict[str, Any]:
    """Thêm audio người dùng có sẵn vào thư viện riêng; tự trim/normalize, tối đa 30 giây, không tải mạng."""
    track = ChapterMusicLibrary().import_track(Path(source_file), name, description=description,
        themes=themes, tags=tags, provenance={"provider": "user_import"})
    return asdict(track)


@mcp.tool()
def update_chapter_music_metadata(track_id: str, description: str | None = None,
                                  themes: list[str] | None = None, tags: list[str] | None = None,
                                  name: str | None = None) -> dict[str, Any]:
    """Cập nhật mô tả, chủ đề và tag của nhạc cục bộ; giữ nguyên file âm thanh và nguồn/quyền đã ghi."""
    return asdict(ChapterMusicLibrary().update_metadata(track_id, name=name, description=description, themes=themes, tags=tags))


@mcp.tool()
def list_chapter_music_presets() -> dict[str,Any]:
    """Đọc các preset phối nhiều chủ đề/bài nhạc và các bài bị loại; không nạp TTS."""
    from omni_tts_core.music_presets import MusicPresetStore
    store=MusicPresetStore();items=store.list_presets()
    return {'count':len(items),'presets':[p.model_dump() for p in items],'path':str(store.path)}


@mcp.tool()
def save_chapter_music_preset(name: str,theme_ids: list[str] | None=None,track_ids: list[str] | None=None,
                              excluded_track_ids: list[str] | None=None,description: str='',preset_id: str | None=None) -> dict[str,Any]:
    """Tạo/thay toàn bộ preset: hợp nhóm và bài riêng, trừ bài loại, bỏ trùng.

    Cập nhật dùng preset_id đã đọc và gửi toàn bộ các danh sách muốn giữ;
    danh sách bỏ qua được coi là rỗng. Preset không chứa thời lượng/fade.
    """
    from omni_tts_core.music_presets import MusicPresetStore
    return MusicPresetStore().save(name,preset_id=preset_id,description=description,
        theme_ids=theme_ids,track_ids=track_ids,excluded_track_ids=excluded_track_ids).model_dump()


@mcp.tool()
def delete_chapter_music_preset(preset_id: str) -> dict[str,Any]:
    """Chỉ xóa preset cục bộ, giữ nguyên audio; không đổi kế hoạch sách đang tạo."""
    from omni_tts_core.music_presets import MusicPresetStore
    return {'preset_id':preset_id,'deleted':MusicPresetStore().delete(preset_id)}


@mcp.tool()
def resolve_chapter_music_selection(music: ChapterMusicOptions) -> dict[str,Any]:
    """Xem chính xác tập random sau khi phối nhóm/bài, bỏ trùng và áp dụng loại trừ/preset; không tạo audio."""
    from omni_tts_core.chapter_music import ChapterMusicSelector
    selector=ChapterMusicSelector(music)
    return {'selection_mode':music.selection_mode,'count':len(selector.pool),
        'tracks':[asdict(t) for t in selector.pool],
        'preset':selector.preset.model_dump() if selector.preset else None}


@mcp.tool()
def plan_epub_music(source_file: str, epub: EpubOptions | None = None) -> dict[str, Any]:
    """Xem trước từng lựa chọn nhạc title:N/chapter:N; cùng seed và EPUB cho cùng kế hoạch, không tạo giọng.

    Agent có thể đọc mô tả rồi dùng epub.music.track_overrides để gắn track_id theo nội dung.
    Chỉ chèn nhạc trong khoảng nghỉ, chưa có nhạc nền dưới lời kể.
    """
    from omni_tts_core.epub_generation import build_epub_music_plan
    path = Path(source_file)
    if not path.is_absolute() or path.suffix.lower() != ".epub" or not path.is_file():
        raise ValueError("source_file phải là đường dẫn tuyệt đối tới EPUB có sẵn.")
    if path.stat().st_size > 20 * 1024 * 1024:
        raise ValueError("EPUB vượt giới hạn 20 MB của MCP.")
    return build_epub_music_plan(read_epub(path), epub or EpubOptions(), hashlib.sha256(path.read_bytes()).hexdigest())


def _absolute_file(value: str, suffixes: set[str], label: str) -> Path:
    path = Path(value)
    if not path.is_absolute() or not path.is_file() or path.suffix.lower() not in suffixes:
        raise ValueError(f"{label} phải là đường dẫn tuyệt đối tới file {'/'.join(sorted(suffixes))} có sẵn.")
    return path


@mcp.tool()
def plan_narrative_pacing(srt_file: str, pacing: NarrativePacingOptions | None = None,
                          language: str = "vi") -> dict[str, Any]:
    """Xem trước cấu trúc nhịp theo các cue SRT (mỗi cue coi là một đoạn): theme, nhạc chuyển ngắn/dài và chỗ
    lặng dài khi chuyển mục; không đọc audio, không render.

    Muốn tự đặt theo nội dung: pacing.music.bridge_before_units (nhạc), pacing.music.major_before_units (nhạc
    dài) và pacing.section_before_units
    (lặng chuyển mục), số đoạn bắt đầu từ 2."""
    from omni_tts_core.narrative_pacing.existing_output_repacer import read_srt_units
    from omni_tts_core.narrative_pacing.section_planner import plan_structure
    units = read_srt_units(_absolute_file(srt_file, {".srt"}, "srt_file"))
    options = pacing or NarrativePacingOptions()
    plan = plan_structure(units, options, language)
    entries = ([("theme", plan.music.intro_before)] if plan.music.intro_before is not None else []) + [
        ("bridge_long" if b in plan.music.majors_before else "bridge_short", b)
        for b in plan.music.bridges_before] if options.music.enabled else []
    entries += [("section", b) for b in plan.sections]
    return {"unit_count": len(units), "music_enabled": options.music.enabled, "entries": [
        {"kind": kind, "before_unit": b + 1, "at_seconds": units[b].start, "topic_score": plan.scores[b],
         "text": units[b].text[:120]}
        for kind, b in sorted(entries, key=lambda e: e[1])]}


@mcp.tool()
def pace_existing_audio(audio_file: str, srt_file: str, pacing: NarrativePacingOptions | None = None,
                        output_directory: str | None = None, language: str = "vi") -> dict[str, Any]:
    """Xếp nhịp lại audio đã tạo (WAV/MP3) theo SRT đi kèm: nghỉ theo tầng, nhạc chuyển giao thoa, SRT/chapters mới.

    Chạy đồng bộ; file 2 giờ mất khoảng 1 phút. Ghi vào output_directory hoặc thư mục 'paced' cạnh audio."""
    from omni_tts_core.narrative_pacing import repace_existing_output
    out = None
    if output_directory:
        out = Path(output_directory)
        if not out.is_absolute():
            raise ValueError("output_directory phải là đường dẫn tuyệt đối.")
    return repace_existing_output(
        _absolute_file(audio_file, {".wav", ".mp3", ".flac"}, "audio_file"),
        _absolute_file(srt_file, {".srt"}, "srt_file"),
        pacing or NarrativePacingOptions(enabled=True), output_dir=out, language=language)


@mcp.tool()
def start_text_generation(request: TextGenerationInput) -> dict[str, Any]:
    """Xếp tác vụ tạo giọng từ văn bản và trả job_id ngay."""
    runtime.controller.service.registry.get(request.model_id)
    return runtime.jobs.start_text(request)


@mcp.tool()
def inspect_epub(source_file: str, chapter_start: int | None = None, chapter_end: int | None = None, limit: int = 50, epub: EpubOptions | None = None) -> dict[str, Any]:
    """Xem cấu trúc, tên và chữ đầu các chương EPUB; không sinh giọng hoặc nạp model. Chương là vị trí 1-based, end=0 đọc hết."""
    path = Path(source_file)
    if not path.is_absolute() or path.suffix.lower() != ".epub" or not path.is_file():
        raise ValueError("source_file phải là đường dẫn tuyệt đối tới EPUB có sẵn.")
    if path.stat().st_size > 20 * 1024 * 1024:
        raise ValueError("EPUB vượt giới hạn 20 MB của MCP.")
    options = epub or EpubOptions()
    overrides = {k: v for k, v in {"chapter_start": chapter_start, "chapter_end": chapter_end}.items() if v is not None}
    options = EpubOptions.model_validate({**options.model_dump(), **overrides})
    return read_epub(path).preview(options, limit=limit)


def _reading_plan(source_file, epub):
    from omni_tts_core.text.epub_content import prepare_epub

    path = Path(source_file)
    if not path.is_absolute() or path.suffix.lower() != ".epub" or not path.is_file():
        raise ValueError("source_file phải là đường dẫn tuyệt đối tới EPUB có sẵn.")
    if path.stat().st_size > 20 * 1024 * 1024:
        raise ValueError("EPUB vượt giới hạn 20 MB của MCP.")
    return path, prepare_epub(read_epub(path), epub or EpubOptions())


@mcp.tool()
def preview_epub_reading(source_file: str, epub: EpubOptions | None = None, chapter_index: int = 1, max_characters: int = 16000) -> dict[str, Any]:
    """So sánh bản gốc/bản đọc/đã bỏ, thống kê nguồn, URL và chữ Hán; không nạp model hoặc mở URL.

    generation.epub.content dùng đúng cấu hình này khi tạo audio/SRT. Số chương giữ vị trí trong EPUB gốc.
    """
    if not 1 <= chapter_index <= 100000 or not 100 <= max_characters <= 50000:
        raise ValueError("chapter_index: 1–100000; max_characters: 100–50000.")
    _path, plan = _reading_plan(source_file, epub)
    return {**plan.report(), "chapter": plan.chapter_preview(chapter_index, max_characters)}


@mcp.tool()
def export_epub_reading(source_file: str, output_directory: str, epub: EpubOptions | None = None) -> dict[str, Any]:
    """Xuất TXT bản đọc, JSON báo cáo lọc và nguồn MD theo content; không tạo audio, giữ EPUB gốc."""
    from omni_tts_core.text.epub_content import export_reading_plan
    from omni_tts_core.text.output_naming import slug_component

    directory = Path(output_directory)
    if not directory.is_absolute() or directory == Path(directory.anchor):
        raise ValueError("Thư mục đầu ra phải tuyệt đối và không phải root của ổ đĩa.")
    path, plan = _reading_plan(source_file, epub)
    if not plan.chapters:
        raise ValueError("Không còn nội dung sau khi lọc; hãy đổi phạm vi / tùy chọn.")
    paths = export_reading_plan(plan, directory, slug_component(path.stem)[:100] or "epub", hashlib.sha256(path.read_bytes()).hexdigest())
    return {**plan.report(), "files": {k: str(v) for k, v in paths.items()}}


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
