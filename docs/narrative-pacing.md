# Nhịp đọc & nhạc chuyển

Dùng cho bài đọc dài (podcast, bình sách, sách nói). Đủ tầng và nhạc khi xuất
**TXT/MD/SRT thành một file ghép**. Xuất tách từng file chỉ có các tầng trong
câu. Với EPUB, Nhịp đọc lo các tầng trong câu và giữa đoạn; tên chương, chương,
cảnh và nhạc chương vẫn theo mục Đọc sách EPUB.

## Nhịp đọc theo model

Một bộ khoảng nghỉ dùng chung cho mọi model, tính theo **tổng khoảng lặng nghe
thấy**. Mỗi tầng có Min–Max (Min = Max là cố định). Đổi model không đổi các con
số; chỉ đổi **ai làm** khoảng nghỉ đó. Mỗi dòng trong Qt có một nhãn:

| Nhãn | Nghĩa |
|---|---|
| MODEL | Thư viện của model làm, app truyền đúng con số vào (Kokoro), hoặc token trong kịch bản (Higgs) |
| APP | App làm: cắt câu rồi chèn đúng khoảng lặng (Piper, Supertonic), hoặc giãn khoảng lặng có sẵn sau khi ghép |
| MODEL TỰ LO + APP BÙ | Model có mức nghỉ riêng không chỉnh được (VieNeu v3 cuối câu ~0,5s), app chỉ bù phần thiếu |
| GIỚI HẠN | Chỉ làm được một phần, có ghi lý do (ZeroTTS đổi `;` thành `,`, Chatterbox đổi `…` `:`, nối chunk kiểu crossfade) |
| KHÔNG ÁP DỤNG | Chế độ xuất hiện tại không có tầng này (xuất tách: giữa đoạn; EPUB: chuyển mục, nhạc) |
| TẮT | Bạn đã tắt tầng đó |

**Phạm vi**
- *Chỉ nhịp kể chuyện*: mục Ngắt nghỉ theo dấu câu, Nghỉ giữa đoạn gốc vẫn chạy
  như cũ; Nhịp đọc chỉ giãn thêm.
- *Toàn bộ ngắt nghỉ*: Nhịp đọc chọn đúng một bên cho mỗi tầng và khóa các mục
  cũ trùng việc (Ngắt nghỉ theo dấu câu, Nghỉ giữa đoạn gốc, Khoảng lặng giữa
  đoạn của ZeroTTS). Giá trị cũ được giữ, tắt Nhịp đọc là dùng lại được.

**Tùy chọn riêng theo model** (chỉ hiện khi model đó đang chọn)
- Kokoro – *Cách ngắt nghỉ*: Tham số model (mặc định, đọc liền mạch, mỗi nhóm
  dấu một mức) hoặc App cắt câu (có dao động Min–Max).
- OmniVoice – *Giữ khoảng lặng dài* (mặc định bật): tắt bước rút lặng của
  OmniVoice (bản 0.2.1 rút mọi khoảng lặng dài hơn 0,5s về tối đa ~1s); app tự
  rút những chỗ ngừng bất thường dài hơn 1,5s.

Đổi model, Nhật ký hệ thống ghi tầng nào đổi nhãn. Preset có sẵn: Podcast tự
nhiên, Đọc chậm / sách nói, Nhanh / tin tức. Nút *Lấy từ cài đặt cũ* đề xuất
khoảng nghỉ từ mục cũ (cộng thêm khoảng lặng model tự có, vì mục cũ tính lặng
chèn thêm). Số đo từng model: `plans/2026-11-10-nhip-doc-theo-nang-luc-model/`.

## Vấn đề nó giải quyết

Bản ghép mặc định nghỉ cùng một khoảng ở mọi chỗ chuyển đoạn. Nhiều engine
cũng cho dấu chấm nghỉ ngắn y như dấu phẩy. Nghe cả tiếng đồng hồ sẽ thấy đều
đều, không biết đâu là chỗ chuyển phần, và cũng không có chỗ để chèn nhạc.

