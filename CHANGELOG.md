# Changelog

Tất cả thay đổi đáng chú ý của Colin TTS Studio được ghi theo từng phiên bản
trong file này. Dự án sử dụng phiên bản theo Semantic Versioning.

## [0.6.5] - 2026-11-04

### Added

- Bộ lọc nội dung EPUB dùng chung core/GUI/MCP: bỏ nguồn theo semantic markup,
  class `sources`/`references` hoặc phạm vi heading nguồn; giữ ghi chú diễn giải.
- URL/DOI có chế độ không đọc, chỉ tên miền hoặc đọc địa chỉ; nhãn liên kết
  có nghĩa được giữ. Lọc trước chuẩn hóa số/ngày và trước mọi provider TTS.
- Dùng nghĩa Việt đã có trong cặp `chữ Hán (giải nghĩa)`, cảnh báo các ký tự
  còn lại theo vị trí và nhận bảng cách đọc riêng; không tự dịch hoặc xóa chữ Hán.
- Tùy chọn phần giới thiệu, phụ lục nội dung và ghi chú kỹ thuật cuối sách.
- Qt/Tkinter có bản xem trước gốc/đọc/thay đổi/chữ Hán và nút xuất để kiểm tra;
  Web có cùng tùy chọn và so sánh. Thiết lập được lưu trong preset/setting EPUB.
- Tạo sách tự lưu TXT bản đọc, JSON báo cáo và nguồn MD; kết quả có
  `reading_text_path`, `reading_report_path`, `references_path`. ZIP Web kèm các file này.
- MCP thêm `preview_epub_reading`, `export_epub_reading`; `inspect_epub` nhận
  toàn bộ `epub`, trả thống kê lọc/cảnh báo qua cùng schema.

### Fixed

- DOI được bảo vệ khỏi bộ chuẩn hóa ngày/số khi người dùng chọn đọc địa chỉ.
- Bibliography lồng trong một chương không làm bỏ cả chương. Lọc phần đọc vẫn
  giữ chỉ số chương gốc; nhịp chuyển chương, SRT và cache theo nội dung sau lọc.

## [0.6.4] - 2026-10-26

### Added

- Tab **Nhạc** trong thanh điều hướng Qt: tìm/tích nhiều chủ đề, thêm/bỏ từng
  bài, lọc các bản đã tích, nghe thử, nhập nhạc và sửa tên/mô tả/chủ đề/tag.
- Quản lý preset nhạc: tạo, lưu, sao chép, xóa và dùng trong Studio; có thể
  chuyển tập đang tích sang Studio mà chưa lưu preset. Tìm kiếm giữ lựa chọn.
- Hai nguồn random mới: `random_selection` với `theme_ids`, `track_ids`,
  `excluded_track_ids`; `preset` với `preset_id`. Hợp nhiều nhóm và bài riêng,
  bỏ trùng rồi loại các bài không dùng. Nhóm đã chọn tự nhận bài nhập sau này.
- Preset riêng lưu tại `music_library/presets.json`, cùng thư viện Qt/Tkinter,
  Web và MCP. Giữ chế độ bài cố định/random một chủ đề để đọc cấu hình cũ.
- MCP thêm `list_chapter_music_presets`, `save_chapter_music_preset`,
  `delete_chapter_music_preset`, `resolve_chapter_music_selection`; plan ghi
  preset, quy tắc chọn và danh sách ứng viên để agent kiểm tra.

### Fixed

- Đổi tập bài trong preset làm hàng đợi/cache kiểm tra lại; chỉ đổi tên preset
  không buộc tạo lại chương. Sách đang chạy giữ lựa chọn nhạc đã chốt kể cả
  khi preset được sửa hoặc xóa trong lúc tạo audio.
- Khôi phục trang điều hướng theo khóa, giữ đúng trang cũ khi thêm tab Nhạc.

### Documentation

- Cập nhật README, hướng dẫn EPUB, thư viện nhạc, preset và payload MCP.

## [0.6.3] - 2026-10-25

### Added

- Gộp nhịp sau tên chương/giữa chương thành các khối độc lập: không nghỉ,
  khoảng lặng hoặc nhạc. Mỗi vị trí có độ dài nhạc cố định/phát trọn và fade riêng.
- Khóa số giây khi phát trọn; khóa fade khi không dùng nhạc; khóa nhịp tiêu đề
  hoặc quyển khi không đọc phần đó; khóa nguồn nhạc khi không vị trí nào dùng nhạc.
