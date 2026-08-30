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
| `get_generation_contract` | Đọc capability, form động, giọng cố định và advanced fields |
| `list_voices` | Liệt kê preset cố định, profile clone và voice design |
| `start_text_generation` | Tạo job nền từ văn bản |
| `start_file_generation` | Tạo job nền từ 1–100 file TXT/MD/SRT |
| `get_job` | Đọc trạng thái, tiến độ, lỗi và kết quả |
| `list_jobs` | Đọc lịch sử job gần nhất |
| `cancel_job` | Hủy an toàn job queued/running |
| `retry_job` | Tạo job mới từ payload của job đã kết thúc |

Luồng khuyến nghị:

1. Gọi `list_models`.
2. Gọi `get_generation_contract` và `list_voices` cho model đã chọn.
3. Gọi một tool `start_*`, lưu `job_id`.
4. Poll `get_job` đến `succeeded`, `failed` hoặc `cancelled`.

## Ví dụ request text

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

## Chính sách an toàn và dữ liệu

- File nguồn phải là đường dẫn tuyệt đối, tồn tại, có đuôi TXT/MD/SRT, tối đa
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