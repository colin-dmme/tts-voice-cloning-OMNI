# ZeroTTS worker

Worker cô lập cho package chính thức `zerotts==0.1.2` và snapshot model
`zeroweight-ai/ZeroTTS` đã ghim revision trong `config/models.yaml`.

Worker dùng JSON Lines qua stdin/stdout, giữ model ONNX trong tiến trình và chỉ
nạp lại khi đường dẫn model hoặc setting khởi tạo thay đổi. Tất cả sampling,
long-form preprocessing, seed và streaming decoder đều nhận từ
`provider_options` đã được Core xác thực.

Bản mã nguồn mở ZeroTTS 0.1.2 chỉ đọc voice latent `.npz` có sẵn. Nó không có
voice encoder, vì vậy provider này không nhận audio từ Profile giọng.
