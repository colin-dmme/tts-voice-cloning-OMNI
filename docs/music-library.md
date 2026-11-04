# Thư viện nhạc, tập chọn và preset

Colin dùng thư viện cục bộ `music_library/`. Từ 0.6.4, Qt có tab **Nhạc** sau
tab **Giọng** để phối nhiều nhóm/bài và lưu preset. Trong Studio có bốn cách
chọn nguồn: một bản cố định, random trong một chủ đề, random trong tập đã tích
hoặc random theo preset đã lưu. Tkinter, Web và MCP dùng cùng cấu hình nguồn.

Random trộn hết tập bài trước khi lấy lượt tiếp theo và tránh lặp sát nhau khi
có ít nhất hai bản. Mỗi khoảng nghỉ đủ điều kiện nhận một lựa chọn; nếu bật cả
sau tiêu đề và giữa chương, hai vị trí đều tham gia lượt trộn. Một nhóm chỉ có
một bài sẽ lặp bài đó. Nhóm trống/thiếu hoặc file bị mất báo lỗi trước khi tạo
giọng, không tự lấy nhạc ngoài nhóm.

**Lượt trộn** là số lưu trong thiết lập. Cùng EPUB, phạm vi chương, danh sách nhạc
và lượt trộn cho cùng lựa chọn; Qt/Tkinter có nút **Đổi lượt trộn**, Web cho đổi
số trực tiếp. Nghe thử random chỉ bốc một mẫu để nghe, không thay lượt trộn của
tác vụ. Nếu đổi phạm vi chương, nhóm, seed hoặc file nhạc, cache được tính lại.

## Tab Nhạc: phối nhiều nhóm và lưu preset

1. Vào **Nhạc → Tạo mới**. Tích các nhóm ở cột chủ đề, ví dụ Tam Quốc + Kiếm
   hiệp. Các bài thuộc nhóm được tích trong bảng; bài trùng nhiều nhóm chỉ
   xuất hiện và tham gia random một lần.
2. Có thể tích thêm bài ngoài nhóm hoặc bỏ tích một số bài không phù hợp.
   Tìm theo tên/tag/nhạc cụ/mô tả; **Chỉ xem các bản đã tích** giúp rà lại tập
   nhạc. Tìm kiếm chỉ ẩn dòng, không làm mất lựa chọn ở các dòng khác.
3. **Tích các bản đang hiển thị** và **Bỏ tích đang hiển thị** tác động đúng
   những dòng đang thấy. **Bỏ toàn bộ** xóa cả lựa chọn nhóm, bài và loại trừ.
4. Đặt tên, mô tả hoàn cảnh dùng, rồi **Lưu preset**. Có thể cập nhật, **Lưu
   bản sao** hoặc **Xóa preset**; xóa preset giữ nguyên file nhạc.
5. Bấm **Dùng preset đã lưu trong Studio** để dùng preset; nút khóa nếu đang
   có thay đổi chưa lưu. Hoặc **Dùng tập đang tích trong Studio** để dùng trực
   tiếp lựa chọn hiện tại mà không cần tạo preset.
6. Trong Studio, chọn **Loại nghỉ → Nhạc** ở vị trí cần phát. Thời lượng,
   fade, âm lượng và lượt trộn chỉnh tại Studio; preset chỉ chứa tập bài.

**Nghe bản đang chọn** phát trọn bản trong thư viện. **Sửa mô tả / tag…** cho
sửa tên, mô tả, chủ đề và tags; không thay audio hoặc nguồn/quyền sử dụng.
**Thêm nhạc…** nhập audio riêng, sau đó sửa chủ đề để đưa vào nhóm mong muốn.
**Làm mới** nạp lại catalog/preset khi có thay đổi từ MCP hoặc giao diện khác.

Quy tắc lưu gồm ba danh sách:

| Trường | Ý nghĩa |
|---|---|
| `theme_ids` | Hợp bài từ các nhóm được tích; tự nhận thêm bài nhập vào nhóm sau này |
| `track_ids` | Bài chọn riêng, bổ sung ngoài các nhóm |
| `excluded_track_ids` | Bài bị bỏ tích, luôn bị loại kể cả khi thuộc nhóm đã chọn |

