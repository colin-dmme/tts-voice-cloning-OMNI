# Lọc nội dung EPUB trước khi tạo giọng — 0.6.5

Colin giữ nguyên EPUB gốc và chuẩn bị một bản văn dành cho nghe. Bộ lọc chạy
trước bước chuẩn hóa số/ngày, chia đoạn và mọi provider TTS. Audio và SRT theo
cùng bản văn đã lọc; cache tính cấu hình, phiên bản bộ lọc và hash nội dung đọc.

## Dùng trên giao diện

Trong **Nhập EPUB**, mở **Nội dung đưa vào giọng đọc**. Qt/Tkinter cho so sánh
**Văn bản sẽ đọc**, **Bản gốc**, **Đã bỏ / đã đổi** và **Chữ Hán còn lại**.
Đổi tùy chọn sẽ cập nhật kết quả; các đoạn bị loại vẫn còn ở bản gốc/báo cáo.
Nút **Xuất bản đọc và nguồn…** cho kiểm tra tài liệu trước khi tạo audio.
Studio Qt có cùng bộ điều khiển để chỉnh sau khi nhập. Web có nhóm tùy chọn,
vị trí phần cần xem và nút so sánh; cảnh báo chỉ vị trí chữ Hán trong kết quả lọc.

| Tùy chọn | Mặc định | Hành vi |
|---|---|---|
| Bỏ nguồn tham khảo | Bật | Bỏ khối nguồn khỏi lời đọc; lưu riêng |
| Đường link | Không đọc | Bỏ URL/DOI trần, giữ nhãn link có nghĩa và liên kết nội bộ như “mục 18” |
| Giữ ghi chú giải thích | Bật | Giữ bối cảnh, điều kiện và giới hạn trong lời đọc |
| Chữ Hán | Dùng nghĩa Việt sẵn có + cảnh báo | Dùng cặp chữ Hán có nghĩa Việt trong ngoặc; cảnh báo phần còn lại |
| Giới thiệu/thuật ngữ | Đọc | Giữ phần đầu có nội dung |
| Phụ lục nội dung | Đọc | Không bỏ toàn bộ phụ lục chỉ vì cuối phần có tài liệu tham khảo |
| Ghi chú kỹ thuật | Không đọc | Bỏ phần có tiêu đề/semantic rõ, như “Ghi chú kỹ thuật”/colophon |
| Xuất nguồn riêng | Bật | Tạo file MD nguồn bên cạnh TXT bản đọc và JSON báo cáo |

URL có thể đổi sang **Chỉ đọc tên miền** hoặc **Đọc nguyên địa chỉ**. Khi đọc
địa chỉ, bộ chuẩn hóa bảo vệ DOI khỏi bị nhận nhầm thành ngày/tháng. Link có
nhãn “Tổ chức Y tế Thế giới” giữ nguyên nhãn, không tự đọc thêm `href`.
Không mở các link hoặc kiểm chứng nội dung nghiên cứu khi trích sách.

## Cách đọc chữ Hán

Ví dụ `医保 (bảo hiểm y tế)` được đọc gọn “bảo hiểm y tế”. Chỉ dùng giải nghĩa
Việt đã nằm trong sách, không tự tạo bản dịch. Các trường hợp chưa xử lý vẫn
giữ trong lời đọc và được cảnh báo để người dùng kiểm tra; cảnh báo không tự
chặn tác vụ. Có thể chọn giữ nguyên/cảnh báo hoặc giữ nguyên/không cảnh báo.

Nút **Cách đọc chữ Hán…** nhận mỗi dòng `chữ gốc = cách đọc`, ví dụ:

```text
万 = vạn
```

Đây là lựa chọn cho sách/tác vụ, không sửa EPUB hoặc từ điển dùng chung. Nếu
có giải nghĩa Việt trong ngoặc, không đọc lặp phần đó. Từ viết tắt/tên tiếng
Anh trong nội dung chính tiếp tục dùng tab Cách đọc của Colin.

Không dùng quy tắc thay `等` toàn cục: ở trích dẫn tác giả có thể là “và cộng
sự”, nhưng trong văn cảnh khác có nghĩa khác. Mặc định khối trích dẫn đã bị bỏ
nên không cần xử lý từng chữ trong đó.

## Nhận diện nguồn và giới hạn