- Chọn bài/nhóm random và âm lượng tại nguồn nhạc chung; nghe thử từng nhịp theo
  đúng độ dài/fade của vị trí đó. Đồng bộ Qt, Tkinter, Web và MCP/core.
- Schema `generation.epub.breaks.title/chapter`, có ưu tiên rõ ràng so với cấu
  hình cũ. Lưu/đọc lại cấu hình không đổi các giá trị cũ chỉ vì mở giao diện.
- SRT, kế hoạch nhạc và checkpoint theo cấu hình thực của từng nhịp; có thể dùng
  khoảng lặng 1 giây sau tiêu đề và phát trọn nhạc giữa chương trong cùng tác vụ.

## [0.6.2] - 2026-10-25

### Added

- Chọn **Cắt vừa khoảng nghỉ** hoặc **Phát trọn bản nhạc trong thư viện** trên
  Qt/Tkinter/Web và MCP (`music.duration_mode`). Phát trọn dùng đủ mẫu PCM của
  bài được chọn, tự cập nhật độ dài nhịp và SRT; nghe thử/plan hỗ trợ cùng chế độ.
- Metadata nhạc gồm `description`, `themes`, `tags`; tự xuất `MUSIC_CATALOG.md`
  cạnh `library.json`, tương thích catalog cũ chưa có các trường mới.
- Random trong nhóm chủ đề trên Qt, Tkinter và Web, dùng shuffle bag hạn chế lặp
  liên tiếp; cùng EPUB và lượt trộn tạo cùng kế hoạch để tiếp tục checkpoint.
- Xuất kế hoạch từng nhịp ra JSON, trả `music_plan_path` trong kết quả. Cache tính
  lựa chọn thực và hash từng file nhạc đã dùng; nhạc vẫn nằm gọn trong nhịp nghỉ.
- `generation.epub.music.track_overrides` cho agent chọn `title:N` hoặc `chapter:N`
  theo nội dung. MCP thêm `plan_epub_music`, `update_chapter_music_metadata`; bộ
  liệt kê hỗ trợ lọc theme/tag và bộ nhập nhận mô tả/chủ đề/tag.

### Documentation

- Hướng dẫn random, mô tả thư viện, kế hoạch nhạc và payload MCP tại
  `docs/music-library.md`. Nhạc riêng và key tiếp tục nằm ngoài Git.

### Fixed

- Nút **Chạy hàng đợi** nhận cả mục **Cần chạy lại** sau khi đổi nguồn/thiết lập
  trên Qt và Tkinter; trước đây chỉ lấy mục **Chờ chạy**, gây thông báo không có
  file phù hợp dù EPUB đã nằm trong hàng đợi. Mục thành công còn hợp lệ vẫn được
  bỏ qua; chạy riêng một mục tiếp tục dùng **Chạy mục chọn**.

## [0.6.1] - 2026-10-25

### Added

- Thư viện nhạc chuyển chương cục bộ, nhập/chuẩn hóa audio và nghe thử; tùy chọn
  nhạc giữa chương hoặc sau tên chương, âm lượng riêng và tự trim/fade vừa nhịp.
- Nhạc thay đúng mẫu PCM trong khoảng nghỉ; giọng và timeline SRT giữ nguyên.
  Sửa cộng thời gian nghỉ theo số mẫu thực ở các sample rate như 22.050 Hz.
- Qt, Tkinter, Web có bộ chọn nhạc; MCP thêm `list_chapter_music`,
  `preview_chapter_music`, `import_chapter_music`, dùng `generation.epub.music`.
- Cache EPUB tính cả hash audio nhạc để không dùng lại chương có nhạc đã thay.
  Key tạo nhạc và file nhạc riêng được loại khỏi Git.

### Documentation

- README bổ sung luồng nhập EPUB, đặt nhịp nghỉ, bật SRT và chọn/nhập nhạc riêng.
- Làm rõ việc chép MP3 trực tiếp vào `music_library/` chưa tự đăng ký bản nhạc;
  cần dùng **Thêm nhạc…** hoặc MCP `import_chapter_music` để cập nhật catalog.
- Hướng dẫn chuyển máy bằng cả thư mục nhạc và `library.json`; audio riêng/API
  key được giữ ngoài Git, không đưa vào bản mã nguồn phân phối.

## [0.6.0] - 2026-10-25

### Added

