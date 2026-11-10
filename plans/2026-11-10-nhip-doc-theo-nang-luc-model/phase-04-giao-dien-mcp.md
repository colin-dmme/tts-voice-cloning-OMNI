# Pha 4. Giao diện Qt Studio, MCP và tài liệu

**Đã làm (10/11/2026).**

- **Core:** `ui_presenters/rhythm_presenter.py` gồm `rhythm_view`, `RhythmTracker`, màu nhãn, `LOCK_TOOLTIP`. Qt và MCP dùng chung presenter này.
- **Qt:**
  - Mục "Nhịp đọc & nhạc chuyển" (`widgets/narrative_pacing.py`) có phạm vi, preset, nút "Lấy từ cài đặt cũ" (hỏi xác nhận), Min–Max cho 12 tầng kèm nhãn màu và tooltip, khung tùy chọn riêng theo model, nhãn cho 3 loại nhạc.
  - Khóa mục cũ: `CollapsibleSection.set_locked` cho "Ngắt nghỉ theo dấu câu" (hiện `DEACTIVE · DO NHỊP ĐỌC QUẢN LÝ`), `DeclarativeProviderGroup.set_locked` cho setting trùng của provider, và khóa "Nghỉ giữa đoạn gốc".
  - Đổi model thì ghi vào Nhật ký hệ thống; lúc khôi phục cài đặt thì không ghi.
- **MCP:** tool `describe_reading_rhythm`, khối `rhythm` trong `get_generation_contract`, `rhythm_plan` trong kết quả job (đọc từ `pacing_report.json`). Ghi chú về `pacing` cho EPUB và xuất tách đã cập nhật.
- **Tài liệu:** `docs/narrative-pacing.md` (mục Nhịp đọc theo model), `docs/mcp-server.md`.
- **Test:** `tests/test_qt_rhythm.py` (6 test, Qt offscreen), cùng test MCP và test kết quả job. Toàn bộ 772 test qua.
- **Ảnh chụp** (render bằng font thật, không mở cửa sổ): `reports/screenshots/`.

Chưa làm:
- Chưa có thông báo nổi ở thanh trạng thái (đang ghi vào Nhật ký hệ thống).
- Preset ngắt nghỉ cũ chưa lưu khối `rhythm`, vì Nhịp đọc đã có preset riêng.
- Skill `narrative-pacing` chưa gọi `describe_reading_rhythm`.
- Qt Studio đang mở phải khởi động lại mới thấy giao diện mới.

Trạng thái: chưa làm. Cần pha 1; phần khóa mục cũ cần pha 2. Đã chốt: **chỉ làm Qt Studio** (Tkinter/Gradio giữ nguyên), **MCP cập nhật đầy đủ**.

## Qt Studio

Dùng lại kiểu giao diện đang có trong `pages/settings_panel.py`: `CollapsibleSection` với ô bật và nhãn `ACTIVE · ĐANG ÁP DỤNG` / `DEACTIVE · …` (hàm `_section`, dòng 153), và `ControlState` cho tooltip lý do khóa.

**Mục "Nhịp đọc"**
- Thay mục "Nhịp kể chuyện && nhạc chuyển" (`settings_panel.py:125`, widget `widgets/narrative_pacing.py`).
- Nhãn đầu mục:
  - Bật, phạm vi toàn bộ: `ACTIVE · QUẢN LÝ TOÀN BỘ NGẮT NGHỈ`.
  - Bật, chỉ nhịp kể chuyện: `ACTIVE · CHỈ NHỊP KỂ CHUYỆN`.
  - Tắt: `DEACTIVE · DÙNG CÀI ĐẶT NGẮT NGHỈ CŨ`.
- Dòng đầu mục: chọn phạm vi, preset, rồi dòng tóm tắt `RhythmPlan.summary`, ví dụ "ZeroTTS: 3 tầng model tự lo + app bù, 9 tầng APP".
- **Tùy chọn riêng của model** (`RhythmPlan.switches`): khung nhỏ "Riêng cho Kokoro" / "Riêng cho OmniVoice", chỉ hiện khi model đó đang chọn.
- 4 nhóm gập: Trong câu · Cuối câu · Giữa đoạn · Nhạc. Mỗi dòng tầng gồm:
  - Tên tầng, ô Min và ô Max (Min = Max là cố định).
  - Nhãn nhỏ cùng kiểu badge: `MODEL`, `APP`, `MODEL TỰ LO + APP BÙ`, `GIỚI HẠN`, `KHÔNG ÁP DỤNG`.
  - Tooltip là `effective_note` + `reason`.
  - KHÔNG ÁP DỤNG: ô mờ nhưng vẫn hiện số. GIỚI HẠN: dòng phụ màu cam ngay dưới.

