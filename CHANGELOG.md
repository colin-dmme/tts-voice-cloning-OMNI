# Changelog

Tất cả thay đổi đáng chú ý của Colin TTS Studio được ghi theo từng phiên bản
trong file này. Dự án sử dụng phiên bản theo Semantic Versioning.

## [0.2.0] - 2026-07-27

### Added

- Thêm Higgs Script toolbar chỉ hiển thị khi chọn provider Higgs, cho phép chèn
  Emotion, Style, Speed, Pitch, Expressiveness, Pause, Long pause và SFX tại
  vị trí con trỏ.
- Thêm Higgs Script validator với cảnh báo token sai và SFX không đi sát từ
  tượng thanh.
- Thêm xem trước các request sau khi chia để kiểm tra delivery state và ranh
  giới chunk trước khi chạy.
- Thêm compiler/chunker riêng cho Higgs: bảo toàn control token, kế thừa
  delivery state giữa các request và không nhân bản pause/SFX.
- Hỗ trợ tạo reusable Custom Voice từ Voice Profile qua
  `POST /v1/audio/voices`.
- Thêm kho Custom Voice theo ID endpoint ổn định; thay URL TryCloudflare không
  làm mất liên kết voice nếu giữ nguyên ID endpoint.
- Custom Voice ID được đưa vào quy trình export/restore `user_state` nhưng không
  xuất URL endpoint hoặc API secret.
- Thêm loại endpoint SGLang, Boson Cloud và compatible gateway.
- Thêm Bearer authorization qua biến môi trường; secret không được ghi vào
  preferences hoặc job manifest.
- Thêm preset voice Boson vào mục Nguồn giọng khi chọn Boson endpoint.

### Changed

- Chuyển Emotion/Style/Prosody/SFX khỏi khu vực sampling của Higgs sang công cụ
  soạn nội dung; các giá trị cũ vẫn được đọc như delivery baseline.
- Chuyển `voice` của Higgs về đúng mục Nguồn giọng, dùng chung lựa chọn giọng
  server, preset, Custom Voice hoặc clone từ Profile.
- Endpoint và Custom Voice được capability-gate từ core; GUI không tự hardcode
  tính năng theo provider.
- Nâng phiên bản ứng dụng và package từ `0.1.0` lên `0.2.0`.

### Fixed

- Không còn làm hỏng token `<|...|>` khi chuẩn hóa văn bản tiếng Việt.
- Không còn xóa Higgs token trong file SRT; HTML subtitle thông thường vẫn được
  loại bỏ như trước.
- Không còn tự chèn pause/SFX từ một setting toàn cục vào mọi chunk.
- Tiến độ file/hàng đợi không còn lùi về 0% khi nhận status callback trễ và
  không tăng sai số lần chạy khi một request đang chạy phát nhiều callback.

### Compatibility

- Pipeline chuẩn hóa và chia đoạn của OmniVoice, VieNeu, Qwen, Valtec, F5-TTS,
  Chatterbox và Piper không thay đổi.
- Cấu hình Higgs `0.1.x` vẫn được đọc; các field delivery cũ được giữ để hỗ trợ
  migration.

## [0.1.0] - 2026-07-25

### Added

- Kiến trúc TTS đa provider, Voice Profile, queue file và giao diện PySide6.
- Higgs TTS 3 qua SGLang-Omni remote endpoint, streaming PCM và clone giọng
  bằng reference audio Data URI.
- GPU safety, model management, license và các pipeline audio đầu ra.