Bộ đọc phân loại khối theo `epub:type`/role của bibliography, class như
`sources`, `references`, `bibliography`, hoặc heading riêng “Nguồn”, “Tài liệu
tham khảo”, “References”… Phạm vi heading kết thúc ở heading cùng cấp hoặc
cao hơn. Nhãn `Nguồn:` dạng đoạn có class label/chữ đậm cũng được nhận diện.
Ghi chú ở một khối riêng hoặc đề mục tiếp theo vẫn được giữ.

Không xóa mọi đoạn chứa từ “nguồn”: câu “Nguồn nước sạch rất cần thiết” vẫn là
nội dung. EPUB không có markup/heading rõ có thể còn đoạn tham khảo chưa được
nhận diện; xem trước giúp phát hiện. Bộ lọc không suy diễn mọi đoạn tiếng Anh
là tài liệu tham khảo. Các phần bìa/điều hướng/chú thích EPUB vốn được bộ đọc
loại trừ vẫn theo quy tắc cấu trúc hiện có.

Vị trí phần/chương luôn là chỉ số trong EPUB gốc. Ví dụ bỏ giới thiệu ở vị trí
1 không đổi chương 2 thành chương 1. Khoảng chương, agent music overrides và
tên file kết quả tiếp tục dùng các chỉ số đó.

## File kết quả

Mỗi lượt tạo EPUB có thêm, cùng thư mục audio:

- `*-reading-<hash>.txt`: đầy đủ văn bản chuẩn bị cho lời đọc, trước chuẩn hóa
  phát âm riêng của model/cách đọc.
- `*-reading-report-<hash>.json`: cấu hình, hash nguồn/bản đọc, thống kê, cảnh
  báo, các thay đổi và vị trí để kiểm tra bằng agent.
- `*-references-<hash>.md`: nội dung nguồn/địa chỉ tách riêng, theo phần/mục;
  không có file MD này nếu bỏ chọn xuất nguồn riêng.

Đường dẫn trả qua `GenerateSpeechResult.reading_text_path`,
`reading_report_path`, `references_path`; ZIP tải về trên Web có các file này.
Đây là tài liệu cục bộ, có thể chứa nguyên văn nguồn tham khảo và phần đã bỏ.
Tên dùng hash để phân biệt nguồn/cấu hình; chạy lại cùng dữ liệu giữ đường dẫn.

## MCP

`get_generation_contract` công bố schema mới dưới `epub_options_schema`.
Cấu hình ví dụ trong `generation.epub`:

```json
{
  "content": {
    "skip_references": true,
    "url_mode": "skip",
    "read_notes": true,
    "han_mode": "prefer_vietnamese",
    "han_readings": {"万": "vạn"},
    "include_frontmatter": true,
    "include_appendices": true,
    "include_technical_notes": false,
    "export_references": true
  }
}
```

Gọi `preview_epub_reading` với `source_file`, `epub` và `chapter_index` để xem
so sánh. `max_characters` giới hạn 100–50.000 ký tự cho mỗi bản xem trước,
mặc định 16.000; kết quả có `truncated` và `changes_truncated`. `han_issues`
chỉ vị trí/đoạn còn chữ Hán; phản hồi xem trước giới hạn danh sách, còn báo cáo
xuất đầy đủ. Tool không tạo audio hoặc nạp model.

`export_epub_reading` nhận cùng `epub` và `output_directory` tuyệt đối để lưu
bản đọc/nguồn trước khi tạo sách. Sau khi kiểm tra, gửi cùng `epub` vào
`start_file_generation`; không đặt các trường lọc này trong provider options.

## Kiểm tra với HowToLiveBetter-vi.epub

Sách có 47 phần được bộ đọc nhận diện, gồm 34 chương chính. Bộ lọc mặc định
nhận diện 774 nhóm nguồn (772 khối có class và 2 đề mục nguồn), giữ 772 khối
ghi chú gốc, dùng 4 nghĩa Việt đã có. Chữ Hán còn lại là `万` trong bảng thuật
ngữ; thêm cách đọc `万 = vạn` thì không còn chữ Hán hoặc URL trong bản đọc.
Ghi chú kỹ thuật cuối sách bị bỏ nên bản đọc còn 46 phần, giữ chỉ số gốc.
File EPUB gốc được đối chiếu SHA-256 và không thay đổi.
