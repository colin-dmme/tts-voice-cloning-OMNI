# Colin Studio TTS MCP server

`colin_studio_tts_mcp` là adapter MCP cục bộ cho Colin TTS Studio. Server dùng
stdio, trả về dữ liệu JSON có cấu trúc và không chứa thuật toán provider hay
logic giao diện.

## Kiến trúc

```text
MCP client / Desktop Coworker
        |
        v
colin_studio_tts_mcp
  - kiểm tra input và đường dẫn
  - SQLite job + progress/cancel/retry
        |
        v
AppController -> SafetyGate -> TtsService -> engine/worker
                         |
                         +-> khóa liên tiến trình dùng chung GUI/MCP
```

MCP gọi cùng `AppController`, `GenerationSettings`, model registry,
generation form, voice library và `TtsService` mà desktop app sử dụng.
Vì vậy capability, provider options, license, GPU safety, output naming,
split/merged, audio format và SRT không bị triển khai lại trong MCP hoặc GUI.

Cấu hình bảo vệ GPU được dùng chung qua `config/gpu_safety.json`. Nếu file
này chưa tồn tại, Core tự đọc ngưỡng đang có trong `config/ui_qt.json` (hoặc
`config/ui_tkinter.json`) để tương thích với bản cũ. Lần lưu tiếp theo từ GUI
sẽ tạo file dùng chung. Giá trị GPU gửi rõ trong `generation.advanced` của
một request MCP vẫn được ưu tiên cho riêng request đó.

## Cài và chạy

Yêu cầu Python 3.10–3.13 và `uv`.

```powershell
uv sync --extra mcp
uv run --frozen --extra mcp colin-studio-tts-mcp
```

stdout được dành riêng cho MCP framing; log Python đi ra stderr.

## Đăng ký Desktop Coworker

Cấu hình upstream trên Windows:

```json
{
  "id": "colin-studio-tts",
  "name": "Colin Studio TTS",
  "enabled": true,
  "transport": "stdio",
  "command": "C:\\Users\\chumi\\.local\\bin\\uv.exe",
  "args": [
    "run",
    "--frozen",
    "--extra",
    "mcp",
    "colin-studio-tts-mcp"
  ],
  "env": {},
  "cwd": "C:\\Coder\\tts-voice-cloning-OMNI",
  "tool_prefix": "tts",
  "expose": "all",
  "tools": [],
  "idle_timeout_sec": 3600
}
```

Desktop Coworker sẽ công bố tool dưới dạng `tts__health`,
`tts__list_models`, v.v. Trong protocol của server, tên gốc không có prefix.

## Tool

| Tool | Mục đích |
|---|---|
| `health` | Kiểm tra server, version, DB job và model đang resident |
| `list_models` | Tìm model, lọc provider hoặc chỉ model đã cài |
| `get_generation_contract` | Đọc capability, form động, giọng cố định, provider settings và advanced fields |
| `list_voices` | Liệt kê preset cố định, profile clone và voice design |
| `start_text_generation` | Tạo job nền từ văn bản |
| `start_file_generation` | Tạo job nền từ 1–100 file TXT/MD/SRT/EPUB; cấu hình sách qua `generation.epub` |
| `inspect_epub` | Xem trước EPUB và khoảng chương, không nạp model/sinh giọng |
| `preview_epub_reading` | So sánh bản gốc/bản đọc/thay đổi, đếm nguồn/URL và chỉ vị trí chữ Hán |
| `export_epub_reading` | Xuất TXT bản đọc, JSON báo cáo và nguồn MD theo bộ lọc, không tạo audio |
| `list_chapter_music` | Mô tả/tag nhạc, lọc theme/tag và danh sách chủ đề |
| `preview_chapter_music` | WAV nghe thử vừa nhịp hoặc `duration_mode=full_track` phát trọn bản, không gọi API |
| `import_chapter_music` | Thêm file nhạc riêng, trim/normalize và lấy tối đa 30 giây |
| `update_chapter_music_metadata` | Cập nhật tên/mô tả/chủ đề/tag, giữ nguyên audio và provenance |
| `list_chapter_music_presets` | Đọc các preset phối nhiều nhóm/bài, mô tả và danh sách loại trừ |
| `save_chapter_music_preset` | Tạo/cập nhật toàn bộ lựa chọn của preset cục bộ |
| `delete_chapter_music_preset` | Xóa preset, giữ nguyên file nhạc |
| `resolve_chapter_music_selection` | Xem tập bài thực sau hợp nhóm/bài, bỏ trùng và loại trừ |
| `plan_epub_music` | Xem trước từng nhịp, random theo nhóm/tập chọn/preset hoặc agent chỉ định |
| `plan_narrative_pacing` | Xem trước vị trí theme/nhạc chuyển theo cue SRT, không render |
| `pace_existing_audio` | Xếp nhịp lại audio + SRT đã có: nghỉ theo tầng, nhạc giao thoa, SRT/chapters mới |
| `describe_reading_rhythm` | Nhịp đọc cho một model: mỗi tầng nghỉ do model hay app làm, bị giới hạn hay không áp dụng, kèm lý do và tùy chọn riêng (giống nhãn trong Qt Studio). `get_generation_contract` cũng có khối `rhythm`; kết quả job có `rhythm_plan` |
| `get_job` | Đọc trạng thái, tiến độ, lỗi và kết quả |
| `list_jobs` | Đọc lịch sử job gần nhất |
| `cancel_job` | Hủy an toàn job queued/running |
| `retry_job` | Tạo job mới từ payload của job đã kết thúc |
| `colab_status` | Xem tài khoản, quyền Google, runtime và hàng đợi Colab tự động |
| `colab_configure` | Lưu tùy chọn Colab và import tệp OAuth Desktop |
| `colab_auth_start` | Tạo liên kết Google cho lần cấp quyền và chờ callback |
| `colab_auth_status` | Xem kết quả cấp quyền Google |
| `colab_control` | Tạm dừng, tiếp tục, hủy job hoặc trả runtime do Studio cấp |
| `cpu_worker_status` | Xem máy đã ghép, model đang công bố, trạng thái và hàng đợi CPU |
| `cpu_worker_control` | Ngừng nhận việc, tiếp tục, dừng máy hoặc bật tắt tham gia nhóm chia tải |
| `cpu_job_control` | Tạm dừng, tiếp tục hoặc hủy job CPU |