- Đọc EPUB theo spine, bỏ điều hướng/bìa và nội dung phụ, giữ tiêu đề, đoạn văn,
  dòng thơ và chuyển cảnh; xem trước/chọn khoảng chương từ desktop, Web và MCP.
- Chỉnh riêng nghỉ sau tên chương, giữa chương, chuyển cảnh và đầu quyển bằng
  khoảng lặng PCM, dùng chung mọi engine hiện có mà không cần thẻ pause của model.
- Xuất WAV/MP3 kèm SRT theo chương hoặc ghép sách; SRT cộng đúng khoảng nghỉ.
  Ghép PCM theo luồng, hỗ trợ RF64 cho sách dài, lưu chương hoàn tất để tiếp tục.
- MCP thêm `inspect_epub`, nhận EPUB qua `start_file_generation`, công bố schema
  `generation.epub` trong contract; báo lỗi job khi có file thất bại.

## [Unreleased]

### Added

- Tích hợp `ZeroTTS 202M Official` từ ZeroWeight AI bằng worker ONNX CPU cô lập,
  snapshot model ghim revision, đầu ra mono 48 kHz và tám voice pack chính thức.
- Thêm đầy đủ 22 thiết lập ZeroTTS vào provider contract: chuẩn hóa tiếng Việt,
  dọn dấu câu, chia đoạn dài, khoảng nghỉ, CFG, text/audio sampling, giới hạn
  frame, seed, streaming decoder, số luồng ONNX và warmup. Qt, Tkinter và MCP
  tự dựng từ cùng metadata, không hardcode control trong GUI.
- Thêm cài đặt Windows/Linux, kiểm tra artifact model, test forwarding worker và
  smoke test MCP thật tạo WAV/SRT. Profile clone được tắt đúng theo bản 0.1.2 vì
  upstream chưa phát hành voice encoder.
- Tích hợp thêm toàn bộ ba artifact chính thức của `ZeroTTS-GGUF`: F32, Q8_0 và
  Q4_0. Worker native ggml giữ model resident, dùng tokenizer và voice latent
  chính thức, rồi giải mã frame bằng MOSS codec ONNX thành WAV mono 48 kHz.
- Hợp đồng setting nay lọc theo runtime model. Ba model GGUF ẩn và từ chối CFG
  cùng warmup vì C++ upstream chưa triển khai, trong khi ONNX vẫn giữ đủ 22 key.
- Sửa signal thay đổi của nhóm provider setting động trên Qt để checkbox,
  spinbox và combobox lưu thay đổi mà không phát sinh lỗi sai chữ ký signal.
- Thêm hệ thống Cách đọc/Từ điển phát âm theo nhiều preset: thay chữ ở đầu vào
  engine nhưng giữ nguyên văn bản và SRT, tô màu chỗ khớp trong Studio, thống kê
  từ/lần/xung đột, ghim preset theo mục hàng đợi và lưu báo cáo bất biến mỗi job.
  Toàn bộ matching, snapshot, lưu preset và báo cáo nằm ở Core, không hardcode
  business logic vào GUI.
- Thêm MCP server cục bộ `colin_studio_tts_mcp` qua stdio với 10 tool:
  khám phá model/form/voice, tạo giọng từ text hoặc TXT/MD/SRT theo job nền,
  theo dõi tiến độ, hủy và thử lại; job metadata bền vững trong SQLite.
- MCP dùng trực tiếp `AppController`, `TtsService`, capability/form descriptor
  và voice library của Core. Không chép provider logic vào adapter hoặc GUI.
- Thêm khóa sinh giọng liên tiến trình tại Core để Qt, Tkinter và MCP không
  tranh model/GPU khi chạy đồng thời; mọi entry point cùng giữ GPU safety.
- Thêm ô tìm Model TTS theo tên hoặc mã, hỗ trợ gõ tiếng Việt không dấu và
  chỉ đổi model khi người dùng chọn gợi ý hoặc nhấn Enter.
- Thêm bộ chặn con lăn cấp ứng dụng cho toàn bộ SpinBox, Slider và ComboBox
  trong giao diện Qt; cuộn trên control sẽ cuộn trang gần nhất thay vì âm thầm
  thay đổi tham số. Control tạo động từ metadata và các dialog cũng tự áp dụng.
- Tích hợp hai provider CPU ONNX độc lập: `Kokoro ONNX` từ bản chuyển đổi
  `onnx-community/Kokoro-82M-v1.0-ONNX-timestamped` (54 giọng, 8 ngôn ngữ)
  và `Supertonic 3` chính thức từ `Supertone/supertonic-3` (10 voice style,
  31 ngôn ngữ gồm tiếng Việt).
