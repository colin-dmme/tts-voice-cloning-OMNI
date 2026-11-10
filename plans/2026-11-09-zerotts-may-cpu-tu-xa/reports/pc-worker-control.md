# Kiểm tra điều khiển worker CPU trên máy thường

Ngày 09/11/2026. Chỉ đọc source và lập kế hoạch; chưa truy cập, cài hoặc chạy trên máy đích.

1. **Giao thức đã dùng được cho PC; ghép nối chưa dùng được.** `worker.py:357` nhận worker ID/tên/type từ môi trường; `protocol.py:57` cho phép worker type bất kỳ và model ZeroTTS CPU. `pairing.py:18` và `pairing_bootstrap.py:95` giới hạn ID vào nhóm Google. Đề xuất tạo ID riêng `pc-<id>` và loại `remote_pc`, kiểm tra cú pháp/độ dài phía server, bind quyền với đúng ID + `zerotts` + `cpu`. Không dùng lại Google worker ID cho máy PC.

2. **Quyền phiên hiện tại hết sau 12 giờ, chưa có quyền thiết bị bền vững.** `pairing.py:25,183,202,224` cấp scoped token hết hạn; token không được refresh, bootstrap giữ trong RAM/env. Để pilot, có thể ghép một phiên ngắn rồi chạy thử. Để tự chạy lâu dài, thêm đăng ký thiết bị được duyệt một lần, secret có thể thu hồi lưu Windows DPAPI (Linux cần kho khóa tương ứng), server chỉ giữ hash; dùng grant đó đổi scoped session token có hạn và đối soát trước khi đổi. Thu hồi thiết bị phải chặn cả refresh và các phiên của nó. Không chuyển master token của broker sang máy phụ; không tự gia hạn phiên đã bị thu hồi.

3. **Phải tách lựa chọn PC khỏi tự cấp Colab trước khi triển khai.** `client.py:36` đang đưa mọi yêu cầu remote ZeroTTS/VieNeu vào managed supervisor khi setting Colab enabled. `daemon.py:42,110` luôn tạo `GoogleColabProvider`/`ColabLifecycle`; `context.py:68,102` gọi `ensure`/`release`. Đề xuất target rõ `existing_worker` hoặc `managed_colab`, chụp profile đích vào job. Tái sử dụng một job store/context và cung cấp lifecycle PC chỉ kiểm tra worker đã đăng ký đúng model, không OAuth/Google, không cấp hoặc trả runtime. `release` của Colab không được chạy khi hủy job PC. Có thể giữ package hiện tại để tương thích và tách các lớp chung khi triển khai, tránh tạo thêm hàng đợi riêng.

   Tổ chức source nên có lõi remote trung lập (broker, inference, queue/context, worker target) và adapter Google riêng. V1 tách ranh giới target/lifecycle trước, chuyển đúng các module chung bằng từng bước nhỏ và giữ import alias tương thích. Tránh đổi tên hàng loạt hoặc tạo supervisor/hàng đợi thứ hai cho PC. Mỗi job chỉ có một chủ thực thi và một target snapshot; UI/MCP cùng đọc trạng thái đó.

4. **Đã có lease và chống kết quả muộn, nhưng chưa có điều khiển máy/worker.** `worker.py:241` xin lease 300 giây, heartbeat khi rảnh 30 giây, gia hạn/kiểm tra hủy mặc định 5 giây. Hủy hoặc mất renew sẽ đóng SDK con do worker giữ; `store.py:427` đánh dấu lease hết hạn và `store.py:338` dùng tệp theo attempt. Không đồng nghĩa job chạy tiếp xuyên sleep/reboot. V1 tiếp tục từ đoạn đã xác minh, đối soát attempt trước khi gửi lại; không công bố exactly-once synthesis. Mất mạng tạm thời có backoff 2..30 giây, 401/403 dừng để xử lý quyền (`worker.py:328`).

5. **Bổ sung hai cấp điều khiển có nghĩa rõ.** Cấp job: tạm dừng cấp đoạn mới, tiếp tục, hủy job; đoạn đã xác minh giữ nguyên. Cấp worker: tạm ngừng nhận việc và đợi việc hiện tại xong, chạy lại, dừng worker, ngắt quyền thiết bị. Hiện `ManagedExecution` đã hỗ trợ pause tại ranh giới đoạn và hủy job, còn broker chưa có desired state cho worker. Đề xuất worker poll desired state đã lưu tại broker; chỉ whitelist các thao tác này, không thêm endpoint chạy shell tùy ý. UI phải phân biệt lệnh đã gửi, worker đã nhận và worker đã dừng; không báo thành công chỉ từ nút bấm. Dừng worker không tắt Windows và không tắt broker.

6. **Cần supervisor và bảng quản lý riêng trên máy phụ.** Hiện background/supervisor của service quản lý broker + tunnel; task Studio quản lý hàng đợi trên máy chính. Chưa có PC worker supervisor. Đề xuất launcher mở bảng Start/Pause/Stop/Status/Logs, tùy chọn chạy khi đăng nhập Windows với quyền user thường, `pythonw`/hidden và single-instance lock. Giữ config/token/log/cache ngoài source, log xoay vòng; closing panel không dừng worker. Reuse mẫu owned-child/process cleanup trong `windows_process.py`; không kill theo tên Python hoặc PID lấy từ JSON cũ. Logon task chỉ chạy sau đăng nhập, không hứa chạy khi máy tắt hoặc chưa đăng nhập.

7. **Nghiệm thu v1 và giới hạn cần thông báo.** Một máy, một worker, concurrency=1; worker nạp/thử model trước READY, Studio chọn đúng profile và kiểm tra heartbeat/model/CPU. Thử câu ngắn và văn bản nhiều đoạn, xác minh WAV/hash trên máy chính; thử hủy khi inference, pause/resume, mất mạng, restart broker, restart worker và khởi động lại client. Thử token hết hạn/thu hồi, hai phiên cùng ID, kết quả cũ sau lease mới, không gửi nhầm sang Google khi managed Colab đang enabled. Máy phụ phải bật và không ngủ khi cần xử lý. Broker hiện ở máy chính nên máy chính và tunnel cần hoạt động; không hứa máy phụ tiếp tục nhận job khi máy chính tắt. Subdomain hiện có dùng được cho kết nối outbound qua Internet; worker không cần mở cổng inbound.

## Source đã đọc

- `D:/_coder/colin-tts-compute-service/src/colin_compute_service/{worker,protocol,pairing,pairing_bootstrap,server,store,supervisor,background}.py`
- `C:/Coder/tts-voice-cloning-OMNI/src/colin_colab_remote/{client,context,daemon,autostart}.py`
- `C:/Coder/tts-voice-cloning-OMNI/src/colin_colab_remote/supervisor_task.ps1`
- `C:/Coder/tts-voice-cloning-OMNI/src/colin_colab_remote/ui/remote_compute_section.py`

Chưa có thay đổi implementation, chưa kiểm chứng qua máy phụ thật. Cần tên máy, OS, kết nối LAN/Internet và CPU/RAM để chốt bộ cài và mức thread.