Khi bật Colab tự động, `generation.runtime_target="remote"` dùng hàng đợi chung
với Qt trong package [colin_colab_remote](C:/Coder/tts-voice-cloning-OMNI/src/colin_colab_remote/README.md).
Hai tool `start_*` nhận `idempotency_key` tùy chọn cho job Colab managed. Giữ
cùng khóa và yêu cầu để tra lại job sau khi mất phản hồi. Job có tiền tố `colab-`.
Trạng thái `waiting` giữ tiến độ và nêu `error_code` cần xử lý, dùng
`colab_control(action="resume", job_id=...)` hoặc `retry_job` để tiếp tục job đó.
Runtime và audio có trạng thái riêng, xem `colab_status` để xác nhận trả máy.

Với [CPU máy khác](C:/Coder/tts-voice-cloning-OMNI/src/colin_remote_compute/README.md), lấy `worker_profile_id` và model từ `cpu_worker_status`, rồi truyền lựa chọn đích trong `generation` của tool `start_*`.

```json
{
  "runtime_target": "remote",
  "remote_compute": {
    "kind": "existing_worker",
    "worker_profile_id": "<profile ID của máy đã ghép>",
    "backend": "cpu"
  }
}
```

Job CPU có tiền tố `cpu-job-`. Dùng `get_job` để theo dõi và `cpu_job_control(action="resume", job_id=...)` để tiếp tục sau khi xử lý lỗi. Có thể truyền `idempotency_key` vào tool `start_*` để tra lại yêu cầu sau khi mất kết nối.

Để chia một job qua nhiều máy, gửi `generation.remote_compute={"kind":"cpu_pool","backend":"cpu"}` với `generation.runtime_target="remote"`. Tab **Máy CPU** lưu các máy tham gia và giới hạn đồng thời. `cpu_worker_status` trả `pool_enabled` cho mỗi máy và `cpu_pool_limit` cho nhóm. `cpu_worker_control` dùng `include_pool` hoặc `exclude_pool` để thay đổi danh sách tham gia.

Luồng khuyến nghị:

1. Gọi `list_models`.
2. Gọi `get_generation_contract` và `list_voices` cho model đã chọn.
3. Gọi một tool `start_*`, lưu `job_id`.
4. Poll `get_job` đến `succeeded`, `failed` hoặc `cancelled`.

## Ví dụ request text

Với sách, dùng `inspect_epub` trước rồi `start_file_generation` với
`generation.epub`. Chọn nhạc qua `list_chapter_music`; thêm file mới bằng
`import_chapter_music` thay vì chỉ chép MP3 vào thư mục thư viện. Xem
[hướng dẫn EPUB, nhạc và SRT](epub-audiobooks.md) để có ví dụ request đầy đủ.
Xem [tập chọn, preset, catalog và lựa chọn theo nội dung](music-library.md)
cho `selection_mode`, `theme_ids`, `track_ids`, `excluded_track_ids`, `preset_id`,
`random_seed`, `track_overrides` và `music_plan_path`.

