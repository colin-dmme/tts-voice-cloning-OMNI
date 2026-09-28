# ZeroTTS GGUF worker

Worker CPU kết hợp runtime ggml/GGUF chính thức của ZeroTTS với ONNX codec 48 kHz.
Ba model F32, Q8_0 và Q4_0 dùng chung worker nhưng nạp riêng file GGUF đã chọn.

Runtime native được build từ commit ZeroTTS đã ghim trong `build_native.py`.
Worker giữ model GGUF trong tiến trình, sinh frame codec bằng ggml, rồi giải mã
frame thành WAV bằng MOSS codec ONNX đi kèm snapshot model.

GGUF upstream chưa triển khai CFG và voice encoder. Vì vậy model GGUF không hiện
setting CFG, chỉ dùng voice pack có sẵn hoặc latent không điều kiện.

Lần cài source checkout cần Git, CMake và một C++17 compiler. Trên Windows,
installer đã được kiểm tra với Visual Studio 2022 Build Tools và MSVC AVX2.
Portable build có thể đóng gói sẵn `native/bin` nên máy đích không cần build lại.
