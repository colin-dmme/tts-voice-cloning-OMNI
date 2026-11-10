# Pha 2. Điều phối runtime, worker và job tạo giọng

## Mục tiêu

Agent hoặc Studio gửi một job VieNeu v3 CUDA và nhận WAV đã xác minh. Một tiến trình nền trên Windows giữ vòng đời job qua việc đóng chat, đóng Qt hoặc mất kết nối. Hàng đợi chỉ cấp máy khi có việc.

## Vòng đời và quyền worker

1. Tiến trình nền giữ khóa chủ theo data root và dùng IPC cục bộ cho Qt/MCP. Ghi job vào SQLite với `idempotency_key` và fingerprint của đầu vào, voice, profile, model và đích xuất. Cùng khóa và cùng yêu cầu trả về job cũ. Cùng khóa với yêu cầu khác báo xung đột.
2. Kiểm tra broker trên PC và HTTPS. Giữ job ở PC đến khi worker sẵn sàng. Khởi động broker khi chính sách người dùng cho phép. Tạo runtime có giới hạn, ghi tài khoản, `launch_id`, `runtimeId`, phiên Jupyter và ID yêu cầu trước từng thao tác từ xa.
3. Dùng worker ID dành riêng cho chế độ tự động. Tái sử dụng cơ chế ghép nối hiện có theo dạng thử thách ràng buộc với `launch_id`. Mã bootstrap cố định khởi động yêu cầu ghép nối trong phiên Colab mà bộ điều phối vừa cấp. Mã một lần do phiên đó trả về, cùng thông tin worker/model/device và nonce khớp mới đủ để broker duyệt theo chính sách đã bật. Device secret và khóa worker chỉ nằm trong runtime. Quyền quản trị broker và OAuth ở PC. Chỉ duyệt một lần theo launch, có hạn dùng và ghi log quyết định. [Ghép nối hiện tại](D:/_coder/colin-tts-compute-service/src/colin_compute_service/pairing.py:112)
4. Worker tải gói nguồn giới hạn của broker, kiểm SHA-256, cài phụ thuộc đã pin, kiểm thiết bị và nạp model. Dùng dấu trạng thái theo launch để đối chiếu nếu lệnh khởi động chưa rõ kết quả. Kiểm tra heartbeat mới, phiên worker, model, thiết bị và kết quả warm-up trước khi chuyển job. Tách trạng thái tải model khỏi trạng thái **Sẵn sàng**. [Gói worker](D:/_coder/colin-tts-compute-service/src/colin_compute_service/worker_package.py:19) · [Worker warm-up](D:/_coder/colin-tts-compute-service/src/colin_compute_service/worker.py:378)
5. Đi qua tuyến TTS remote hiện tại. Ghi khóa ổn định theo job, đoạn và lần thử, cùng broker job ID và kết quả đã xác minh. Khi mất kết nối, tra job theo khóa trước khi gửi lại. Chỉ tạo lần thử mới sau khi đã đối soát trạng thái cũ. Tải WAV vào file tạm, kiểm SHA-256 và kiểm tra WAV đọc được, sau đó ghi ra đích và cập nhật tiến độ. Hoàn tất khi đủ đầu ra đã yêu cầu. [Router VieNeu](C:/Coder/tts-voice-cloning-OMNI/src/omni_tts_core/engines/vieneu_routing_engine.py:53) · [Broker client](C:/Coder/tts-voice-cloning-OMNI/src/omni_tts_core/remote_compute/client.py:93)
6. Khi xong hoặc hết thời gian giữ máy đã chọn, chốt kết quả trên PC, thu hồi phiên worker và trả runtime do Studio cấp. Lỗi trả máy có trạng thái riêng. Đối soát các runtime đang chờ trả khi tiến trình nền khởi động lại.

## Tệp dự kiến

- Tạo bộ điều phối và kho trạng thái theo data root trong `C:/Coder/tts-voice-cloning-OMNI/src/omni_tts_core/remote_compute/`. Dùng lại cơ chế quản lý tiến trình nền của [local_broker.py](C:/Coder/tts-voice-cloning-OMNI/src/omni_tts_core/remote_compute/local_broker.py:113) tại điểm thích hợp.
- Sửa quyền sở hữu job và phục hồi trong [job_manager.py](C:/Coder/tts-voice-cloning-OMNI/src/colin_studio_tts_mcp/job_manager.py:49) và [job_store.py](C:/Coder/tts-voice-cloning-OMNI/src/colin_studio_tts_mcp/job_store.py:39). Truyền khóa ổn định qua [router VieNeu](C:/Coder/tts-voice-cloning-OMNI/src/omni_tts_core/engines/vieneu_routing_engine.py:53). Mở rộng ZeroTTS CPU khi luồng CUDA qua kiểm thử.
- Bổ sung ghép nối theo launch và ràng buộc phiên trong [pairing.py](D:/_coder/colin-tts-compute-service/src/colin_compute_service/pairing.py:153), [server.py](D:/_coder/colin-tts-compute-service/src/colin_compute_service/server.py:97) và [pairing_bootstrap.py](D:/_coder/colin-tts-compute-service/src/colin_compute_service/pairing_bootstrap.py:90). Tái sử dụng gói ZIP và quyền tải audio mẫu theo lease.
- Bổ sung chuyển trạng thái có điều kiện theo trạng thái, attempt và lease trong [store.py](D:/_coder/colin-tts-compute-service/src/colin_compute_service/store.py:279). Worker kiểm tra yêu cầu hủy khi gia hạn lease và giữa các đơn vị có thể ngắt. [worker.py](D:/_coder/colin-tts-compute-service/src/colin_compute_service/worker.py:246)

## Tiêu chí qua pha

- [ ] Một câu VieNeu v3 preset chạy đúng CUDA, WAV hoàn chỉnh về PC và runtime đã được trả.
- [ ] Đóng chat hoặc mở hai MCP client vẫn giữ một job và một runtime. Khởi động lại bộ điều phối rồi nối lại job dở theo dữ liệu đã lưu.
- [ ] Mô phỏng timeout khi gửi job, worker rớt và kết quả về trễ. Tái sử dụng đoạn đã xác minh, chỉ chạy lại đoạn thiếu. Job giữ đúng thứ tự.
- [ ] Từ chối phiên ghép nối sai launch, sai worker, sai model, sai thiết bị hoặc hết hạn. Notebook mở tay dùng ID riêng. Giữ log sạch token, mã ghép nối và audio mẫu.
- [ ] Tạo giọng qua Qt và Studio MCP tiếp tục dùng API hiện tại. Luồng Colab thủ công vẫn có thể chọn trong Studio.
