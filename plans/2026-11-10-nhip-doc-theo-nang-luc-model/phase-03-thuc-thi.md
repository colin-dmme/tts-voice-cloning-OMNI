# Pha 3. Thực thi theo bên đảm nhận

Trạng thái: **đã làm (10/11/2026)**, đang đo xác nhận trên model thật.

Đã làm:
- `rhythm/execution.py` `prepare_rhythm(request, spec, source_kind)`: service gọi một lần mỗi job (cả ghép lẫn tách).
  - Phạm vi `full`: tầng `app_split` điều khiển bộ cắt câu (giá trị Nhịp đọc, Min–Max thành random). Tầng `library_param` thành `pause_options` cho engine. Job ghép đặt nghỉ giữa đoạn gốc về 0. Setting provider trùng tầng bị bỏ khỏi `provider_options`.
  - Pacing chỉ giãn các tầng không ai khác đảm nhận (`skip_layers`).
- `TtsEngineRequest.pause_options` (`engines/base.py`): kênh riêng, không đi qua `provider_options` vì kênh đó kiểm tra chặt theo khai báo provider.
- Kokoro: `preset_onnx_engine` gửi `pause_options`; worker truyền `sentence_pause` / `clause_pause`. Core chunk seam dùng cùng mức nghỉ cuối câu (`chunk_pause_ms`).
- OmniVoice: `postprocess_output=False` khi bật "Giữ khoảng lặng dài", rồi `rhythm/silence_tools.tidy_silences` cắt lặng đầu/cuối (giữ 0,1s) và rút lặng >2s về 1,2s. Bản omnivoice 0.2.1 đang cài rút lặng dài hơn 0,5s về **tối đa khoảng 1s** (không phải 0,6s), nên hồ sơ GIỚI HẠN đã sửa thành 1000ms.
- Renderer: Min–Max lấy mẫu riêng cho từng chỗ nghỉ. Tầng có range thì không cộng dao động ±70ms. `PacingUnit.locked_after` cho ranh giới EPUB. `skip_layers` dùng cho cả trong câu lẫn giữa đoạn.
- EPUB: pacing chạy cho từng chương, vì mỗi chương đã là một lần gọi `generate_audio`. Tên quyển/chương/cảnh là ranh giới khóa; nhạc và tầng chuyển mục tắt. SRT chương dịch theo remap như job TXT.
- Xuất tách: `stretch_sentence_pauses` giãn trong từng file. Seed theo số thứ tự đoạn nên file lẻ và file tổng giống nhau.
- Câu hỏi `?`: bộ cắt câu chỉ có một nhóm `. ! ?`, nên với Piper/Supertonic/Kokoro-cắt-câu, `?` nhận mức cuối câu khi cắt rồi được app giãn thêm cho đủ mức câu hỏi.
- `pacing_report.json` có thêm `rhythm_plan`.

### Đo xác nhận (10/11/2026, `scripts/measure_pause_capabilities.py --rhythm`)

Lần đo đầu với Nhịp đọc chỉ đạt 0–8/15 dấu. Có ba lỗi đã sửa:
1. **Cắt câu bị cộng dồn khoảng lặng ở hai đầu mẩu.** Mỗi mẩu Piper có sẵn khoảng 0,45s lặng, nên phẩy ra ~0,67s, cuối câu ~1,0s. Sửa: worker Piper/Supertonic/Kokoro cắt lặng hai đầu mỗi mẩu (`split_total`); service cắt tương tự ở chỗ nối chunk lớn (`_trim_seam_edges`); trước đó một chỗ nối ra 1,95s.
2. **Bộ dóng dấu câu trong code thật bị trôi vị trí.** Đã chuyển sang đồng hồ chỉ tính lúc có tiếng, giống script đo. Ngưỡng chỗ lặng để giãn: dấu câu từ 0,07s, dấu phẩy từ 0,08s (trước là 0,12s).
3. **OmniVoice còn chỗ ngừng 1,8s.** `tidy_silences` giờ rút chỗ ngừng dài hơn 1,5s về 0,9s.

Chấm bằng cách xếp N khoảng lặng dài nhất cạnh N mục tiêu (không dóng từng dấu, vì dóng hay lệch khi giọng có nhiều chỗ ngắt):

| Model | Đạt | Ghi chú |
|---|---|---|
| Piper (2 giọng) | 10–14/15 | Phẩy 0,22–0,24s, `; :` 0,41s, câu ngắn 0,63–0,72s; "…" bị đọc liền nên lệch một vị trí |
| VieNeu v3 | 14/15 | |
| Kokoro (tham số model) | 10/15 | Phẩy ~0,30s vì thư viện dùng một mức cho `, ; :` (đúng thiết kế, có ghi chú) |
| ZeroTTS | 9/15 | Cuối câu, câu hỏi, câu ngắn đạt; vài dấu phẩy model đọc gần liền (<0,08s), không giãn được |
| Supertonic | 8/15 | Đúng phần lớn, phẩy hơi dài (~0,3s) |
| OmniVoice | 8/15 | Model tự nghỉ dao động nhiều; cuối câu đôi khi ~0,45s |

Chưa kiểm bằng tai, chưa thử job EPUB thật và job xuất tách thật; các trường hợp này mới có test tự động.

Ban đầu: chưa làm. Cần pha 1 (`RhythmPlan`) và pha 2 (`ReadingRhythmOptions`).

## Nguyên tắc