Tập cuối = hợp các nhóm và bài riêng, bỏ trùng, rồi trừ các bài bị loại. Muốn
giữ chính xác một danh sách cố định, không tích nhóm mà chỉ tích từng bài.
Preset lưu trong `music_library/presets.json` và dùng chung giữa các giao diện.
Sao lưu cả thư mục thư viện khi chuyển máy.

Sửa tập bài của preset làm hàng đợi/cache kiểm tra lại ở lượt chạy sau; đổi tên
hoặc mô tả đơn thuần không buộc tạo lại audio. Tác vụ đang chạy giữ kế hoạch ID
đã chốt, không đổi nhạc giữa chừng khi preset bị sửa/xóa. Preset bị thiếu hoặc
tập chọn rỗng báo lỗi để chọn lại, không tự chuyển sang toàn bộ thư viện.

## Cắt theo nhịp hoặc phát trọn bản

Từ 0.6.3, phần EPUB có hai khối **Sau tên chương, trước nội dung** và **Giữa
hai chương**. Mỗi khối tự chọn **Loại nghỉ**: **Không nghỉ**, **Khoảng lặng**,
hoặc **Nhạc**. Không nghỉ khóa toàn bộ thời gian/fade; khoảng lặng chỉ mở số
giây; nhạc mở thêm độ dài nhạc và fade-in/fade-out riêng cho vị trí đó.

Khi chọn **Nhạc**, trong **Độ dài nhạc** chọn một trong hai chế độ:

- **Số giây cố định** (`fit_pause`, mặc định): cắt/fade đúng nhịp đã đặt;
  bản ngắn hơn được đệm im lặng, không làm đổi tổng thời lượng.
- **Phát trọn bản nhạc** (`full_track`): phát đủ bản trong thư viện được chọn,
  thêm fade đầu/cuối và tự lấy độ dài bản nhạc làm độ dài nhịp. Ví dụ nhịp đặt
  3 giây nhưng bản nhạc dài 6 giây thì nhịp có nhạc dài 6 giây; nếu bài dài 2
  giây thì nhịp dài 2 giây. Áp dụng cho bản cố định, random và agent chỉ định.

Ở chế độ phát trọn, ô số giây bị khóa, không giới hạn nhạc và không cộng thêm
khoảng lặng. Fade chỉ mở khi dùng nhạc; nếu tổng fade dài hơn bài/nhịp thì tự
co cho vừa. Tắt đọc tiêu đề sẽ khóa toàn bộ khối sau tên chương; tắt đọc tên
quyển sẽ khóa nghỉ sau tên quyển. **Nguồn nhạc cho các nhịp nghỉ** gồm bài/nhóm,
lượt trộn và âm lượng, chỉ mở khi có vị trí đang dùng nhạc.

WAV/MP3 và SRT dùng cùng số mẫu PCM thực tế, kể cả khi sample rate của model
khác sample rate thư viện. **Nghe thử nhịp này** phát đúng độ dài và fade của
vị trí đó. Không nghỉ/vị trí không bật nhạc sẽ không phát. 0 giây chỉ tắt nhịp
cố định; ở phát trọn, số giây không áp dụng. Nhạc hiện chỉ phát giữa chương/sau tên chương.
Nhạc nền dưới lời kể trong chương được để cho nâng cấp sau.

"Phát trọn" là trọn bản WAV đã nhập trong thư viện. Bộ nhập vẫn lấy tối đa 30
giây, trim im lặng và cân mức âm như trước. Các file nhạc chuyển chương hiện
có dài vài giây nên được phát đầy đủ; file nguồn dài hơn 30 giây chỉ có đoạn
đã nhập, không tự nạp lại file gốc khi đọc sách.

## File mô tả đi kèm