- Thêm hợp đồng `provider_options` và schema `ProviderSettingSpec`: Core kiểm
  tra kiểu/range, lưu preferences/history, rồi Qt và Tkinter tự dựng control từ
  metadata. GUI không chứa nhánh riêng cho Kokoro hoặc Supertonic.
- Thêm worker cô lập, bộ cài Windows/Linux và kiểm tra đầy đủ artifact cho cả
  hai model. Kokoro có `Cắt im lặng đầu/cuối` và `Ngữ điệu liên tục`;
  Supertonic có `Mức chất lượng` 5–12 (khuyến nghị 8).
- Ngắt nghỉ theo dấu câu dùng chung của Core áp dụng cho cả hai provider và
  được chèn trực tiếp vào PCM; A/B tích hợp đo được chênh lệch đúng bằng tổng
  khoảng nghỉ đã cấu hình.

- Tích hợp 13 package Piper ONNX khác biệt thực tế từ bộ `VbeeTTS/extracted_models`,
  đặt tên hậu tố `— Vbee Export` để phân biệt xuất xứ package. Bảy package trùng
  PCM với model sẵn có và một thư mục Ngạn trùng lặp đã được loại khỏi catalog.
- Thêm nguồn model `manual` và hành động `Nhập model local`: kiểm tra SHA-256 của
  cả ONNX/JSON, copy vào storage quản lý, không sửa nguồn và không nhầm với tải
  Hugging Face.
- Thêm hồ sơ tinh chỉnh chung cho mọi Piper ONNX: Piper chuẩn, Vbee tham chiếu,
  Noise Scale, Noise W và Seed tái lập để A/B. Tham số đi thật tới worker ONNX;
  tooltip theo package chỉ khuyến nghị, không tự đổi hành vi.

- Thêm worker `vieneu_v3_worker` độc lập cho VieNeu v3 Turbo 3.3.0: mặc định
  chạy CPU ONNX INT8 không cần PyTorch, có bộ cài GPU PyTorch riêng cho batch dài.
- Thêm probe runtime theo từng model/worker, nhãn thiết bị rõ `CPU ONNX` hoặc
  `GPU CUDA · PyTorch` và thông báo cài đặt chỉ đúng worker đang chọn.
- Đồng bộ catalog VieNeu v3.3 đủ 20 giọng chính thức, gồm Ngọc Huyền, Mỹ Duyên,
  Quỳnh Anh, Đức Trí, Kim Thanh và Adam.
- Tab Văn bản: thêm ô "Nơi lưu" để chọn thư mục lưu audio riêng cho lần tạo,
  và các nút "📂 Mở thư mục" + "⧉ Copy path" + "⧉ Copy content" cạnh "Nghe thử"
  để mở nhanh thư mục kết quả, copy đường dẫn file audio, hoặc copy đúng đoạn
  văn bản đã dùng để tạo file đang nghe thử.
- Tên file mặc định cho audio từ Văn bản lấy 20 ký tự đầu của nội dung (đã lọc
  dấu câu, khoảng trắng, ký tự đặc biệt) thay cho "output"; ô Tên file hiện
  gợi ý tên tự động khi gõ.
- Tùy chọn tự thêm hậu tố "_{giọng}_{thời lượng}" (định dạng giờ-phút-giây, ví
  dụ `01m23s`, không dùng ký tự `:`) vào tên file. Tên tự động luôn thêm hậu
  tố; khi tự đặt tên thì có checkbox bật/tắt. Thời lượng chỉ biết sau khi tạo
  xong nên Core chốt tên file lúc lưu (bản gộp) hoặc theo từng file (bản tách).
- Lịch sử: thêm cột "Giọng" và "Ngôn ngữ", cùng bộ lọc Thời gian/Trạng thái/
  Loại và tìm kiếm theo giọng để dễ tra cứu.
- Thêm chính sách nối chunk trung lập provider: AUTO, Crossfade, Nối thẳng và
  Chèn khoảng lặng; thời gian crossfade mặc định là 80 ms.
- Thêm điều khiển Qt cùng tooltip tiếng Việt và mô tả chính sách thực tế của
  model đang chọn.

### Compatibility

- Mặc định Piper vẫn là Noise `0.667`, Noise W `0.800`, Seed ngẫu nhiên nên các
  cấu hình cũ giữ nguyên hành vi. Logic nghỉ theo dấu câu, nối chunk và nghỉ giữa
  đoạn gốc không thay đổi; chưa thêm xử lý cắt đuôi rung/rè.
