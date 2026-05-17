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

File này tự chuẩn bị môi trường `uv`, pull source mới nhất nếu có Git, restore `user_state/` vào profile/setting runtime rồi mở giao diện Tkinter.
Sau lần chạy đầu, script cũng tạo shortcut `Colin TTS Local` ngoài Desktop để mở lại nhanh.

Nếu máy thuê chưa có source, chạy bootstrap từ GitHub bằng PowerShell:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://raw.githubusercontent.com/colin-dmme/tts-voice-cloning-OMNI/main/scripts/install_from_github.ps1 | iex"
```

Chạy giao diện web Gradio:

```bat
run_app.bat
```

Chạy giao diện Tkinter:

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

Bản UI và quản lý model chạy với nhóm thư viện nhẹ. Để sinh audio bằng OmniVoice, cài thêm nhóm TTS:

```bat
uv sync --extra tts
```

Để dùng VieNeu-TTS-v2, cài worker riêng:

```bat
install_vieneu_worker.bat
```

VieNeu chạy trong `engines/vieneu_worker/.venv`, tách khỏi môi trường chính để tránh xung đột dependency với OmniVoice. Sau khi cài, chọn `VieNeu TTS v2 Standard` hoặc `VieNeu TTS v2 Turbo` trong dropdown model.

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
- Có checkbox `Tách mỗi dòng SRT/đoạn văn thành một file audio`, mặc định bật và Tkinter sẽ nhớ trạng thái cho lần mở sau.
- Quản lý profile giọng trong tab `Profile giọng`, lưu theo tên, dự án, transcript và ghi chú.
- Quản lý model và tải các model bắt buộc còn thiếu.

Khi bật chế độ tách file, `.srt` sẽ xuất mỗi cue/dòng subtitle thành một cặp file riêng như `tenfile_001.wav` và `tenfile_001.srt`. Nếu nhập văn bản trực tiếp, mỗi đoạn cách nhau bằng một dòng trống sẽ thành một file audio riêng.

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

File này sẽ cài nhóm TTS rồi ép cài lại `torch==2.7.1+cu126` và `torchaudio==2.7.1+cu126`, phù hợp hơn với GTX 1080 Ti.
