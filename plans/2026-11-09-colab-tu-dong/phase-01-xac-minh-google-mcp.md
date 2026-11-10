# Pha 1. Xác minh Colab MCP và quyền cấp GPU

## Mục tiêu

Chứng minh một tài khoản Google AI Pro đã chọn có thể cấp một GPU Colab, chạy mã CUDA và trả đúng máy bằng MCP từ PC Windows. Ưu tiên thực hiện pha này trước khi sửa luồng tạo giọng.

## Thiết kế

- Dùng Colab MCP từ xa tại `https://colaboratory.googleapis.com/mcp`. Thử kết nối sau khi bật API/MCP và đăng ký OAuth Desktop. Cho người dùng xác nhận trên trang OAuth của Google. Dùng PKCE, phạm vi `colaboratory` và quyền nhận diện tối thiểu cần để kiểm tra đúng chủ. Giữ refresh token trong kho bí mật Windows của tài khoản chạy bộ điều phối. Sau khi khởi động lại, thử refresh trong tiến trình nền. Nếu Google từ chối hoặc người dùng thu hồi quyền, chuyển sang **Cần kết nối lại**. OAuth External ở chế độ Testing có thể cấp refresh token hết hạn sau 7 ngày với phạm vi này. [Xác thực Google MCP](https://docs.cloud.google.com/mcp/set-up-authentication-mcp-servers) · [OAuth Desktop](https://developers.google.com/identity/protocols/oauth2/native-app) · [Hạn refresh token](https://developers.google.com/identity/protocols/oauth2#expiration)
- Gắn nhãn tài khoản `google-pro-1` với danh tính Google đã xác minh sau khi đồng ý. Kiểm tra `get_subscription` và `list_runtime_specs` trước khi cho phép yêu cầu máy. `get_subscription` cho biết bậc gói. `list_runtime_specs` cho biết cấu hình được quyền yêu cầu. Quyền cấp được máy, số dư Compute Units và lượng GPU sẵn có là các kiểm tra riêng. Chỉ hiển thị số dư nếu có nguồn chính thức trả về. [Gói Colab](https://developers.google.com/colab/api/reference/mcp/tools_list/get_subscription) · [Quyền lợi Google AI](https://research.google.com/colaboratory/faq.html)
- Giới hạn pilot ở một runtime có thời hạn ngắn, loại GPU đã được người dùng cho phép và chính sách tự trả máy đã bật. Ghi `runtimeId` và UUID `requestId` trước `create_runtime`. Đối soát operation hoặc `get_runtime` theo đúng ID nếu chưa nhận được kết quả. `create_session` cho phép đặt ID phiên riêng. Chạy probe ngắn bằng `execute_code`, xác minh `torch.cuda.is_available()` và tên GPU. Trả máy với `delete_runtime` theo ID đã lưu, rồi kiểm tra máy không còn được cấp. [Tạo runtime](https://developers.google.com/colab/api/reference/mcp/tools_list/create_runtime) · [Thực thi mã](https://developers.google.com/colab/api/reference/mcp/tools_list/execute_code) · [Trả runtime](https://developers.google.com/colab/api/reference/mcp/tools_list/delete_runtime)
- Dùng `requestId` gốc cho lần cấp chưa rõ kết quả. `executionId` chỉ nối lại phiên gọi còn giữ kết quả, nên mỗi đoạn bootstrap có tác dụng phụ cần kiểm tra dấu trạng thái của chính ứng dụng trước khi chạy lại. Chỉ lưu ID, trạng thái và log đã lọc. Loại thông tin kết nối, khóa proxy, mã cấp quyền và token khỏi log. [Hợp đồng Colab MCP](https://developers.google.com/colab/api/reference/mcp)

## Tệp đã triển khai

- Adapter tại `C:/Coder/tts-voice-cloning-OMNI/src/colin_colab_remote/google_mcp.py`; OAuth và kho DPAPI tại `oauth.py` trong cùng package.
- Kiểm thử provider tại `C:/Coder/tts-voice-cloning-OMNI/tests/test_colab_google_provider.py`; kiểm thử đối soát bootstrap và giải phóng tại `test_colab_managed_lifecycle.py`.

## Tiêu chí qua pha

- [x] OAuth nhận đúng tài khoản. Tiến trình Python riêng refresh được quyền sau khi cửa sổ cấp quyền đã hoàn tất.
- [ ] Tạo một runtime, xác nhận GPU thực và thực thi probe. Mô phỏng mất phản hồi sau khi cấp máy, đối soát lại đúng runtime đã ghi.
- [ ] Xác nhận đã trả đúng runtime. Giữ nguyên các runtime mở tay của người dùng.
- [ ] Lỗi đăng nhập, thiếu GPU, thiếu hạn mức và lỗi API hiện các trạng thái riêng. Khi tài khoản thiếu hạn mức, job chờ theo chính sách và báo người dùng. [Giới hạn Colab](https://research.google.com/colaboratory/faq.html)

## Kết quả kiểm tra ngày 09/11/2026

Đã bật Colab API, tạo Desktop OAuth client và cấp quyền. `get_subscription` báo Free; Settings → Subscription chưa có quyền lợi trả phí. T4 xuất hiện với `eligible=true` trong danh sách cấu hình, nhưng điều đó chưa chứng minh cấp máy thành công hoặc có Compute Units. Lệnh cấp máy CPU thử trả `Precondition check failed.`. Đã đối soát giải phóng đúng ID máy thử và `list_runtimes` cuối cùng trống. Chưa xác minh CUDA hay audio qua worker thật.

75 kiểm thử provider, lifecycle, supervisor và compatibility đạt. Broker HTTP trên PC và HTTPS tại `tts-compute.tainguyenso.online` cùng báo `status=ok`, `managed_colab=enabled`. Chế độ tự cấp máy vẫn tắt và chưa cài task supervisor tự chạy khi đăng nhập, chờ hoàn tất pilot với tài khoản có quyền lợi phù hợp.

Nếu tài khoản chưa dùng được Colab MCP, giữ đường ghép mã hiện tại và thử CLI chính thức trong WSL2 như một thử nghiệm riêng. Tiêu chí chuyển phương án là cấp máy, xác minh CUDA và trả đúng runtime qua kênh chính thức. [Colab CLI](https://github.com/googlecolab/google-colab-cli)