- `library.json` là catalog máy đọc, mỗi bản có ID, file, thời lượng, SHA-256,
  `description` (mô tả và cảnh gợi ý), `themes` (nhóm thể loại), `tags` (tâm trạng,
  nhạc cụ, tình huống) và provenance nguồn/quyền sử dụng.
- `MUSIC_CATALOG.md` là bản mô tả dễ đọc, tự cập nhật sau nhập nhạc hoặc sửa
  metadata, nằm cạnh WAV trong cùng thư mục. Catalog v1 được đọc với metadata
  mới mặc định rỗng, không buộc nhập lại nhạc cũ.
- `themes` dùng ID chữ thường không dấu, ví dụ `tam-quoc`, `tien-hiep`,
  `huyen-huyen`, `ngon-tinh`, `kiem-hiep`, `co-trang`, `co-phong`. Một bản có thể thuộc nhiều
  nhóm. Random dựa vào `themes`; tag không tự làm bài thuộc một nhóm.
- `presets.json` chứa tên/mô tả preset, các nhóm/bài đã tích và các bài loại trừ.
  File này thuộc thư viện riêng; không chứa thiết lập model, nhịp nghỉ hoặc fade.
- Chép MP3 vào thư mục vẫn cần nhập bằng **Thêm nhạc…** hoặc MCP; không tự quét.
  Sao lưu cả WAV, `library.json`, `MUSIC_CATALOG.md` và `presets.json` khi chuyển máy.

Các mô tả là định hướng khi tạo/biên mục; agent nên nghe mẫu, đọc nội dung trước
khi chọn nhạc cho cảnh cụ thể. Metadata không tự phân tích nội dung sách hoặc
đổi nhạc theo cảm xúc. Nhạc và API key riêng không được đưa vào Git hay gói mã.

## MCP cho AI agent

Mở lại kết nối MCP sau nâng cấp. `get_generation_contract` công bố các trường
mới qua schema EPUB dùng chung mọi model.

1. `list_chapter_music(theme="tam-quoc")`: trả mô tả, tags, các nhóm và đường dẫn
   catalog. Có thể thêm `tag` để lọc tình huống/nhạc cụ.
2. `import_chapter_music` nhận `source_file`, `name`, `description`, `themes`,
   `tags`. `update_chapter_music_metadata` cập nhật tên/metadata theo `track_id` mà
   không thay audio/provenance; giá trị `null` giữ nguyên, `[]` xóa nhóm/tag.
3. `plan_epub_music` nhận `source_file` và đối tượng `epub`; trả mỗi nhịp, độ dài,
   chương, lựa chọn, metadata/hash bản nhạc. Không gọi TTS hoặc provider nhạc.
4. Gửi cùng đối tượng `epub` vào `start_file_generation` qua `generation.epub`.

### Tạo và dùng preset qua MCP

`list_chapter_music_presets` trả ID, tên, mô tả và đầy đủ quy tắc chọn của từng
preset. `save_chapter_music_preset` nhận ví dụ:

```json
{
  "name": "Tam Quốc phối kiếm hiệp",
  "description": "Nhịp chuyển chương truyện chiến trận và giang hồ.",
  "theme_ids": ["tam-quoc", "kiem-hiep"],
  "track_ids": [],
  "excluded_track_ids": ["co-tran-chieu-mua"]
}
```

Tool trả `preset_id`. Khi cập nhật, gửi ID đó cùng **toàn bộ** các danh sách và
mô tả muốn lưu; danh sách bỏ qua là rỗng, không phải giữ giá trị cũ. Dùng
`delete_chapter_music_preset(preset_id=...)` để xóa preset mà giữ các file nhạc.

Đặt trong `generation.epub.music`:

```json
{
  "selection_mode": "preset",
  "preset_id": "mix-id-tra-ve-tu-tool-luu",
  "random_seed": 42,
  "volume_percent": 30
}
```

Hoặc gửi trực tiếp tập chọn mà không lưu preset:

```json
{
  "selection_mode": "random_selection",
  "theme_ids": ["tam-quoc", "kiem-hiep"],
  "track_ids": ["tien-hiep-van-son"],
  "excluded_track_ids": ["co-tran-chieu-mua"],
  "random_seed": 42,
  "volume_percent": 30
}
```