Ví dụ một job 1:58 có 318 chỗ chuyển đoạn, chỗ nào cũng nghỉ đúng 0,28s; dấu
chấm và dấu phẩy đều chỉ nghỉ khoảng 0,2–0,3s.

## Cách hoạt động

Sau khi ghép xong PCM, Core chỉ **chèn thêm thời gian vào những khoảng lặng có
sẵn**, không cắt vào chữ nào. SRT được dịch theo cùng timeline.

| Tầng | Nhận biết (tiếng Việt / tiếng Anh) | Mặc định |
|---|---|---|
| Nối ý | Đoạn sau mở bằng "Bởi vậy", "Nhưng", "Như vậy"… / "So,", "But", "In other words", "Therefore"… | 0,60s |
| Đoạn thường | Không thuộc tầng nào khác | 0,85s |
| Sau câu hỏi | Đoạn trước kết bằng "?" | 1,00s |
| Câu ngắn chốt ý | Một trong hai đoạn ngắn dưới 90 ký tự | 1,05s |
| Chuyển ý | "Trước hết", "Từ đây", "Câu hỏi thứ…", "Điểm thứ…" / "First", "Next", "Now", "Let's turn to", "Moving on"… | 1,30s |
| **Chuyển mục** | Chủ đề đổi rõ (xem dưới), không có nhạc | 2,0s |
| Chuyển phần | Nhạc ngắn (~5s) | xem "Nhạc chuyển" |
| Bước ngoặt lớn / kết | Nhạc dài (~10s) | xem "Nhạc chuyển" |