**Khóa mục cũ** khi phạm vi toàn bộ
- Mục "Ngắt nghỉ theo dấu câu": nhãn đầu mục đổi thành `DEACTIVE · DO NHỊP ĐỌC QUẢN LÝ`, ô bật bị khóa.
- Ô "Nghỉ giữa đoạn gốc" trong "Cơ bản" và setting trùng trong "Tinh chỉnh riêng" (ví dụ "Khoảng lặng giữa đoạn" của ZeroTTS): vô hiệu, tooltip "Do Nhịp đọc quản lý — tầng X".
- "Tùy chỉnh điểm nối chunk" **không khóa**: đó là kỹ thuật nối mẩu. Phân xử chỉ gắn GIỚI HẠN cho tầng trong câu khi chọn crossfade/nối thẳng.

**Đổi model / thiết bị / chế độ xuất / nguồn EPUB**
- Tính lại plan rồi gọi `diff_rhythm_plans`.
- Có khác biệt thì ghi vào "Nhật ký hệ thống" và hiện thông báo 6s ở thanh trạng thái, kèm nút "Xem chi tiết".

**Ràng buộc**: presenter Core (`ui_presenters/rhythm_presenter.py` mới) tính sẵn mọi chữ và trạng thái. Widget không rẽ nhánh theo provider_id.

## MCP (`src/colin_studio_tts_mcp/`)

- `contracts.py`:
  - `generation.pacing` nhận `scope`, các trường `*_range` và `model_switches`. Trường cũ vẫn nhận.
  - Áp cho `start_text_generation` và `start_file_generation`, gồm cả file EPUB.
- `get_generation_contract(model_id)`: thêm khối `rhythm`, gồm hồ sơ tầng của model, switch kèm giá trị mặc định, và setting bị khóa.
- Tool mới `describe_reading_rhythm(model_id, output_mode="merged", source_kind="text", pacing=None)`: trả `RhythmPlan` JSON đã phân xử, có cả dòng giải thích.
- `plan_narrative_pacing`, `pace_existing_audio`: nhận cùng trường mới; báo cáo có `rhythm_plan`.
- Kết quả job (`job_manager.py`) trả `rhythm_plan` từ `pacing_report.json`.
- Phần Colab đang có thay đổi chưa commit trong `server.py` / `contracts.py`: chỉ thêm, không sắp xếp lại import hay format cả file.

## Tài liệu

- `docs/narrative-pacing.md`: thêm phần "Nhịp đọc theo model" (bảng nhãn, hồ sơ đã đo, hai tùy chọn Kokoro/OmniVoice, EPUB, cách đọc thông báo khi đổi model).
- `docs/mcp-server.md`: tool mới, trường mới, ví dụ request TXT và EPUB.
- Skill `~/.claude/skills/narrative-pacing`: gọi `describe_reading_rhythm` trước khi render.

## Tiêu chí

- [ ] Trong Qt, đổi Kokoro → OmniVoice → ZeroTTS → Piper: số không đổi, nhãn đúng bảng hồ sơ, có thông báo khác biệt, switch riêng hiện/ẩn đúng model.
- [ ] Phạm vi toàn bộ: mục cũ khóa và có tooltip. Tắt Nhịp đọc: mục cũ chỉnh được như trước.
- [ ] Chọn nguồn EPUB: `section` và nhạc hiện KHÔNG ÁP DỤNG kèm lý do.
- [ ] `describe_reading_rhythm` và presenter Qt cho cùng JSON (test so sánh).
- [ ] Test MCP cũ (`tests/test_colin_studio_tts_mcp.py`) vẫn qua; thêm test cho tool mới và trường mới.
- [ ] Chụp màn hình mục Nhịp đọc với Kokoro, OmniVoice, ZeroTTS, lưu vào `reports/`.
