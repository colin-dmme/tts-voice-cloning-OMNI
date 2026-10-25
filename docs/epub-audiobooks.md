# Đọc EPUB thành audiobook trong Colin TTS 0.6.1

EPUB dùng cùng core, model, profile giọng và preset cách đọc với TXT/SRT. Các
khoảng nghỉ sách được chèn vào PCM sau tổng hợp; không gửi thẻ pause vào model.

## Dùng trên giao diện

- Qt: chọn **Nhập EPUB…**, xem danh sách chương và nội dung trích, chọn khoảng
  chương rồi **Thêm vào hàng đợi**. Chỉnh lại ở mục **Đọc sách EPUB** bên phải.
- Tkinter: tab **Xử lý file**, nút **Nhập EPUB / chỉnh nhịp…** mở cùng các lựa
  chọn và bản xem trước; thêm sách vào hàng đợi rồi chạy như file thông thường.
- Web: tải EPUB vào File nguồn, mở **Đọc sách EPUB — chương và khoảng nghỉ**.
  Nút **Xem trước EPUB** chỉ trích chữ, không nạp model hoặc tạo giọng.

Khoảng chương dùng vị trí trong danh sách (bắt đầu từ 1), không suy đoán từ số
ghi trong tên. Đến chương = 0 nghĩa là hết sách. Thiết lập áp dụng cho các EPUB
trong lượt chạy; không thay đổi cách tách đoạn TXT/MD/SRT.

### Các khoảng nghỉ

| Thiết lập | Mặc định |
|---|---:|
| Sau tên chương, trước nội dung | 1,2 giây |
| Hết chương, trước tên chương kế | 2,5 giây |
| Chuyển cảnh | 1,2 giây |
| Sau tên quyển | 1,8 giây |

Có thể đặt từ 0 tới 10 giây; 0 là không chèn. Nghỉ giữa các đoạn văn vẫn theo
thiết lập chung. Mỗi ranh giới chỉ dùng một loại nghỉ, không cộng thêm nghỉ đoạn.
Đây là khoảng lặng chèn thêm; giọng có thể còn khoảng im lặng tự nhiên đầu/cuối.

EPUB nhận diện thứ tự từ spine, tên chương từ heading và nhãn mục lục, bỏ bìa,
điều hướng, chú thích/đánh số trang có semantic markup. Nội dung inline và xuống
dòng `br` được giữ khi lấy chữ. `p.scene` chứa dấu phân cảnh và `hr` chuyển thành
nhịp nghỉ; dấu ba chấm trong lời thoại vẫn được giữ trong văn bản.

## Audio, SRT và tiếp tục

Chọn **Mỗi chương một file** hoặc **Ghép một file** trong phần EPUB. Lựa chọn
**Tách mỗi đoạn/dòng SRT** của đầu ra thông thường không áp dụng cho sách.
Chọn WAV/MP3 và bật **Xuất kèm SRT** ở Đầu ra; chọn audio-only vẫn được hỗ trợ.

Mỗi chương có SRT bắt đầu từ 0; bản ghép dịch toàn bộ cue theo độ dài PCM thực
tế của các chương trước, bao gồm khoảng nghỉ. Khoảng lặng không tạo cue phụ đề
giả. SRT có độ chi tiết theo các đoạn/chunk hiện có của core, không phải forced
alignment theo từng từ. Khoảng nghỉ chuyển chương nằm cuối chương trước và
chỉ chèn khi còn chương tiếp theo trong phạm vi đã chọn.

Đầu ra nằm trong `<tên sách>-audio/`. `.colin-epub/` chứa WAV trung gian và
checkpoint: chạy lại cùng file, giọng và thiết lập sẽ dùng lại chương đã hoàn
tất. Đổi nguồn hoặc thiết lập tạo cache khác. Khi hủy/lỗi, chương đã hoàn tất
được giữ. Không xóa `.colin-epub/` nếu còn muốn tiếp tục hoặc ghép lại.

Ghép sách ghi PCM theo luồng để không giữ toàn bộ audiobook trong RAM. WAV ghép
dùng RF64 để hỗ trợ vượt 4 GB; trình phát cần hỗ trợ RF64. MP3 cần ffmpeg trong
PATH và được mã hóa từ PCM một lần, không ghép lại MP3 đã nén.

## Nhạc chuyển chương

Trong phần EPUB, mở **Nhạc đệm trong khoảng nghỉ**, bật nhạc và chọn bản nhạc.
Chọn phát **giữa hai chương**, **sau tên chương trước nội dung**, hoặc cả hai.
Âm lượng mặc định 30%; có nút nghe thử đúng độ dài nhịp chuyển chương hiện tại.
Nếu nhịp đang bằng 0, không chèn nhạc. Nhạc không phát dưới phần lời kể.

Colin tự cắt đoạn nhạc, thêm fade-in/fade-out và đổi sample rate theo model.
Nhạc chiếm đúng số mẫu PCM của nhịp nghỉ; không cộng thêm thời lượng, không đổi
văn bản gửi tới model và không tạo caption giả trong SRT. File ngắn hơn nhịp
được đệm im lặng, không lặp giai điệu hoặc time-stretch làm méo nhạc. Fade quá
dài được co theo nhịp ngắn. Mặc định fade-in 120 ms, fade-out 350 ms.

**Thêm nhạc…** nhận WAV/MP3/FLAC/OGG/M4A tối đa 100 MB, lấy tối đa 30 giây,
trim im lặng đầu/cuối và cân mức âm. Thư viện nằm tại `music_library/` trong
workspace, tách khỏi Git. Giữ thư mục này khi chuyển máy để giữ lựa chọn nhạc.
Đọc lại sách chỉ dùng file cục bộ; không phát sinh thêm lần gọi ElevenLabs.

