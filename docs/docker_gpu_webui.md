# Docker GPU Web UI

Ghi chú cho máy thuê dạng Docker GPU Linux, không có Windows Remote Desktop.

## Cấu hình lúc thuê

- Template: `pytorch`
- Ports: giữ `22`, giữ `8888`, thêm `7860`
- Storage: nên chọn `200GB` hoặc `250GB`

Port `7860` là cổng Gradio Web UI của Colin TTS Local.

## Chạy nhanh trong container

Sau khi container mở terminal, chạy:

```bash
git clone https://github.com/colin-dmme/tts-voice-cloning-OMNI.git
cd tts-voice-cloning-OMNI
bash Start-ColinTTS-Docker-GPU.sh
```

Script này sẽ:

- cài `uv` nếu container chưa có;
- cài môi trường Python chính;
- restore `user_state/` vào profile giọng và setting dùng chung;
- cài VieNeu worker CUDA trên Linux;
- mở Web UI ở `0.0.0.0:7860`;
- dùng owner mode mặc định, không yêu cầu license.

Linux GPU scripts dùng PyTorch CUDA 12.8 mặc định để hỗ trợ RTX 50xx/5090 Blackwell (`sm_120`). Nếu cần ép index khác, đặt biến `PYTORCH_CUDA_INDEX_URL` trước khi chạy script.

Nếu muốn giữ license như bản khách hàng:

```bash
bash Start-ColinTTS-Docker-GPU.sh --require-license
```

Nếu muốn cài thêm Qwen worker:

```bash
bash Start-ColinTTS-Docker-GPU.sh --qwen
```

Nếu worker đã cài rồi và chỉ muốn mở lại app:

```bash
bash Start-ColinTTS-Docker-GPU.sh --skip-workers
```

## Cách dùng Web UI

Mở URL port `7860` do nhà cung cấp cloud hiển thị.

Trong tab `Tạo giọng đọc`:

- nhập text trực tiếp, hoặc upload `.srt`, `.txt`, `.md`;
- chọn model, profile giọng, codec, thiết bị `GPU CUDA`;
- bật `Tách dòng SRT/đoạn văn thành file riêng` nếu muốn xuất từng dòng;
- bấm `Tạo audio`;
- tải từng file hoặc tải toàn bộ bằng file ZIP.

## Không ảnh hưởng Windows

Các script Windows cũ vẫn giữ nguyên:

- `Start-ColinTTS.bat`
- `install_vieneu_worker_cuda.bat`
- `run_tkinter.bat`
- bản portable Windows trong `packaging/build_portable.ps1`

Linux Docker dùng các script `.sh` riêng trong `scripts/`.