Các ID ví dụ cần tồn tại trong thư viện máy đang chạy; đọc catalog trước khi
gửi. `resolve_chapter_music_selection` nhận `{"music": {...}}`, trả chính xác
tập bài sau khi hợp/loại trừ cùng snapshot preset, không tạo giọng/nhạc.
`plan_epub_music` dùng cùng nguồn, ghi `candidate_track_ids`, `selection_rules`,
`preset_id`/`preset_name` và bài được chọn ở từng nhịp. Agent vẫn có thể chỉ
định nhạc theo nội dung bằng `track_overrides` như bên dưới.

Ví dụ cấu hình trong `generation.epub` (sau tiêu đề im lặng 1 giây, giữa chương phát trọn nhạc):

```json
{
  "music": {
    "selection_mode": "random_theme",
    "theme": "tam-quoc",
    "random_seed": 42,
    "volume_percent": 30,
    "track_overrides": {
      "title:2": "tam-quoc-muu-luoc",
      "chapter:2": "tam-quoc-xuat-tran"
    }
  },
  "breaks": {
    "title": {"mode": "silence", "duration_ms": 1000},
    "chapter": {
      "mode": "music",
      "duration_mode": "full_track",
      "fade_in_ms": 250,
      "fade_out_ms": 750
    }
  }
}
```

`title:N` là nhịp **sau khi đọc tên chương N**. `chapter:N` là nhịp **hết nội dung
chương N**, trước chương tiếp theo. N là vị trí 1-based trong sách được Colin
nhận diện, không phải số in trên tiêu đề. Khi chỉ đọc một phần, N vẫn giữ vị trí
gốc. Chương cuối trong phạm vi không có nhịp chuyển chương cuối.

Chỉ định của agent ưu tiên hơn random và có thể chọn bài ngoài nhóm nếu phù hợp
nội dung; các vị trí còn lại tiếp tục theo nhóm. Chỉ định không tạo thêm nhịp:
các nhịp chọn không nghỉ hoặc khoảng lặng không phát nhạc. Mỗi ID/file được dùng phải có thật. Tạm
thời đây chỉ là lựa chọn cho nhịp nghỉ; không có tự động gắn nhạc nền trong lời.

Kết quả có `music_plan_path` trỏ tới `<tên>-music-plan-<hash>.json` cạnh audio;
job cũng giữ `chapter-music-plan.json`. File ghi lựa chọn chính xác, nguồn/hash
và seed để kiểm tra hoặc chạy lại. Checkpoint dùng cả lựa chọn và hash âm thanh,
nên không tái dùng nhầm chương sau khi đổi file nhạc đã được chọn.

Plan ghi `configured_pause_ms` là nhịp nhập ban đầu, `duration_ms` là độ dài sẽ
dùng theo chế độ (với phát trọn là độ dài file; khi resample có thể lệch dưới
một mẫu PCM). `preview_chapter_music` nhận `duration_mode`, trả `duration_ms`
theo độ dài WAV thực xuất. Thiết lập nguồn nhạc của tác vụ nằm trong
`generation.epub.music`, thiết lập từng nhịp nằm trong `generation.epub.breaks`;
không gửi các trường này vào thông số model.

Với 0.6.3, `generation.epub.breaks.title/chapter` quản lý thời lượng/fade từng
vị trí; `music` quản lý nguồn nhạc, âm lượng, random và agent overrides. Mỗi
`breaks.<vị trí>` đã có sẽ được ưu tiên hơn `title_pause_ms/chapter_pause_ms` và
các cờ/thời lượng/fade cũ trong `music`. Các vị trí chưa có khóa mới tiếp tục
đọc cấu hình cũ; `music.enabled=false` không tắt một vị trí đã chọn Nhạc bằng
`breaks`. Khi tất cả vị trí là không nghỉ/khoảng lặng, nguồn nhạc cũ không còn
tác dụng và không được nạp chỉ vì cấu hình còn giữ ID.