- **Ngôn ngữ:** bộ từ dấu hiệu có tiếng Việt và tiếng Anh (cả mốc đặt nhạc,
  câu giới thiệu series "Welcome…/This is…/podcast", câu kết "Thanks for
  listening/That's all for today", cụm chuyển chủ đề "moving on to/which brings
  us to"). Ngôn ngữ `auto` được đoán từ văn bản: có chữ riêng của tiếng Việt
  (đ, ư, ơ, dấu thanh…) là tiếng Việt, còn lại chữ Latin là tiếng Anh. Ngôn ngữ
  khác chỉ dùng các tầng theo dấu câu, câu hỏi và độ dài.
- Năm tầng đầu nhân theo độ dài đoạn trước (`paragraph_length_scaling`): đoạn
  ngắn 0,9×, đoạn dài từ 600 ký tự 1,15×. Người đọc thật nghỉ lâu hơn sau đoạn dài.
- Mỗi khoảng nghỉ (trừ tầng nối ý) có dao động ±70ms để không đều như máy.
- **Trong đoạn:** dấu câu được dóng với khoảng lặng thật (DP theo tốc độ đọc).
  Nghỉ sau `.` `!` kéo tới 0,52s, `?` 0,62s, `:` `;` 0,38s. Nếu câu trước hoặc
  câu sau ngắn (≤32 ký tự, kiểu "Con người ấy là ai? Chính là bản thân chúng
  ta.") thì nghỉ 0,70s (`short_sentence_pause_ms`). Dấu phẩy chỉ có mức sàn
  0,20s (`comma_min_pause_ms`, 0 = giữ nguyên), và chỉ áp cho khoảng lặng
  ≥0,12s đã dò được.

**Căn cứ các mức mặc định.** Nghiên cứu về giọng đọc cho thấy nghỉ giữa câu bằng
khoảng 0,7 lần nghỉ giữa đoạn. Nghỉ giữa đoạn khoảng 0,4–1,3s với người đọc
nhanh, 0,75–1,8s với người đọc chậm, và dài hơn khoảng 1,2 lần sau đoạn dài.
Thử nghiệm nghe cho thấy nghỉ giữa câu 0,6–1,2s nghe tự nhiên nhất. Giọng
zerotts huuduc đọc khoảng 4,4 âm tiết/giây, tức là nhanh, nên các mức trên được
đặt ở nửa dưới của các khoảng đó.

### Tầng chuyển mục

Kịch bản thường là các đoạn phẳng, không có tiêu đề. Core chấm điểm mỗi ranh
giới đoạn (`topic_shift.py`):

- **Độ gắn kết từ vựng** (kiểu TextTiling): so từ/cụm hai âm tiết của 3 đoạn
  trước với 3 đoạn sau. Chỗ "thung lũng" sâu là chỗ đổi chủ đề. Điểm này tính
  theo bách phân vị nên bài dài hay ngắn đều so được.
- **Cộng điểm** khi đoạn sau mở bằng mốc ("Trước hết", "Bây giờ", "Đến đây"…)
  hoặc câu đầu có "chuyển sang", "trở về với", "bổ sung", "một điểm nữa"…
- **Trừ điểm** khi đoạn sau mở bằng từ nối ("Bởi thế", "Đó là", "Như vậy"…).

Nhạc chuyển lấy các ranh giới điểm cao nhất (gần mỗi `interval_minutes`). Chuyển
mục lấy các ranh giới điểm cao tiếp theo (điểm ≥ 1,0), khoảng một chỗ mỗi
`section_interval_minutes` (mặc định 3,5 phút), cách nhau và cách nhạc ít nhất
0,45 khoảng đó. Tự chọn bằng `section_before_units`; tắt bằng
`sections_enabled=false`.

## Nhạc chuyển giao thoa

Có hai loại nhạc chuyển, theo mục đích:

| Loại | Dùng khi | Nghe được | Fade-in / chỉ nhạc / fade-out | Nguồn |
|---|---|---|---|---|
| **Ngắn** (sting) | Sang phần mới, khoảng mỗi `interval_minutes` (10') | ~5s | 1,0s / ~2–3s / 1,6s | Kho nhạc ngắn 4–6s |
| **Dài** (bumper) | Bước ngoặt lớn của tập, khoảng mỗi `major_interval_minutes` (30'), và luôn có ở câu kết | ~10s | 1,5s / 6s / 2,5s | `major_track_ids` / `major_theme`, mặc định là một đoạn trích từ theme series |

Nhạc ngắn không phát riêng quá `max_solo_ms` (3s), kể cả khi bản nhạc dài hơn.
Nguồn nhạc dài theo thứ tự ưu tiên: `major_track_ids`, rồi nhóm `major_theme`
(ví dụ `chuyen-chuong`), rồi đoạn trích theme series. Các bản nhạc dài được xoay
vòng, không lặp lại trong một tập. Bản có tag `closing` được giữ cho câu kết.

Thư viện riêng có sẵn hai nhóm, tạo bằng ElevenLabs gói Free nên chỉ được dùng
phi thương mại:
- `binh-sach`: 8 nhạc ngắn 6,7–8,7s, nhạc cụ cổ cầm, tiêu, tranh, tỳ bà, nhị
  hồ, chuông, sáo trúc.
- `chuyen-chuong`: 4 nhạc dài 16–18s, gồm Thư phòng, Đại Quan Viên, Mộng hoa
  hư ảo và Tạm biệt (có tag `closing`).

Loại dài lấy những chỗ có điểm chuyển chủ đề cao nhất trong số chỗ đặt nhạc. Các
chỗ đó cách nhau ít nhất 0,6 × `major_interval_minutes`. Tự chọn bằng
`major_before_units`; tắt bằng `major_enabled=false`. Phần chỉ có nhạc của loại
dài bị giới hạn bởi độ dài bản nhạc. Kho hiện chỉ có theme mở/kết (20s) đủ dài
cho loại này.

Mỗi đoạn nhạc chuyển có ba pha:

- **Fade-in:** nhạc dâng dưới chữ cuối của đoạn trước, từ -40 lên -15 dB.
- **Phần chỉ có nhạc:** nhạc lên mức đầy trong 0,5s sau khi giọng dứt.
- **Fade-out:** đoạn sau bắt đầu đọc khi nhạc vẫn còn, rồi nhạc lặn từ -14 xuống
  -45 dB.

Mức nhạc được tính theo độ to của giọng (mặc định nhỏ hơn giọng 3,5 dB).

**Vị trí đặt nhạc**
- **Hook đầu không bao giờ có nhạc.**
- **Theme series** (`theme_track_id`) vào ở câu giới thiệu series ("Đây là…",
  "podcast", "kênh"…). Nếu không tìm thấy câu như vậy, theme vào ở ranh giới
  đầu tiên sau `hook_min_seconds`. Theme có khoảng 3,5s chỉ nghe nhạc, sau đó
  làm nền -16 dB dưới câu dẫn rồi tắt trong khoảng 11s.
- **Nhạc chuyển tự đặt:** khoảng mỗi `interval_minutes` phút có một đoạn, ưu
  tiên các mốc "Bây giờ / Trở lại / Đến đây / Vậy nếu / Trước khi…". Nếu cả
  khung không có mốc phù hợp thì bỏ qua, không ép nhạc vào giữa ý. Câu kết
  ("tạm khép lại", "hẹn gặp lại") luôn có một đoạn nhạc chuyển.
- **Tự chọn vị trí:** gửi `bridge_before_units` (số đoạn, bắt đầu từ 2). Khi
  có danh sách này, chế độ tự đặt bị tắt. `auto_bridges=false` nghĩa là chỉ dùng
  đúng danh sách, kể cả khi danh sách rỗng. `bridge_tracks` gán bài cho từng chỗ,
  dạng `{số đoạn: track_id}`. Dùng `plan_narrative_pacing` để xem trước.
- **Skill `narrative-pacing`** (ở `~/.claude/skills/`) dành cho agent: đọc kịch
  bản, lập `plan.json` để người dùng duyệt, chọn hoặc tạo nhạc (ElevenLabs),
  render, rồi xuất bảng chia và file nghe thử nhạc.
- **Nhạc kết:** theme dâng lên dưới câu cuối rồi chơi hết bài.

Nguồn nhạc chuyển dùng chung thư viện `music_library/`: bản cố định, random
theo chủ đề, random trong tập đã tích hoặc theo preset. Nhóm `mo-ket` (Nhạc
mở / kết series) chứa các theme dài 15–30s.

## Dùng ở đâu

- **Qt:** trong Studio, mở mục **Nhịp đọc & nhạc chuyển**.
- **MCP:** `describe_reading_rhythm(model_id, pacing?, output_mode?, source_kind?)`
  xem nhãn từng tầng trước khi gửi job; `get_generation_contract` có khối `rhythm`.
- **MCP:**
  - `generation.pacing` khi gọi `start_text_generation` / `start_file_generation`.
  - `plan_narrative_pacing(srt_file, pacing)` để xem trước vị trí nhạc.
  - `pace_existing_audio(audio_file, srt_file, pacing)` để xếp nhịp lại một
    file đã tạo. Lệnh chạy đồng bộ; file 2 giờ mất khoảng 1 phút.

**File xuất ra**
- Khi tạo giọng: `pacing_report.json` (kèm danh sách chapter) nằm trong thư
  mục job.
- Khi dùng `pace_existing_audio`: `*_paced.mp3`, `*_paced.srt`, `chapters.txt`
  và `pacing_report.json`.

## Lưu ý

- Muốn nhạc mở đầu đúng chỗ thì văn bản nên có một đoạn giới thiệu series
  riêng, tách khỏi đoạn hook.
- Nhạc tạo bằng ElevenLabs gói Free (`commercial_use_permitted: false`) chỉ
  dùng cá nhân. Kênh có kiếm tiền cần nhạc có quyền thương mại.
- Thời lượng thường tăng khoảng 5%. Ví dụ job 1:58 nói trên thành khoảng 2:03.