- Catalog Piper tăng từ 33 lên 46 mục; 13 package Vbee Export đã được nhập sẵn ở
  máy hiện tại và có thể gỡ an toàn vào `.trash` rồi nhập lại từ nguồn.

### Changed

- Các model VieNeu cũ tiếp tục dùng worker hiện hữu nhưng được hiển thị rõ là
  `VieNeu v2`; chọn đồng thời VieNeu v2 và v3 sẽ cài đúng hai runtime, không gộp
  nhầm theo provider.
- VieNeu v3 dùng giọng mặc định chính thức của SDK 3.3 là Adam; bỏ tham số style
  đã bị SDK v3 ngừng hỗ trợ và bật denoise reference mặc định cho clone giọng.
- Nút "Dán đường dẫn" đọc thẳng clipboard vào hàng đợi, bỏ hộp thoại nhập tay;
  việc quét file nguồn chạy nền nên thêm số lượng lớn không làm treo giao diện.

### Changed

- AUTO của VieNeu giao việc chia/nối nội bộ cho SDK; Piper tiếp tục dùng nhịp
  theo dấu câu. Logic chọn chính sách nằm ở Core và metadata provider, không ở GUI.
- Loại bỏ crossfade ẩn toàn cục và tự di trú cấu hình nghỉ chunk cũ để giữ hành vi.

## [0.5.1] - 2026-09-10

### Changed

- Nâng worker VieNeu v3 Turbo từ SDK 3.3.0 lên 3.6.4 và `sea-g2p` lên 0.9.1.
- Đồng bộ catalog lên 23 giọng chính thức, dùng Minh Quân làm mặc định cho lượt
  chọn mới và giữ tương thích với lựa chọn giọng đã lưu trước đó.
- Chuyển cấu hình CPU mặc định sang ONNX FP32 và tải đúng thư mục
  `onnx_update` của model 3.6.4.

### Fixed

- Kiểm tra cache Hugging Face theo toàn bộ pattern bắt buộc thay vì chỉ kiểm tra
  sự tồn tại của một snapshot bất kỳ.
- MCP không còn công bố lựa chọn fixed voice có `voice_id` rỗng.

## [0.3.1] - 2026-07-29

### Added

- Thêm `AuthoringControlScope` trung lập provider với quyền bật/tắt riêng cho
  Emotion, Style, Pace, Pitch, Expressiveness, Pause và vocal SFX.
- Thêm allow-list tới từng giá trị: có thể cho dùng Emotion nhưng cấm riêng
  `elation`, hoặc chỉ cho phép nhịp/biểu cảm mà không dùng Emotion/Style/SFX.
- Thêm các preset phạm vi do core cung cấp: Cân bằng, Chỉ nhịp & biểu cảm,
  Không dùng cảm xúc và Chỉ khoảng nghỉ.
- Thêm dialog phạm vi động lấy toàn bộ nhóm, giá trị, nhãn và tooltip từ
  dialect metadata; GUI không chứa danh sách Higgs hoặc nhánh provider.
- Thêm source lineage nối candidate đã render về nguồn, session và candidate
  gốc; mở lại AI Director sau khi áp dụng sẽ tự dùng bản gốc và đúng lịch sử.
- Thêm fallback phục hồi lời từ markup khi kết quả không còn khớp lineage
  chính xác, kèm cảnh báo để người dùng kiểm tra.

### Changed

- Prompt AI chỉ công bố các feature/value đang được phép và đánh dấu rõ nhóm
  bị tắt.
- Core lọc lại mọi quyết định sau phản hồi AI; giá trị ngoài phạm vi bị loại và
  được ghi vào warnings, nên không phụ thuộc AI tự tuân thủ prompt.
- Preset, setting gần nhất và snapshot lịch sử giờ lưu cả control scope.
- Nâng phiên bản package và ứng dụng từ `0.3.0` lên `0.3.1`.

### Compatibility

- Brief/preset `0.3.0` chưa có control scope được tự nâng lên phạm vi mặc định;
  tùy chọn SFX cũ vẫn được chuyển đúng.
- Provider không hỗ trợ authoring và pipeline tạo giọng cũ không thay đổi.
- Runtime key, state, lineage và lịch sử tiếp tục nằm trong file cục bộ đã
  ignore khỏi Git.

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
