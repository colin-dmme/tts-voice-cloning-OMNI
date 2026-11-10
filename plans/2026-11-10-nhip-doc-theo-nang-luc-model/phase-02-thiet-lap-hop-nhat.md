# Pha 2. Thiết lập Nhịp đọc hợp nhất và chuyển đổi từ cài đặt cũ

Trạng thái: **đã làm phần Core (10/11/2026)**. Việc lưu preset và trạng thái giao diện chuyển sang pha 4, vì phụ thuộc giao diện Qt.

Đã làm:
- `NarrativePacingOptions`: thêm `scope`, `model_switches` và `layer_ranges: {tầng: [min, max]}`. Đổi so với thiết kế ban đầu: dùng một dict chung thay cho các trường `*_range` riêng, để thêm tầng mới không phải đổi schema. Tầng không có trong dict dùng giá trị đơn như cũ, nên request cũ chạy y nguyên. `RANGE_LAYERS` trong shared được kiểm tra khớp với `rhythm/layers.py` ngay khi import.
- `rhythm/presets.py`: `RHYTHM_PRESETS` (podcast, audiobook, news). `apply_rhythm_preset` giữ nguyên switch, phạm vi và nhạc. `rhythm_from_legacy` đề xuất range từ cài đặt cũ bằng cách lấy lặng cộng thêm cộng với lặng tự nhiên trung vị đo ở pha 0.
- Test: `tests/test_rhythm_execution.py` (phần settings).

Còn lại (pha 4): lưu khối `rhythm` trong `pause_presets.py` / `user_state.py`, hộp xác nhận chuyển đổi khi bật lần đầu.

Ban đầu: chưa làm.

## Hướng

Không tạo thêm một bộ số thứ sáu. `ReadingRhythmOptions` **mở rộng `NarrativePacingOptions`**: các tầng giữa đoạn và nhạc đã có sẵn ở đó, chỉ thêm Min–Max cho các tầng trong câu và cuối câu. Bộ số trong mục "Ngắt nghỉ theo dấu câu" và "Nghỉ giữa đoạn gốc" được giữ nguyên, dùng lại khi tắt Nhịp đọc.

## File

- **Sửa** `src/omni_tts_shared/narrative_pacing.py`:
  - Thêm `LayerRange(min_ms, max_ms)` với validator `min ≤ max`; `min == max` nghĩa là giá trị cố định.
  - Thêm các trường `*_range` cho `comma`, `clause`, `ellipsis`, `sentence_end`, `question_end`. Trường đơn cũ (`sentence_end_pause_ms`…) vẫn nhận, tự đổi thành range `(x, x)`. Hợp đồng MCP cũ không vỡ.
  - Thêm `scope: Literal["pacing_only", "full"]`:
    - `pacing_only`: hành vi hiện nay, Nhịp kể chuyện chạy sau mọi thứ.
    - `full`: Nhịp đọc nắm mọi tầng và khóa mục cũ.
  - Thêm `model_switches: dict[str, str]` (ví dụ `{"kokoro_pause_mode": "library", "omnivoice_keep_long_silence": "on"}`). Lưu cho mọi model, chỉ model tương ứng dùng. Validator kiểm khóa/giá trị theo hồ sơ năng lực ở Core, không ở schema (schema shared không import Core).
- **Sửa** `src/omni_tts_core/pause_presets.py`: preset lưu thêm khối `rhythm`. Preset cũ không có khối này vẫn đọc được.
- **Sửa** `src/omni_tts_core/user_state.py`, `ui_presenters/settings_state.py`: lưu `rhythm` cạnh cài đặt cũ, không ghi đè.

## Chuyển đổi khi bật lần đầu

Lần đầu bật chế độ `full`, Core đề xuất giá trị khởi tạo từ cài đặt hiện tại. Giao diện hiện cho người dùng xác nhận, không âm thầm áp:

| Cài đặt cũ (lặng **thêm**) | Thành tầng Nhịp đọc (lặng **tổng**) |
|---|---|
| `sentence_pause` min–max | `sentence_end` = cũ + lặng tự nhiên trung vị của model (số đo pha 0) |
| `comma_pause`, `clause_pause`, `ellipsis_pause` | tương tự |
| `paragraph_pause` min–max | `paragraph`; các tầng giữa đoạn khác giữ mặc định của pacing |

Nếu chưa có số đo cho model: dùng mặc định pacing (520/620/380/200…) và ghi "chưa hiệu chỉnh theo model".

## Preset có sẵn

- **Podcast tự nhiên**: mặc định hiện tại của pacing, đã đối chiếu nghiên cứu.
- **Đọc chậm / sách nói**: nhân ×1,25 các tầng giữa đoạn, cuối câu 650–750.
- **Nhanh / tin tức**: nhân ×0,8, tắt `short_sentence`.

## Tiêu chí

- [ ] Request cũ (chỉ có trường đơn) và preset cũ load được, kết quả không đổi.
- [ ] Bật rồi tắt Nhịp đọc: cài đặt dấu câu và đoạn cũ còn nguyên.
- [ ] Đổi model không ghi vào `rhythm`. Test: đổi 5 model liên tiếp, so sánh bản lưu.
- [ ] `normalize_pause_values` không xóa khối `rhythm`.