### Tự thêm MP3 hoặc nhạc riêng

1. Mở **Nhạc đệm trong khoảng nghỉ → Thêm nhạc…**, chọn file audio nguồn.
2. Colin đọc file, lấy tối đa 30 giây, trim/cân mức âm và lưu một bản WAV riêng
   trong thư viện; file nguồn được giữ nguyên.
3. Bản vừa nhập được chọn ngay trong danh sách. Bật nhạc, đặt âm lượng/vị trí và
   dùng **Nghe thử nhạc** trước khi chạy EPUB.

Chỉ chép `.mp3` vào thư mục `music_library/` **không tự làm nhạc xuất hiện**.
Ứng dụng đọc catalog `music_library/library.json`, không tự quét mọi file trong
thư mục. Nếu đã chép file vào đó, vẫn dùng **Thêm nhạc…** để chọn chính file ấy;
không cần sửa JSON bằng tay. Web dùng ô **Thêm nhạc cá nhân**; MCP dùng
`import_chapter_music` với đường dẫn tuyệt đối và tên bản nhạc.

Khi chuyển máy, copy cả thư mục `music_library/` gồm WAV và `library.json` vào
workspace mới, hoặc nhập lại nhạc qua giao diện. Catalog và audio riêng không
đi cùng Git clone; không xóa `library.json` nếu muốn giữ các ID nhạc đã lưu.

Các mẫu được tạo bằng tài khoản ElevenLabs Free trong workspace có nhãn dùng cá
nhân. Khi cần xuất bản thương mại, chọn nhạc có quyền phù hợp hoặc tạo mẫu mới
bằng gói cho phép thương mại. Không phân phối các file ElevenLabs riêng lẻ như
một gói thư viện công khai. Xem [billing](https://elevenlabs.io/docs/overview/administration/billing)
và [điều khoản Sound Effects](https://elevenlabs.io/creative-terms).

## MCP

Mở lại kết nối MCP sau nâng cấp. `health.version` là phiên bản source đang chạy;
`installed_distribution_version` giúp nhận ra môi trường editable còn metadata
cũ trước khi launcher đồng bộ. Có thể xem trước mà không tạo giọng:

```json
{
  "source_file": "D:\\books\\truyen.epub",
  "chapter_start": 1,
  "chapter_end": 2,
  "limit": 20
}
```

Gửi payload trên cho tool `inspect_epub`. `get_generation_contract` trả
`source_formats`, `epub_defaults` và `epub_options_schema` chung cho mọi model.
Tạo audio qua `start_file_generation` hiện có:

```json
{
  "request": {
    "source_files": ["D:\\books\\truyen.epub"],
    "model_id": "piper_ngoc_huyen",
    "voice": {"mode": "fixed"},
    "output": {
      "directory": "D:\\Audiobooks",
      "audio_format": "mp3",
      "create_srt": true
    },
    "generation": {
      "language": "vi",
      "runtime_target": "cpu",
      "epub": {
        "chapter_start": 1,
        "chapter_end": 2,
        "read_titles": true,
        "include_volumes": true,
        "output_mode": "chapters",
        "title_pause_ms": 1200,
        "chapter_pause_ms": 2500,
        "scene_pause_ms": 1200,
        "volume_pause_ms": 1800
      }
    }
  }
}
```

Chọn model/voice theo contract thực tế, lưu job ID và dùng `get_job` theo dõi.
`result.files[].result.item_audio_paths` và `item_srt_paths` chứa toàn bộ kết quả.
Nếu một file lỗi, job báo `failed` và giữ kết quả các file/chương đã hoàn tất.
Không gửi thẳng `epub_options` vào `advanced`; dùng đúng `generation.epub`.

Nhạc được quản lý bằng `list_chapter_music`, `import_chapter_music` và
`preview_chapter_music`. Chọn ID có trong danh sách rồi thêm vào `generation.epub`:

```json
{
  "music": {
    "enabled": true,
    "track_id": "co-phong-hao-khi",
    "volume_percent": 30,
    "between_chapters": true,
    "after_title": false,
    "fade_in_ms": 120,
    "fade_out_ms": 350
  }
}
```

`preview_chapter_music` nhận `track_id`, `duration_ms` từ 1–10.000, âm lượng và
hai tham số fade, trả đường dẫn WAV. `import_chapter_music` nhận `source_file`
tuyệt đối và `name`, không tải mạng. Bật nhạc khi thiếu file/ID sẽ báo lỗi để
chọn lại, không tự thay một bài khác. Cache kiểm tra thêm hash file nhạc.

MCP nhận tối đa 100 file/request và 20 MB/file. Bộ đọc giới hạn 200 MB giải nén,
10.000 tệp và 20 MB/tài liệu XHTML; không giải nén ra ổ đĩa, không chạy script
hoặc tải tài nguyên ngoài. Sách ảnh/scan cần OCR trước. Mã hóa nội dung/DRM,
XML hỏng hoặc khoảng chương vượt sách sẽ báo lỗi. Đây là trình đọc cấu trúc,
không phải EPUBCheck hoặc bộ biên tập/sửa nghĩa tự động.

## Kiểm tra

Test PCM dùng engine giả có thời lượng biết trước để đo chính xác nhịp nghỉ và
timestamp SRT, cả theo chương và ghép sách. Test provider xác nhận metadata nghỉ
không đi vào văn bản model. Khi nghe thử, nên chọn cuối chương 1 -> đầu chương 2
và thêm một chương có thơ/chuyển cảnh trước khi chạy toàn bộ truyện.
