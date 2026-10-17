# Bật, tắt và kiểm tra broker Colab chạy nền

Broker là trạm chuyển việc giữa Studio trên PC và các worker Colab. Khi dùng Colab, giữ PC bật/có mạng và broker chạy. Nếu chỉ tạo audio bằng model ngay trên PC, không cần broker.

## Mở bảng điều khiển

Có hai cách, dùng cùng một cơ chế điều khiển:

- Trong Studio: **Điện toán Colab → Trạng thái / Bật tắt broker nền**.
- Khi chưa mở Studio: bấm đúp [Manage-Compute-Broker.vbs](C:/Coder/tts-voice-cloning-OMNI/Manage-Compute-Broker.vbs) trong thư mục dự án. Chỉ mở bảng điều khiển nhỏ, không hiện cửa sổ terminal chạy liên tục.

Nếu Studio đang mở từ trước khi cập nhật, đóng/mở lại bằng [run_qt.bat](C:/Coder/tts-voice-cloning-OMNI/run_qt.bat) để thấy nút mới. Nếu Windows hỏi ứng dụng mở `.vbs`, chọn Windows Script Host; không dùng Notepad để chạy file. Nếu máy chặn VBS, dùng nút trong Studio.

## Các nút và trạng thái

| Mục | Ý nghĩa |
| --- | --- |
| **Broker trên PC: ĐANG CHẠY** | Đã gọi `/health` và xác nhận đúng dịch vụ, không chỉ dựa vào file trạng thái cũ |
| **HTTPS/Colab: kết nối tốt** | Đã kiểm tra tên miền công khai. Broker chạy trên PC nhưng mạng/tunnel lỗi thì Colab vẫn có thể chưa kết nối được |
| **Bật chạy nền** | Bật task Windows, cho phép tự chạy lúc đăng nhập và chờ broker thật sự sẵn sàng |
| **Tắt chạy nền** | Xác nhận rồi dừng broker + Cloudflare Tunnel, tắt tự chạy lần đăng nhập sau. Giữ tắt cho tới khi bạn bấm Bật lại |
| **Làm mới trạng thái** | Kiểm tra lại cả PC lẫn HTTPS. Bảng tự kiểm tra trạng thái PC mỗi 15 giây; kết quả HTTPS chỉ cập nhật khi bạn bấm nút này |
| **Mở thư mục log** | Mở `C:\Coder\colin-tts-compute-runtime\logs` để kiểm tra lỗi |
| **Job đang xử lý / đang chờ** | Số job lưu trong broker, giúp bạn tránh tắt giữa lúc làm việc |

**Đóng bảng điều khiển hoặc đóng Studio KHÔNG tắt broker.** Muốn tắt, bấm đúng **Tắt chạy nền**. Bạn không cần giữ cửa sổ đen hay cửa sổ quản lý luôn mở.

**Tắt broker ảnh hưởng tất cả worker Colab**, không chỉ tài khoản đang chọn trong Studio. Không xóa job, audio, model hoặc token. Tác vụ đang chạy có thể bị gián đoạn; nên đợi hết job trước khi tắt. Bật lại không đảm bảo tự tiếp tục đúng job vừa bị ngắt — kiểm tra trạng thái trong Studio.

Tắt broker **không tự dừng máy GPU Google**. Sau khi dùng xong, còn cần dừng cell và chọn **Runtime → Disconnect and delete runtime** trên Colab để trả tài nguyên. Nút **Ngắt quyền Colab** là thu hồi quyền một worker, khác với **Tắt chạy nền** là dừng cả broker trên PC.

## Không còn cửa sổ đen chạy nền

Task Windows `Colin TTS Compute Broker` dùng `pythonw.exe`, không khởi động PowerShell/terminal. Các tiến trình broker/tunnel con cũng được yêu cầu không tạo cửa sổ. Chỉ một supervisor được phép dùng cùng thư mục dữ liệu; khi dừng, các tiến trình con được dọn cùng để tránh chạy sót hoặc tự bật lại.

Dữ liệu và khóa vẫn ở `C:\Coder\colin-tts-compute-runtime`, không chuyển/xóa. Log mới của launcher là `logs/background-launcher.log`, log broker/tunnel là `logs/supervisor.log`. Không gửi tệp `secrets/` cho người khác.

Nếu còn một tab terminal cũ trống sau khi đổi launcher, sau khi bảng quản lý xác nhận broker mới đang chạy bạn có thể đóng tab cũ. Không đóng cả ứng dụng terminal nếu có công việc khác trong đó.

## Nếu cần khôi phục sau này

Script `D:\_coder\colin-tts-compute-service\scripts\install_background_task.ps1` chuyển **task hiện có** sang launcher pythonw, giữ principal, trigger đăng nhập và cấu hình tự phục hồi. Trước khi thay, script lưu XML task trong `C:\Coder\colin-tts-compute-runtime\task-backups`. Script không tự dừng phiên đang chạy.

Nếu task bị xóa hoặc source D bị mất, phục hồi source/môi trường trước theo [hướng dẫn bắt đầu lại](C:/Coder/tts-voice-cloning-OMNI/HUONG-DAN-BAT-DAU-LAI.md). Không tạo lại token chỉ vì cửa sổ quản lý báo chưa có task. Nếu lỗi quyền Windows, kiểm tra quyền của task/tài khoản đăng nhập; không tự chạy broker bằng một terminal thứ hai để tránh trùng phiên.

## Đã kiểm tra ngày 17/10/2026

- Studio: 459 bài kiểm thử qua; service: 58 bài qua.
- Đã thử bật/tắt thật và dừng trực tiếp từ Task Scheduler: không còn Python/tunnel chạy sót sau khi tắt.
- Đã bật lại bằng pythonw; broker trên PC và tên miền HTTPS đều hoạt động, không có cửa sổ console của broker.
- Sao lưu trước chuyển đổi tại `C:\Coder\_backups\colin-broker-background-20261017` (Git bundles và database SQLite đã kiểm tra). XML task gốc nằm trong `C:\Coder\colin-tts-compute-runtime\task-backups`.

Trạng thái sau mỗi lần chạy có thể thay đổi; xem bảng quản lý để biết trạng thái hiện tại. Chưa chạy GPU Google Colab trong bài kiểm tra này.
