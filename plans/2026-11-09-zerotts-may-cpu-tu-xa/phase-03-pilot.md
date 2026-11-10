# Pha 3. Thử thật ZeroTTS CPU qua Internet

Trạng thái: chờ tên máy Windows đích, cấu hình và kênh truy cập hoặc người dùng chạy bộ cài trên máy đó. Chưa cài phần mềm hay chuyển credential sang máy khác trong lượt lập kế hoạch.

## Lượt đầu

1. Ghi tên máy/OS/kiến trúc, CPU, RAM trống và nơi cài; kiểm tra broker HTTPS trước khi cài model.
2. Cài gói worker đã xác minh, ghép quyền thiết bị và đối chiếu đúng máy trên Studio.
3. Chọn ZeroTTS Official CPU, một preset, một job. Đo warm-up và tạo một câu ngắn bằng kênh gửi thật từ máy chính.
4. Tải WAV về đúng thư mục đầu ra trên máy chính, xác minh checksum, sample rate, duration và nghe nội dung. Gửi câu thứ hai để kiểm model resident.
5. Tạo văn bản nhiều đoạn để kiểm thứ tự, tiến độ, lưu từng đoạn và ghép audio cuối.

## Khôi phục và điều khiển

- [ ] Pause chặn cấp đoạn mới, Resume tiếp tục đúng phần thiếu.
- [ ] Cancel khi inference dừng SDK do worker tạo; kết quả muộn không được nhận sang attempt khác.
- [ ] Ngừng nhận việc không nhận lease mới; Stop được xác nhận và model được giải phóng.
- [ ] Ngắt/nối lại Internet và restart worker: đối soát trạng thái, giữ các đoạn đã xác minh, không gửi lại mù.
- [ ] Restart broker và mở lại client: job/worker rõ online, waiting hoặc failed, không báo xong nếu thiếu file.
- [ ] Hết hạn/thu hồi quyền: dừng hoặc làm mới đúng chính sách; không dùng khóa quản trị để vượt lỗi.
- [ ] Chọn PC khi tùy chọn Colab tự cấp đang bật: không gọi API Google.

## Đo và chốt cấu hình

Đo thời gian model khởi động, thời gian tạo các câu sau, thời lượng WAV, RAM đỉnh và RTF = thời gian tạo / thời lượng audio. Thử số model threads 2/4/8 phù hợp số lõi cùng codec threads rõ ràng. Giữ concurrency=1 và cấu hình cố định trong từng lượt đo. Số thread không phải cam kết tỷ lệ CPU cứng của toàn bộ tiến trình.

Chọn chế độ cân bằng theo khả năng sử dụng máy phụ trong lúc chạy. Chỉ mở thêm job song song hoặc thêm GGUF sau khi có số đo và kiểm tra bộ nhớ. Chưa công bố nhanh hơn realtime hoặc nhanh hơn máy chính khi chưa đo.

## Khi bật thêm provider

Lặp pilot trên cùng host/profile cho Piper và VieNeu v3 CPU theo pha 4. Thử đổi ZeroTTS → Piper → VieNeu → ZeroTTS để xác nhận một model active, RAM được thu hồi và hàng đợi không bị trộn. Piper kiểm native sample rate của ít nhất hai model, khoảng nghỉ/seed đã lưu; VieNeu kiểm cả preset và clone qua asset. Thử remote khi máy chính không có engine/model tương ứng. Chưa coi provider đã được hỗ trợ chỉ vì xuất hiện trong UI hoặc đã có engine local.

## Kết quả cần bàn giao

- Launcher/bảng quản lý sử dụng được trên máy phụ và profile máy đúng trong Studio.
- WAV thật và log job gắn ID máy/model/release, không chứa secret.
- Bảng số đo trên máy đích; trạng thái cuối worker, hàng đợi và quyền.
- Hướng dẫn ngắn cài một lần, chạy hằng ngày, tạm dừng, dừng, cập nhật và khôi phục.
