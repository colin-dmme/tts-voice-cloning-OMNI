# VieNeu Worker

Thư mục này chứa môi trường riêng cho VieNeu-TTS. App chính gọi worker qua subprocess để tránh xung đột dependency với OmniVoice.

## Cài đặt

Từ thư mục gốc dự án, chạy:

```bat
install_vieneu_worker.bat
```

## Cách app chính gọi worker

Core ghi một file JSON request tạm, gọi `synthesize.py`, worker tạo WAV tạm, sau đó core đọc WAV lại để dùng chung pipeline xuất file, tách file và SRT.

Khi dùng VieNeu Standard kèm profile giọng, worker tự chuyển codec sang `neuphonic/distill-neucodec` để có hàm encode giọng mẫu. Codec này chạy CPU và cần package `neucodec`.