Service tính `RhythmPlan` **một lần** ở đầu job, ghi vào `pacing_report.json`, rồi mỗi bước đọc plan để biết tầng nào thuộc mình. Không bước nào tự quyết lại.

## Thay đổi theo bước của pipeline (`service._generate_merged_text`)

| Bước hiện tại | Khi `scope == "full"` |
|---|---|
| 1. Cắt câu theo dấu (`text/punctuation_pauses.py`) | Chỉ cắt tại dấu thuộc tầng `app_split`; `pause_after_ms` lấy ngẫu nhiên trong range (seed). Tầng khác không cắt. |
| 2. Nối chunk (`chunk_join.py`) | Giữ nguyên. Lặng kỹ thuật nằm dưới mức tổng nên bước giãn sẽ bù. Crossfade/nối thẳng đã được phân xử gắn GIỚI HẠN. |
| 3. Nghỉ giữa đoạn gốc (`_paragraph_pause_values`) | Đặt 0. Tầng giữa đoạn do bước 4 đảm nhận (tránh cộng dồn). |
| 4. Nhịp kể chuyện (`narrative_pacing/`) | Chỉ giãn tầng có mechanism `app_stretch`. Tầng `library_param`/`native_token`/`app_split` bị bỏ qua trong `plan_sentence_pauses`. |

Thứ tự 3→4 hiện đã đúng: pacing chạy cuối và chỉ giãn, không rút.

## Thay đổi theo worker

- **Kokoro** (`engines/kokoro_worker/synthesize.py:106`): `kokoro_pause_mode=library` thì truyền `sentence_pause` / `clause_pause` = điểm giữa range (giây) và bước 1 không cắt câu. `app_split` thì giữ `0.0` và cắt câu như hiện nay.
- **Supertonic** (`engines/supertonic_worker/synthesize.py:59`): giữ `silence_duration=0.0`, vì app đã cắt. Không cần sửa.
- **ZeroTTS** (`engines/zerotts_worker/synthesize.py:136`, `zerotts_gguf_worker:238`): `segment_gap_seconds` về mặc định 0,08 khi bị khóa. Giá trị người dùng đã đặt được giữ, chỉ không dùng.
- **OmniVoice** (`src/omni_tts_core/engines/omnivoice_engine.py`): `omnivoice_keep_long_silence=on` (mặc định khi Nhịp đọc bật) thì truyền `postprocess_output=False`. Sau đó app tự cắt lặng đầu/cuối mỗi mẩu và rút lặng bất thường >2s về 1,2s, **trước** bước giãn. `off` thì giữ hành vi thư viện như hiện nay. Nhịp đọc tắt: không đổi gì.
- **Higgs**: khi plan cho `native_token`, dùng dialect `authoring/dialects/higgs.py` để chèn token trước khi gửi. Pacing vẫn bù phần thiếu.
- **Remote CPU** (`colin_remote_compute/piper.py`, ZeroTTS remote): gửi kèm tham số mới. Worker cũ không hiểu tham số thì phân xử hạ xuống APP (khai báo khả năng trong profile thiết bị).

## Chế độ khác

- **Tách đoạn (split)**: các tầng trong câu và cuối câu vẫn chạy. Pacing hiện bỏ qua split, nên cần bật riêng `plan_sentence_pauses` cho từng file tách (mỗi file là một unit).
- **EPUB** (đã chốt: dùng Nhịp đọc):
  - Hiện `pacing_on = ... and source_units is None` (`service.py:783`) loại EPUB. Bỏ điều kiện này khi `scope == "full"` và truyền thêm danh sách ranh giới EPUB.
  - Ranh giới có `SourceUnit.pause_kind` (title/chapter/scene/volume) là **ranh giới khóa**: pacing không giãn, không đặt `section`, không đặt nhạc ở đó. Nghỉ và nhạc chương giữ nguyên theo `EpubOptions`.
  - Ranh giới đoạn thường trong chương nhận các tầng `connector`…`subtopic`. Bước 3 (nghỉ giữa đoạn gốc) đặt 0 như job TXT.
  - `plan_structure` chạy **riêng từng chương** để topic_shift không so từ vựng qua hai chương. Tầng `section` vẫn KHÔNG ÁP DỤNG.
  - Sau khi giãn, dịch SRT, mốc chương (`chapters.txt`, metadata chương MP3/M4B nếu có) và báo cáo nhạc chương theo `PacingResult.remap`.
  - Rủi ro: file EPUB dài nhiều giờ. Cần đo thời gian và bộ nhớ của `SilenceMap` trên audio 10 giờ. Nếu quá lớn, xếp nhịp theo từng chương trước khi ghép.

## Tiêu chí

- [ ] Test tích hợp với engine giả: mỗi tầng chỉ được một bước thay đổi (đếm insert trong report).
- [ ] Đo lại bằng script pha 0 khi bật Nhịp đọc: ≥90% dấu cuối câu và ≥80% dấu phẩy nằm trong `[min − 60ms, max + 120ms]` cho mọi model không GIỚI HẠN.
- [ ] Nhịp đọc tắt: job mẫu ZeroTTS và Piper cho thời lượng và hash như trước thay đổi.
- [ ] `pacing_report.json` có `rhythm_plan` (tầng, bên đảm nhận, range, switch, số lần áp).
- [ ] EPUB mẫu 3 chương: nghỉ chương/cảnh và nhạc chương giữ đúng giá trị EPUB; mốc chương và SRT lệch < 50ms so với audio mới.
- [ ] OmniVoice bật "Giữ khoảng lặng dài": đo cuối câu đạt range; không còn lặng >2s.
