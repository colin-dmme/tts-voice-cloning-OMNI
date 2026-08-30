# VieNeu v3 worker

Runtime độc lập cho `VieNeu v3 Turbo 3.3` của dự án
`tts-voice-cloning-OMNI`.

- CPU mặc định: ONNX Runtime INT8, không cần PyTorch.
- GPU tùy chọn: PyTorch CUDA, phù hợp batch dài.
- Không dùng runtime, manifest hoặc adapter của dự án khác.
- VieNeu v2 và các model GGUF cũ tiếp tục dùng `engines/vieneu_worker`.

Không cài package thủ công vào Python chính của ứng dụng. Dùng nút cài đặt
trong Quản lý model hoặc các script `install_vieneu_v3_worker*.bat` ở thư mục
gốc dự án.
