# CPU từ xa trong Colin TTS Studio

Studio dùng một broker HTTPS để gửi việc tới các máy Windows x64 đã ghép. Mỗi máy nhận một đoạn một lượt, tự nạp model đã cài và giữ model gần nhất trong bộ nhớ. Máy phụ kết nối ra `tts-compute.tainguyenso.online`.

## Ghép máy và tạo giọng

1. Trên máy phụ, giải nén bộ cài và mở **Install-CPU-Worker.bat**. Chọn **1** để bắt đầu với ZeroTTS hoặc **2** để cài thêm Piper Ngọc Huyền và VieNeu v3. Bộ cài tạo một WAV thử cho mỗi model trước khi công bố sẵn sàng.
2. Mở **Colin TTS CPU Worker** trên Desktop, bấm **Lấy mã ghép** rồi **Sao chép mã**. Trên máy chính mở tab **Máy CPU** bên trái. Dán mã, đối chiếu tên máy và bấm **Cấp quyền cho máy**. Mỗi máy ghép một lần. [Mở bảng quản lý độc lập](C:/Coder/tts-voice-cloning-OMNI/Manage-CPU-Workers.vbs)
3. Trong tab **Máy CPU**, đánh dấu cột **Chia tải** cho các máy bạn muốn dùng chung. Giới hạn mặc định là 4 máy đồng thời mỗi job và có thể chỉnh từ 1 đến 16.
4. Trong Studio chọn model, vào **Thiết bị xử lý → CPU máy khác** rồi chọn **Tự chia tải** hoặc chọn tên một máy. WAV được lưu theo thư mục đầu ra của Studio.

Model trong bộ cài gồm ZeroTTS 202M Official (giọng preset), Piper Ngọc Huyền, Piper 25hours Single Low, Piper VAIS1000 Medium và VieNeu v3 Turbo ONNX FP32 (preset hoặc clone từ Profile). Có thể tắt kết nối worker rồi chạy lại bộ cài để thêm model trong danh sách đã duyệt.

## Theo dõi và can thiệp

- **Máy CPU** hiển thị trạng thái, model đã cài và số lượt nhận, hoàn tất, WAV theo từng máy và toàn nhóm. Bỏ dấu **Chia tải** ngừng cấp đoạn mới cho máy đó. Dùng **Tạm ngừng**, **Dừng xử lý** hoặc **Ngắt quyền** để điều khiển trực tiếp máy. Bảng tự làm mới khi mở.
- **Hàng đợi CPU** hiển thị tiến độ, lượt đã xác minh, thông báo và kết quả. Tạm dừng job để các đoạn đang chạy hoàn tất. Tiếp tục dùng lại các đầu ra đã xác minh. Hủy job đối soát mọi đoạn đã gửi với broker.
- Trên máy phụ, **Thống kê nhận việc** hiện số lượt đã nhận, đã hoàn tất và số WAV broker đã nhận, cùng lịch sử 7 ngày. Bấm **X** để thu bảng xuống khay hệ thống. **Chạy cùng Windows** được bật mặc định để worker đã ghép tự chạy sau khi đăng nhập. Có thể bỏ dấu chọn trong bảng.
- Với agent, dùng `cpu_worker_status`, `start_text_generation` hoặc `start_file_generation`, `get_job` và `cpu_job_control`. [Hợp đồng Studio MCP](C:/Coder/tts-voice-cloning-OMNI/docs/mcp-server.md)

## Mã nguồn và dữ liệu

`src/colin_remote_compute/` chứa giao thức broker, hàng đợi, suy luận từ xa và bảng máy CPU. `src/colin_colab_remote/` chứa tài khoản Google, cấp và trả Colab cùng giao diện riêng. Các engine giữ cách chạy chung trong `engines/`. Mã worker Windows và bộ cài nằm ở [repository broker](D:/_coder/colin-tts-compute-service/pc-worker/HUONG-DAN.md).

Hàng đợi dùng lại dữ liệu ở `%LOCALAPPDATA%\ColinTTS\colab_remote` để các job trước nâng cấp còn truy cập được. Model, log và quyền thiết bị của máy phụ nằm ở `%LOCALAPPDATA%\ColinTTS\CPUWorker`. Windows DPAPI mã hóa quyền thiết bị theo tài khoản đã ghép.

Khi chia tải, Studio chia văn bản theo ranh giới câu và giới hạn độ dài đoạn, chọn nhóm máy trên cùng broker có model đúng phiên bản và cùng sample rate. Mỗi máy xong một đoạn sẽ nhận đoạn kế tiếp. Studio giữ danh sách ứng viên lúc xếp job, kiểm tra lại lựa chọn **Chia tải** trước khi cấp việc mới và ghép WAV/SRT theo thứ tự gốc. Một đoạn ngắn chỉ cần một máy. Các file trong hàng đợi xử lý lần lượt, các đoạn trong mỗi file có thể chạy song song.
