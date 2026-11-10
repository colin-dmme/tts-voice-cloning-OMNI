# Colab từ xa

Package này quản lý tài khoản Google, vòng đời runtime và giao diện Colab của Colin TTS Studio. Broker, hàng đợi và suy luận từ xa dùng chung nằm trong [colin_remote_compute](C:/Coder/tts-voice-cloning-OMNI/src/colin_remote_compute/README.md). Các đường import cũ vẫn dẫn đến mã dùng chung.

```text
colin_colab_remote/
  ui/                     Bảng Colab tự động, ghép mã và bảng broker
  google_mcp.py           Colab MCP từ xa chính thức của Google
  oauth.py                OAuth Desktop, PKCE và kho quyền được mã hóa Windows DPAPI
  lifecycle.py            Cấp runtime, ghép worker theo launch_id và trả đúng runtime
  mcp_tools.py            Công cụ quản trị Colab đăng ký với Studio MCP
  settings.py             Tùy chọn Colab và thư mục dữ liệu riêng
  autostart.py             Khôi phục supervisor khi đăng nhập Windows
```

## Thiết lập một lần

Mở **Studio → Điện toán Colab → Quản lý Colab tự động**. Chọn tài khoản, GPU và thời hạn máy. Nhập JSON của một OAuth client loại Desktop đã đăng ký với Google, sau đó bấm **Kết nối / cấp lại quyền Google**. Mở liên kết Google hiển thị trong bảng, chọn đúng tài khoản và đồng ý quyền. Bật **Tự cấp Colab** rồi lưu. Khi bật tự trả máy, ứng dụng được phép giải phóng runtime do chính nó cấp khi hết việc hoặc hủy. GPU được chọn phải nằm trong cấu hình tài khoản đủ điều kiện. [Colab MCP](https://developers.google.com/colab/api/reference/mcp) · [OAuth Desktop](https://developers.google.com/identity/protocols/oauth2/native-app)

Google Cloud project dùng cho OAuth cần bật Colab API/MCP theo hướng dẫn của Google. Ứng dụng OAuth External ở chế độ Testing có thể có refresh token hết hạn sau 7 ngày. Bảng hiển thị **Cần cấp quyền** khi Google yêu cầu kết nối lại. [Thiết lập Google MCP](https://docs.cloud.google.com/mcp/set-up-authentication-mcp-servers) · [Thời hạn quyền OAuth](https://developers.google.com/identity/protocols/oauth2#expiration)

Google AI Pro có quyền lợi 200 Colab Compute Units với gói đủ điều kiện. Google loại trừ kỳ dùng thử Google One, gồm ưu đãi dùng thử kéo dài. Vì vậy nhãn Google AI Pro trong Google One chưa chứng minh tài khoản đã có quyền lợi Colab. Đối chiếu trạng thái và số dư tại **Colab → View resources** cùng **Settings → Subscription** trước pilot. [Quyền lợi Google AI Pro](https://support.google.com/googleone/answer/14534406?hl=en) · [Điều kiện Colab và Google AI](https://research.google.com/colaboratory/faq.html)

Tạo giọng như bình thường với thiết bị **Colab từ xa**. Job được lưu trong hàng đợi của supervisor, có thể theo dõi bằng Qt hoặc `get_job` của Studio MCP. **Tạm dừng cấp việc** chờ đoạn hiện tại xong. **Hủy job** giữ các đầu ra đã xác minh. **Dừng việc và giải phóng runtime** yêu cầu dừng và trả máy của ứng dụng. Tự khôi phục dùng task Windows `Colin TTS Colab Supervisor` khi đăng nhập.

Mở bảng độc lập bằng [Manage-Colab-Auto.vbs](C:/Coder/tts-voice-cloning-OMNI/Manage-Colab-Auto.vbs) hoặc chạy `.\.venv\Scripts\python.exe -m colin_colab_remote panel` từ thư mục dự án. Xem trạng thái bằng `.\.venv\Scripts\python.exe -m colin_colab_remote status`.

## Broker và worker

Dịch vụ HTTP và worker chạy Colab được bảo trì trong repository riêng tại `D:/_coder/colin-tts-compute-service/src/colin_compute_service`. Client Studio nằm trong `colin_remote_compute/broker/`. Dịch vụ phân phối gói source worker có SHA-256 qua HTTPS cho phiên đã duyệt.

Managed worker dùng `managed-google-pro-1/2/3`, có `launch_id` gắn với runtime do ứng dụng cấp. Bộ điều phối đối soát đúng launch trước khi duyệt. Worker tự tải và giữ quyền giới hạn trong runtime. Worker notebook ghép mã dùng ID `google-pro-1/2/3`.

Broker cần báo `/health.managed_colab=enabled`. Gói worker lấy từ Git HEAD đã commit của cả hai repository theo danh sách cho phép. Khi nâng cấp service, chạy kiểm thử, commit source worker rồi khởi động lại broker lúc hàng đợi trống. Broker tạo lại gói nguồn tại lúc khởi động. [Contract managed worker](D:/_coder/colin-tts-compute-service/README.md)

## Dữ liệu và khôi phục

Dữ liệu ở `%LOCALAPPDATA%/ColinTTS/colab_remote`, gồm cấu hình, SQLite, checkpoint, cache từng đoạn và kho quyền theo tài khoản. Dùng `COLIN_COLAB_DATA_DIR` để cô lập khi kiểm thử. Giữ dữ liệu này khi nâng cấp để đối soát runtime và tiếp tục job. JSON OAuth, quyền Google, audio mẫu và dữ liệu job được lưu ngoài source.

Khi nguồn hoặc mẫu giọng thay đổi, job yêu cầu tạo lại để giữ đúng phiên bản nội dung. Khi mất kết nối, supervisor tra broker theo khóa cũ. Chỉ chuyển lần thử sau khi biết trạng thái trước đã kết thúc. Kết quả audio và kết quả trả runtime có trạng thái riêng, nên lỗi kết nối lúc trả máy vẫn giữ WAV đã hoàn tất.

## Kiểm tra

Trong môi trường Studio, chạy `python -m pytest tests/test_colab_google_provider.py tests/test_colab_managed_lifecycle.py tests/test_colab_supervisor.py tests/test_colab_remote_compatibility.py`. Các bài dùng provider giả và dữ liệu tạm. Pilot thật cần cấp quyền Google, cấp một GPU, tạo WAV rồi xác nhận runtime đã được trả.