Từ 0.6.5, `generation.epub.content` quản lý lọc nguồn, URL, ghi chú và chữ Hán.
Gọi `preview_epub_reading` trước khi sinh giọng; tool trả bản gốc/bản đọc của
`chapter_index`, các thay đổi và `han_issues` theo vị trí. `inspect_epub` nhận
`epub` đầy đủ; `chapter_start/chapter_end` gửi riêng sẽ ghi đè khoảng chương
trong `epub`. Chỉ số chương giữ vị trí trong sách gốc sau khi loại một số phần.

`export_epub_reading(source_file, output_directory, epub)` xuất tài liệu trước
khi tạo audio. `output_directory` phải tuyệt đối và không phải root ổ đĩa.
Job EPUB tự xuất cùng tài liệu, trả `reading_text_path`, `reading_report_path`,
`references_path`. Xem [schema, mặc định và ví dụ](epub-content-filter.md).

`save_chapter_music_preset` nhận tên và toàn bộ tập chọn; khi cập nhật phải gửi
`preset_id` cùng các danh sách muốn lưu. Danh sách bỏ qua được coi là rỗng,
không phải cập nhật một phần. Preset chỉ quản lý nguồn bài: thời lượng, fade,
âm lượng và các vị trí phát vẫn thuộc request tạo sách. Kế hoạch đang chạy
giữ các ID nhạc đã chọn kể cả khi preset được sửa/xóa.

```json
{
  "request": {
    "text": "Xin chào, đây là Colin TTS Studio.",
    "model_id": "omnivoice_vietnamese",
    "voice": {
      "mode": "fixed",
      "voice_id": null
    },
    "output": {
      "directory": "C:\\TTS Output",
      "stem": "demo-mcp",
      "mode": "merged",
      "audio_format": "wav",
      "create_srt": true
    },
    "generation": {
      "language": "vi",
      "runtime_target": "auto",
      "speed": 1.0,
      "provider_options": {},
      "advanced": {
        "sentence_pause_ms": 320
      }
    }
  }
}
```

Ba kiểu voice:

- `fixed`: `voice_id` là preset/speaker ID; có thể null nếu model không bắt buộc.
- `profile`: `voice_id` là profile ID đã lưu; bắt buộc.
- `design`: `voice_id` là designed voice ID đã lưu; bắt buộc.

MCP không hardcode tham số riêng của provider. Ví dụ với
`zerotts_202m_gguf_q8_0`, hãy đọc `provider_settings` từ
`get_generation_contract`, rồi gửi các giá trị cần đổi trong
`generation.provider_options`:

```json
{
  "request": {
    "text": "Ngày 13/09/2026, ZeroTTS được gọi qua MCP.",
    "model_id": "zerotts_202m_gguf_q8_0",
    "voice": {"mode": "fixed", "voice_id": "maichi"},
    "generation": {
      "language": "vi",
      "runtime_target": "cpu",
      "provider_options": {
        "normalize_vi_text": true,
        "audio_temperature": 0.8,
        "audio_topk": 25,
        "audio_topp": 0.95,
        "streaming_decoder": true,
        "intra_op_num_threads": 4
      }
    }
  }
}
```

Provider ZeroTTS hiện trả bốn model: ONNX, GGUF F32, GGUF Q8_0 và GGUF Q4_0.
Contract ONNX có 22 setting. Mỗi contract GGUF có 20 setting và không nhận
`cfg_scale` hoặc `warmup`, đúng giới hạn runtime C++ upstream.

## Chính sách an toàn và dữ liệu

- File nguồn phải là đường dẫn tuyệt đối, tồn tại, có đuôi TXT/MD/SRT/EPUB, tối đa
  20 MB/file và 100 file/job.
- Output directory phải tuyệt đối và không được là root của ổ đĩa.
- MCP luôn đặt `overwrite=false`; Core tự chọn tên trống nếu file đã tồn tại.
- MCP không nhận đường dẫn audio clone tùy ý. Agent phải dùng profile ID đã được
  ứng dụng quản lý.
- API key từ xa không đi trong request MCP; Core chỉ đọc biến môi trường đã cấu hình.
- SQLite `config/mcp_jobs.sqlite3` lưu payload để retry. Kết quả public chỉ trả
  preview text ngắn, nhưng DB là dữ liệu cục bộ và vẫn có thể chứa toàn văn.
- Job queued/running còn dở khi server khởi động lại được đánh dấu
  `interrupted`, sau đó có thể dùng `retry_job`.

## Kiểm tra

```powershell
uv run --extra mcp python -m unittest tests.test_colin_studio_tts_mcp -v
uv run --extra mcp python -m unittest discover -s tests -q
```
