# Pha 3. Giám sát và bàn giao điều khiển

## Bảng Điện toán Colab

Mở rộng bảng hiện tại của Qt với danh sách job, alias tài khoản, loại GPU, runtime đã cấp, thời gian sử dụng, hạn giữ máy, số đoạn đã xác minh, thông báo lỗi và đường dẫn WAV. Hiện cả trạng thái job lẫn trạng thái runtime để phân biệt **Audio đã xong, đang chờ trả máy** với **Hoàn tất**. Các giai đoạn khởi tạo gồm **Chờ**, **Đang cấp máy**, **Đang tải model**, **Đang tạo**, **Đang kiểm tra WAV** và **Đang trả máy**. [Điện toán Colab](C:/Coder/tts-voice-cloning-OMNI/src/omni_tts_ui_qt/pages/remote_compute_section.py:42)

| Điều khiển | Tác dụng |
| --- | --- |
| **Tạm dừng cấp việc** | Ngừng cấp đoạn và job mới. Đoạn đang chạy được hoàn thành. Hạn giữ máy vẫn áp dụng. |
| **Tiếp tục** | Đối soát máy, worker và đoạn đã xác minh rồi tiếp tục phần còn thiếu. |
| **Hủy job** | Yêu cầu hủy và chờ broker xác nhận trạng thái cuối. Giữ các WAV đã xác minh. Khi hai sự kiện hoàn thành và hủy đến sát nhau, giao dịch broker quyết định trạng thái nào được chốt trước. |
| **Giải phóng runtime** | Dừng cấp việc cho đúng runtime của Studio. Hiện job bị ảnh hưởng, xử lý hủy hoặc chờ đoạn hiện tại theo lựa chọn, rồi xác nhận nhà cung cấp đã trả máy. |
| **Kết nối lại** | Tạm dừng hành động trên tài khoản đó. Người dùng xác nhận với Google. Bộ điều phối kiểm tra lại chủ tài khoản, đối soát runtime cũ và phục hồi từ hàng đợi. |

## Chính sách vận hành

- Người dùng chọn tài khoản, model, thư mục xuất, quyền tự cấp và trả máy, số runtime tối đa và trần thời gian. Pilot dùng một runtime và trả khi hết hàng. Tùy chọn giữ ấm có thời hạn chỉ bật sau khi đã đo thời gian tải model và mức tiêu tài nguyên.
- Thử lại lỗi mạng và thiếu GPU tạm thời với giới hạn và thời gian chờ. Với OAuth hết quyền, quota hoặc hết Compute Units, ghi trạng thái chờ và báo rõ nguyên nhân. Việc chọn tài khoản khác là lựa chọn của người dùng cho công việc được phép. [Giới hạn Colab](https://research.google.com/colaboratory/faq.html)
- Nếu hết hạn thời gian giữa batch, ngừng cấp đoạn mới, giữ WAV đã xác minh và trả runtime sau khi chốt công việc đang chạy hoặc hết thời hạn dừng. Phục hồi phần thiếu theo chính sách người dùng đã bật. Nếu mất quyền khi trả máy, giữ ID và trạng thái **Cần trả máy** để đối soát ngay khi có lại quyền.
- Agent dùng công cụ TTS có cấu trúc. `start_text_generation`, `start_file_generation`, `get_job`, `list_jobs` và `cancel_job` dùng chung sổ trạng thái với Qt. Thêm trạng thái runtime và thao tác pause/resume/release theo chính sách. Mã dùng với `execute_code` nằm trong adapter, với tham số được xác thực. [Studio MCP](C:/Coder/tts-voice-cloning-OMNI/docs/mcp-server.md)

## Tệp dự kiến

- Sửa [remote_compute_section.py](C:/Coder/tts-voice-cloning-OMNI/src/omni_tts_ui_qt/pages/remote_compute_section.py:42) và [broker_control.py](C:/Coder/tts-voice-cloning-OMNI/src/omni_tts_ui_qt/widgets/broker_control.py) để hiển thị trạng thái và chặn tắt broker giữa job managed cho đến khi người dùng chọn cách xử lý.
- Sửa [server.py](C:/Coder/tts-voice-cloning-OMNI/src/colin_studio_tts_mcp/server.py) để kết nối IPC, giữ các công cụ job hiện có và thêm điều khiển runtime cần thiết. Cập nhật [mcp-server.md](C:/Coder/tts-voice-cloning-OMNI/docs/mcp-server.md) khi đã có giao diện chạy được.

## Tiêu chí bàn giao

- [ ] Từ Studio và MCP nhìn cùng một job đang chạy. Đóng Qt, ngắt MCP và mở lại vẫn thấy tiến độ.
- [ ] Thử tạm dừng, tiếp tục, hủy khi đang tạo, kết nối lại và trả máy. Kiểm tra trạng thái cuối từ cả broker lẫn Colab theo đúng ID.
- [ ] Thử runtime mất giữa batch, PC khởi động lại, quyền bị thu hồi và lỗi khi trả máy. Khôi phục được các đầu ra đã xác minh, hiện nguyên nhân nếu cần người dùng xử lý.
- [ ] Xác nhận một batch ngắn và một mẫu clone có quyền sử dụng. Kiểm tra số đoạn, định dạng WAV và nghe mẫu trước khi bật chế độ tự động thường xuyên.
