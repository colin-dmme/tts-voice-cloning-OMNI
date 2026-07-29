# Changelog

Tất cả thay đổi đáng chú ý của Colin TTS Studio được ghi theo từng phiên bản
trong file này. Dự án sử dụng phiên bản theo Semantic Versioning.

## [0.3.0] - 2026-07-29

### Added

- Thêm nền tảng AI authoring độc lập với provider TTS: AI tạo
  `PerformancePlan` trung lập, dialect adapter mới chuyển sang cú pháp provider.
- Thêm `HiggsDialectAdapter` cho Emotion, Style, Pace, Pitch, Expressiveness,
  Pause và vocal SFX; renderer luôn dùng lại nguyên văn nguồn.
- Thêm AI Performance Director trong tab Văn bản, chỉ xuất hiện khi model TTS
  khai báo authoring capability.
- Thêm khai báo loại nội dung, nền tảng, vai trò đoạn, đối tượng nghe, phong
  cách, mật độ tag, SFX và chỉ dẫn riêng.
- Thêm Voice Context: đọc profile giọng đang chọn, hỗ trợ khai báo nam/nữ/trung
  tính và mô tả chất giọng; mô tả được nhớ riêng theo profile/voice ID.
- Thêm tạo 1–4 phương án, giải thích từng quyết định, cảnh báo validator, tạo
  lại theo cùng setting, so sánh và áp dụng có Undo.
- Thêm preset có tên, preset theo profile giọng, lưu setting gần nhất và lịch
  sử candidate theo hash văn bản.
- Thêm trang **AI / API** quản lý AI provider, model, endpoint, timeout, retry,
  API key pool, nhập JSON, test kết nối và lấy danh sách model.
- Thêm Gemini OpenAI-compatible adapter, key rotation, quota/auth
  classification, retry server-busy, heartbeat, cancel và log không chứa giá
  trị API key.
- Thêm one-time importer tương thích `key_pool.json` của dự án
  `rewrite-truyen-dai`, có chống trùng bằng fingerprint.
- Thêm tài liệu mở rộng provider/dialect tại
  `docs/ai-authoring-architecture.md`.

### Changed

- Mở rộng `ProviderDescriptor` bằng `authoring_dialect` và
  `authoring_features`; GUI không kiểm tra trực tiếp `provider_id`.
- Chuyển mô tả delivery tag Higgs về ngữ nghĩa đặt ở đầu câu; Pause/SFX vẫn là
  điều khiển theo vị trí.
- Nâng phiên bản package và ứng dụng từ `0.2.0` lên `0.3.0`.

### Compatibility

- Provider không khai báo authoring capability giữ nguyên giao diện và pipeline
  tạo giọng cũ.
- API key, preset và lịch sử AI nằm trong file runtime cục bộ đã ignore khỏi
  Git; `user_state` và cấu hình TTS cũ không thay đổi.
- Higgs Script toolbar thủ công vẫn hoạt động độc lập với AI Director.

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
