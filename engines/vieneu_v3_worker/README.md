# VieNeu v3 worker

Runtime độc lập cho `VieNeu v3 Turbo 3.6.4` của dự án
`tts-voice-cloning-OMNI`.

- CPU mặc định: ONNX Runtime FP32, không cần PyTorch.
- GPU tùy chọn: PyTorch CUDA, phù hợp batch dài.
- Không dùng runtime, manifest hoặc adapter của dự án khác.
- VieNeu v2 và các model GGUF cũ tiếp tục dùng `engines/vieneu_worker`.

Không cài package thủ công vào Python chính của ứng dụng. Dùng nút cài đặt
trong Quản lý model hoặc các script `install_vieneu_v3_worker*.bat` ở thư mục
gốc dự án.

Studio có thể gửi VieNeu v3 sang Colab qua compute service; cùng 23 preset
(gồm Ngọc Huyền) và clone từ audio Profile. Worker Colab dùng SDK 3.6.4,
giữ model resident và cache embedding/reference codes theo SHA-256 trong RAM.
Cache tối đa 16 giọng theo cặp SHA-256 + thiết lập denoise; đổi model sẽ xóa cache RAM.
