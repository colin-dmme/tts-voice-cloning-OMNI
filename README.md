# Colin TTS Local v0.1.0

App TTS local ưu tiên tiếng Việt, có lõi tách khỏi giao diện để sau này đổi Gradio sang CustomTkinter, PyQt6 hoặc giao diện khác mà không phải viết lại logic model.

## Mục tiêu thiết kế

- Model nằm trong thư mục dự án tại `models/`.
- Quản lý môi trường bằng `uv`.
- UI không gọi trực tiếp OmniVoice.
- Core xử lý model, chia câu, chuẩn hóa text, sinh audio và tạo SRT.
- Mỗi file source nên nhỏ, giới hạn kiểm tra là 700 dòng.

## Chạy app

Chạy 1-click cho máy làm việc hoặc máy thuê:

```bat
Start-ColinTTS.bat
```

Đây là file chính cần bấm sau khi clone repo sang máy khác. File này tự chuẩn bị môi trường `uv`, pull source mới nhất nếu có Git, restore `user_state/` vào profile/setting runtime rồi mở giao diện Tkinter.
Sau lần chạy đầu, script cũng tạo shortcut `Colin TTS Local` ngoài Desktop để mở lại nhanh.

Nếu máy thuê chưa có source, chạy bootstrap từ GitHub bằng PowerShell:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://raw.githubusercontent.com/colin-dmme/tts-voice-cloning-OMNI/main/scripts/install_from_github.ps1 | iex"
```

Nếu máy thuê là Docker GPU Linux, mở container template `pytorch`, expose port `7860`, rồi chạy:

```bash
git clone https://github.com/colin-dmme/tts-voice-cloning-OMNI.git
cd tts-voice-cloning-OMNI
bash Start-ColinTTS-Docker-GPU.sh
```

Sau đó mở URL port `7860` do nhà cung cấp cloud hiển thị. Xem thêm `docs/docker_gpu_webui.md`.

Chạy giao diện web Gradio bằng cùng launcher chính:

```bat
Start-ColinTTS.bat -Web
```

Các file `run_app.bat` và `run_tkinter.bat` chỉ giữ lại cho dev/debug. Khi dùng hằng ngày hoặc sang máy mới, ưu tiên `Start-ColinTTS.bat`.

Chạy giao diện Tkinter thủ công trong lúc debug:

```bat
run_tkinter.bat
```

Nếu muốn dừng app đang chạy nền:

```bat
stop_app.bat
```

Hoặc chạy thủ công:

```bat
uv sync
uv run omni-tts-gradio
```

`run_app.bat` dùng `uv sync --inexact` để không gỡ các thư viện TTS optional đã cài trước đó.

## Cài thêm engine TTS

Bản UI và quản lý model chạy với nhóm thư viện nhẹ. Khi muốn dùng model nào, mở tab `Quản lý model`, chọn model đó rồi dùng các nút:

- `Tải model`: tải payload/cache cần cho model.
- `Cài worker/môi trường`: cài worker riêng hoặc thư viện TTS chính.
- `Cài GPU/CUDA`: cài bộ tăng tốc CUDA phù hợp với provider/model.

Các file `install_*.bat` vẫn tồn tại để core chạy đúng tác vụ trên Windows, nhưng không cần bấm trực tiếp khi dùng app. VieNeu, Qwen, Valtec, F5-TTS và Chatterbox chạy trong worker riêng dưới `engines/`, tách khỏi môi trường chính để tránh xung đột dependency với OmniVoice.

## Quy ước model local

Model được khai báo trong `config/models.yaml` và tải về `models/`:

```text
models/
  omnivoice/
    vietnamese/
    base/
  tokenizer/
  asr/
```

App sẽ ưu tiên load model từ đường dẫn local trong dự án.
VieNeu dùng worker riêng và cache Hugging Face chung trong `.hf_cache/`.

## Giao diện Tkinter

Source code nằm riêng trong `src/omni_tts_ui_tkinter/` và chỉ gọi core qua controller. Giao diện này hỗ trợ:

- Tiếng Việt trên toàn bộ UI.
- Tạo audio từ văn bản nhập trực tiếp.
- Kéo thả hoặc chọn nhiều file nguồn `.txt`, `.md`, `.srt`.
- Mặc định xuất WAV/SRT cùng thư mục với file nguồn và dùng tên file nguồn.
- Có thể chọn thư mục xuất riêng.
- Có checkbox `Tách dòng SRT/đoạn văn thành file riêng`, mặc định bật và Tkinter sẽ nhớ trạng thái cho lần mở sau.
- Quản lý profile giọng trong tab `Profile giọng`, lưu theo tên, dự án, transcript và ghi chú.
- Quản lý model và tải các model bắt buộc còn thiếu.

Khi bật chế độ tách file, `.srt` sẽ xuất mỗi cue/dòng subtitle thành một cặp file riêng như `tenfile_001.wav` và `tenfile_001.srt`. Nếu nhập văn bản trực tiếp, mỗi đoạn cách nhau bằng một dòng trống sẽ thành một file audio riêng. `Nghỉ giữa câu/chunk` áp dụng bên trong đoạn dài bị chia nhỏ; `Nghỉ giữa đoạn trong file tổng` áp dụng giữa các đoạn gốc khi xuất một file liền mạch, nối thêm file tổng, hoặc tạo SRT timeline.

Profile giọng được lưu trong `voices/profiles/`, còn file audio mẫu được copy vào `voices/samples/`. Các giao diện chỉ chọn `profile_id`; core sẽ tự lấy file giọng mẫu và transcript khi tạo audio.

Cache Hugging Face cũng được trỏ về `.hf_cache/` khi chạy qua các file `.bat`, để dữ liệu không bị rải sang cache hệ thống.

## Đồng bộ máy thuê

Máy chính là nguồn chuẩn cho profile giọng và setting dùng chung. Khi muốn đưa state hiện tại lên GitHub:

```bat
Sync-State-To-Git.bat
```

Script này export `voices/profiles`, `voices/samples` và các setting UI portable vào `user_state/`, commit riêng phần state đó rồi push lên branch hiện tại. Trên máy thuê mới, `Start-ColinTTS.bat` sẽ restore `user_state/` trước khi mở app. Model, cache tải model, output và license vẫn không đưa vào Git.

Nếu dùng GTX 1080 Ti, chạy:

```bat
install_tts_deps_cuda126.bat
```

Thông thường bạn có thể bấm `Cài GPU/CUDA` trong tab `Quản lý model`. Lệnh thủ công này chỉ còn dùng khi debug hoặc cần cài trực tiếp ngoài app; nó cài nhóm TTS rồi ép cài lại `torch==2.7.1+cu126` và `torchaudio==2.7.1+cu126`, phù hợp hơn với GTX 1080 Ti.

Nếu dùng RTX 50xx/5090 Blackwell và gặp lỗi `CUDA capability sm_120` hoặc `no kernel image is available`, chạy:

```bat
Fix-RTX50-CUDA.bat
```

Với source checkout có thể cài riêng Qwen worker Blackwell bằng:

```bat
install_qwen_worker_blackwell.bat
```
