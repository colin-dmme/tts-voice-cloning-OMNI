# Pha 1. Host worker CPU dùng chung trên Windows, thử đầu bằng ZeroTTS

Trạng thái: chưa triển khai. Phạm vi đầu: Windows x64, CPU, Internet, một worker.

## Căn cứ

[Báo cáo runtime](C:/Coder/tts-voice-cloning-OMNI/plans/2026-11-09-zerotts-may-cpu-tu-xa/reports/zerotts-runtime.md). Tái sử dụng `D:/_coder/colin-tts-compute-service/src/colin_compute_service/worker.py` và `C:/Coder/tts-voice-cloning-OMNI/engines/zerotts_worker/`. Host không phụ thuộc Qt; từng engine nhận dependency theo manifest riêng. ZeroTTS pilot không cần môi trường PyTorch; VieNeu dùng manifest riêng khi thêm adapter.

## Source và gói phát hành

- Thêm `D:/_coder/colin-tts-compute-service/src/colin_compute_service/pc_worker/` cho installer, cấu hình, CLI, supervisor, dispatcher và quản lý tiến trình Windows; registry adapter theo hợp đồng pha 4 ngay từ đầu.
- Sửa `D:/_coder/colin-tts-compute-service/src/colin_compute_service/worker.py` để ZeroTTS dùng helper timeout/log đã có trong `resident.py`, thêm warm-up trước đăng ký READY.
- Mở rộng `worker_package.py` với manifest Windows gồm phiên bản source, dependency lock và checksum. Có launcher `Install-Worker.bat` và `Manage-Worker.vbs`; tên/đường dẫn cuối cùng chốt khi triển khai.
- Giữ engine chuẩn tại repository Studio và đóng gói từ bản đã commit; không tạo bản sao engine bảo trì độc lập.

## Các bước

1. Kiểm tra Windows/kiến trúc, CPU, RAM trống, ổ đĩa, kết nối broker/model host và cài đặt đã có. Không ghi đè release đang chạy.
2. Tạo môi trường Python 3.12 riêng từ manifest/lock đã có. Dùng đường Windows `.venv/Scripts/python.exe`, không dùng `/content` hay `.venv/bin/python` của Colab.
3. Tải `zeroweight-ai/ZeroTTS` tại revision `8a0c3c29f6f047011f5cae02d0b14475a690be86`. Kiểm đầy đủ tokenizer/config, graph ONNX, codec external `.data`, voice index và preset `.npz`. Ghi manifest model; hỗ trợ dùng lại cache đã xác minh.
4. Nạp model và tạo câu chẩn đoán với preset có thật. Kiểm WAV không rỗng, PCM, 48 kHz, duration hữu hạn; sau đó mới READY. Lỗi thiếu model/voice hoặc dependency phải hiện đúng bước.
5. Giữ một model active và concurrency=1 trên cả máy, không phải một job cho mỗi provider chạy đồng thời. Dispatcher dùng registry `describe/activate/synthesize/close`; từng engine có venv riêng, đổi model chỉ khi slot rảnh và đã đóng model cũ. Công bố installed/loadable/ready riêng, log SDK có giới hạn và timeout.
6. Supervisor chạy nền, có khóa chống chạy trùng; giữ và dọn đúng tiến trình con do nó tạo. Bảng trên máy phụ có Start, ngừng nhận việc, Stop, Status và Logs. Hiển thị điều khiển mong muốn và trạng thái đã xác nhận riêng.
7. Lưu cấu hình, quyền DPAPI, log xoay vòng và cache ngoài source. Tùy chọn chạy khi đăng nhập Windows bằng user thường. Đóng bảng không dừng worker; Stop phải dừng tiến trình inference thuộc worker.
8. Cập nhật vào release mới, chỉ đổi phiên bản khi worker không còn lease chạy; giữ release cũ để quay lại. Không ghi dữ liệu/account/model vào Git.

## Tiêu chí

- [ ] Máy Windows chưa có Studio cài và tự kiểm tra ZeroTTS thành công.
- [ ] Một host worker có ID/kết nối/quyền riêng cho máy, không cần tạo endpoint hoặc supervisor mới cho từng provider.
- [ ] READY chỉ xuất hiện sau warm-up và xác minh WAV.
- [ ] Hai câu liên tiếp dùng lại model; ghi số đo thay vì suy từ log READY.
- [ ] Treo SDK, log nhiều, hủy và mở launcher hai lần đều có trạng thái/timeout đúng.
- [ ] Không dùng broker master key trên máy phụ; ghép máy theo pha 2.
- [ ] Kiểm tra Start/Stop và đóng bảng, không để sót tiến trình model do worker tạo.

Chưa đưa GGUF vào pha này. Nếu ưu tiên GGUF, bổ sung adapter và đo so sánh trên cùng máy, cùng nội dung/voice trước khi thay model mặc định.
