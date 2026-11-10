# Pha 2. Điều phối PC và ghép máy có quyền riêng

Trạng thái: chưa triển khai. Phụ thuộc gói worker Windows và broker đang chạy.

## Ranh giới

[Báo cáo điều khiển](C:/Coder/tts-voice-cloning-OMNI/plans/2026-11-09-zerotts-may-cpu-tu-xa/reports/pc-worker-control.md). Worker/giao thức đã nhận ID/type bất kỳ, nhưng pairing hiện chỉ nhận nhóm Google và scoped token hết sau 12 giờ. Không dùng cơ chế phiên notebook làm chứng cứ đã có đăng ký PC lâu dài.

## Source liên quan

- Service: `D:/_coder/colin-tts-compute-service/src/colin_compute_service/{pairing,protocol,server,store,worker}.py` và module PC mới.
- Studio: `C:/Coder/tts-voice-cloning-OMNI/src/colin_colab_remote/{client,context,daemon,store,settings,inference}.py`, `broker/{models,profiles}.py`, `ui/remote_compute_section.py` và công cụ MCP quản trị remote.
- Đích tách lõi chung: `C:/Coder/tts-voice-cloning-OMNI/src/colin_remote_compute/`. Giữ alias cũ và migrate dữ liệu có đối soát; không tạo supervisor hoặc job store thứ hai.

## Các bước

1. Thêm ID PC có cú pháp/độ dài được xác thực, loại `remote_pc`; không mượn `google-pro-*`. Preview có tên máy, định danh, CPU và allowlist model/provider. Một thiết bị có thể được phép dùng nhiều adapter; không ràng buộc toàn bộ máy vào đúng một provider như phiên notebook hiện tại.
2. Giữ `runtime_target=remote` trên wire; thêm options target có kiểu `RemoteComputeTarget(kind=existing_worker|managed_colab, worker_profile_id, backend=cpu|cuda)`. Options vắng mặt giữ nghĩa request remote cũ. UI **CPU máy khác** luôn resolve `existing_worker + cpu`. Lưu snapshot target/model/revision vào job; đổi UI không đổi máy của job đã gửi.
3. Resolver chung phân biệt local, PC worker, Colab và remote API riêng trước khi kiểm model local. PC kiểm model/revision/backend CPU/clone/options trên worker; không yêu cầu model/dependency cài trên máy chính. Thay chốt cứng hai model ID bằng registry adapter. `should_manage` chọn lifecycle theo target; job PC không gọi OAuth/tier/create/delete Google kể cả khi Colab auto đang bật.
4. Tái sử dụng job store/context, khóa từng đoạn, cache đã xác minh và một chủ thực thi. Tiếp tục sau restart từ đoạn đã có kết quả hợp lệ; đối soát attempt trước khi gửi lại đoạn chưa rõ.
5. Ghép PC lần đầu bằng mã ngắn duyệt trên máy chính. Tạo quyền thiết bị có thể thu hồi, lưu DPAPI ở máy phụ; server giữ hash. Đổi thành session giới hạn ID/allowlist model/CPU, có xử lý mất phản hồi và xoay khóa. Thời hạn/chính sách cuối cùng chốt trước triển khai. Thu hồi chặn cấp phiên và phiên đã có. Thêm adapter vẫn dùng cùng thiết bị trong phạm vi model được phép; không gửi master key sang máy phụ.
6. Broker lưu trạng thái nhận việc của worker và các yêu cầu điều khiển cho phép. Worker chủ động lấy trạng thái qua HTTPS; không thêm endpoint shell tùy ý. Phân biệt đã gửi, worker đã nhận và đã hoàn tất lệnh.
7. Hai cấp điều khiển: job pause/resume/cancel; worker ngừng nhận việc, tiếp tục, dừng và ngắt quyền. Ngừng nhận việc đợi đoạn/job hiện tại theo lựa chọn rõ. Restart worker cần supervisor còn sống; báo offline nếu không còn kênh nhận lệnh.
8. UI giữ provider/model như hiện tại; thêm **CPU máy khác** trong Thiết bị xử lý cho model có adapter, hiện selector máy chung bên dưới. Khóa UI riêng phải được mapper chuyển thành `remote + target`, không lọt qua normalizer thành Auto. Auto của provider local vẫn chạy local. Giữ nhãn CPU ONNX/GGUF/precision đúng model. Hiển thị thiếu máy/model để người dùng thiết lập; backend kiểm lại khi submit/lease. Higgs Remote GPU dùng hợp đồng endpoint của nó và không được chọn CPU worker nếu không có adapter CPU.
9. Đồng bộ target options qua defaults, GenerationSettings, shared schema, TtsEngineRequest, text/file, MCP protected fields, preferences/history và restore UI. Worker profile ID không chứa credential. Frontend chưa có selector phải báo chưa hỗ trợ thay vì âm thầm đổi sang Auto/local. Trạng thái CPU/RAM lấy từ máy phụ, không từ detector của máy chính.

## Mạng và vận hành

Máy phụ chỉ cần kết nối HTTPS ra `tts-compute.tainguyenso.online`; broker/tunnel vẫn trên máy chính. Giữ kết nối broker hiện có cho cả hai máy, chưa cần cấu hình LAN hoặc mở inbound port trên máy phụ. Mất mạng tạm thời backoff; lỗi quyền dừng và hiện hành động cần xử lý. Chỉ cho failover theo chính sách đã chọn và sau khi trạng thái attempt trước đã rõ.

## Tiêu chí

- [ ] Chọn PC khi Colab tự động đang bật vẫn không gọi Google hoặc đòi gói Google.
- [ ] Giữ đúng lựa chọn CPU máy khác + máy đích qua preferences/history/MCP; request cũ giữ hành vi cũ. Auto không tự gửi việc ra ngoài.
- [ ] Hai thiết bị không dùng trùng định danh; sai ID/model/quyền bị từ chối.
- [ ] Đóng/mở Studio hoặc chat giữ job và các đoạn đã xác minh.
- [ ] Quyền hết hạn tự làm mới hợp lệ; quyền bị thu hồi không tự khôi phục.
- [ ] Pause, cancel, ngừng nhận việc và Stop có xác nhận thực tế; không giết tiến trình ngoài quyền sở hữu.
- [ ] Các đường import/job/manual Colab cũ tiếp tục hoạt động qua chuyển đổi.
