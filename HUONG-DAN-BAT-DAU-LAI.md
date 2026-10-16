# Colin TTS: bắt đầu lại sau sự cố ổ D

Ngày kiểm tra: 16/10/2026, giờ Bangkok/Việt Nam.

Bạn có thể dùng ZeroTTS ngay trên máy. Phần Colab cần bạn đăng nhập Google và cập nhật token mới một lần.

## 1. Mở và thử ngay trên máy

1. Mở thư mục `C:\Coder\tts-voice-cloning-OMNI`.
2. Bấm đúp `run_qt.bat`. Đây là giao diện Colin TTS Studio có phần Điện toán Colab. File `Start-ColinTTS.bat` mở giao diện Tkinter cũ.
3. Trong Studio, chọn nhà cung cấp **ZeroTTS** và model **ZeroTTS 202M Official**.
4. Chọn thiết bị **CPU ONNX trên máy**.
5. Chọn giọng cố định **Mai Chi**.
6. Vào tab **Văn bản**, dán: `Xin chào. Tôi đang thử lại Colin TTS sau khi khôi phục dữ liệu.`
7. Bấm **Tạo giọng đọc**. Xong thì bấm **Nghe thử** hoặc **Mở thư mục**.

Model và môi trường ZeroTTS trên C vẫn có. Chế độ CPU này không cần notebook Colab hay token broker.

Hai mẫu kiểm tra đã tạo được qua broker công khai, dùng worker tạm trên PC:

- [Mẫu kiểm tra khôi phục](C:/Coder/tts-voice-cloning-OMNI/outputs/recovery-20261016/kiem-tra-khoi-phuc.wav)
- [Mẫu kiểm tra broker tự khởi động](C:/Coder/tts-voice-cloning-OMNI/outputs/recovery-20261016/kiem-tra-broker-tu-khoi-dong.wav)

Cả hai là WAV 48 kHz, dài 3,28 giây. Đây là kiểm tra phần mềm và đường truyền; chưa phải kiểm thử trên máy Google Colab.

## 2. Công việc đã tới đâu

| Thành phần | Tình trạng đã xác minh |
| --- | --- |
| Studio | Source còn nguyên trên C; mốc trước sự cố `3456bc0` |
| Compute service | Đã clone lại từ GitHub private về `D:\_coder\colin-tts-compute-service`; mốc trước sự cố `1056f16` |
| Tên miền broker | `https://tts-compute.tainguyenso.online`, đã hoạt động trở lại |
| Cloudflare Tunnel | Giữ tunnel cũ `colin-tts-compute-home`, đã kết nối healthy |
| Dữ liệu broker và khóa | Chuyển sang `C:\Coder\colin-tts-compute-runtime` |
| Tự khởi động broker | Windows task `Colin TTS Compute Broker`, chạy khi đăng nhập |
| Ba profile Colab | `google-pro-1`, `google-pro-2`, `google-pro-3`; chưa có notebook Google nào online trong lần kiểm tra này |
| Chính sách chuyển | Đang là tự chuyển khi worker lỗi; không round-robin sau job thành công |
| Model ZeroTTS | Còn tại `C:\Coder\tts-voice-cloning-OMNI\models\zerotts\zeroweight-ai\ZeroTTS` |
| Lịch sử và hàng đợi | Database còn 652 mục lịch sử và 20 mục hàng đợi; kiểm tra SQLite đạt |

Studio gửi đoạn cần đọc đến broker. Worker nhận việc, sinh WAV rồi trả lại broker. Studio tải WAV về, ghép và lưu kết quả trên máy của bạn. Máy PC phải có mạng và broker phải chạy khi dùng Colab.

Port nội bộ được chọn tự động trong dải `18787-18849`. Bạn dùng tên miền cố định, không cần nhập port đang chọn.

## 3. Bật một tài khoản Colab trước

1. Đăng nhập tài khoản Google thứ nhất tại [Google Colab](https://colab.research.google.com/).
2. Chọn **File > Upload notebook**, mở file [Colin-TTS-Worker-google-pro-1.ipynb](D:/_coder/colin-tts-compute-service/colab/Colin-TTS-Worker-google-pro-1.ipynb).
3. Mở **Secrets** ở thanh bên. Tạo hoặc cập nhật đúng hai tên dưới đây, bật quyền notebook truy cập từng secret:

| Tên secret | Giá trị cần nhập |
| --- | --- |
| `COLIN_GITHUB_TOKEN` | GitHub fine-grained token có quyền đọc source private của `colin-dmme/colin-tts-compute-service` |
| `COLIN_COMPUTE_BROKER_TOKEN` | Toàn bộ nội dung trong [broker-token.txt](C:/Coder/colin-tts-compute-runtime/secrets/broker-token.txt) |

**Broker token đã đổi sau phục hồi.** Nếu từng cấu hình Colab trước đây, phải thay secret broker cũ. Không dán token vào ô code hoặc tin nhắn chat.

Nếu chưa có GitHub token: mở [trang fine-grained tokens](https://github.com/settings/personal-access-tokens), chọn chủ sở hữu `colin-dmme`, chỉ chọn repository private cần đọc, cấp **Contents: Read-only**. Hướng dẫn chính thức: [GitHub personal access tokens](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens).

4. Chọn runtime Python thông thường, bộ tăng tốc **None/CPU**. Backend ZeroTTS hiện dùng `CPUExecutionProvider`.
5. Chạy lần lượt ba cell code. Cell cuối chạy liên tục là trạng thái chờ nhận việc. Dòng sẵn sàng có `COLIN TTS COMPUTE WORKER READY` và `worker_id=google-pro-1`.
6. Trên PC, bấm [Check-Colab.bat](C:/Coder/tts-voice-cloning-OMNI/Check-Colab.bat). Khi đúng, `google-pro-1` hiện `ONLINE`.
7. Trong Studio, chọn ZeroTTS Official, đổi thiết bị thành **Colab từ xa**. Trong **Điện toán Colab**, chọn Google AI Pro 1, bấm **Kiểm tra kết nối**, rồi thử một câu ngắn ở tab Văn bản.

Sau khi tài khoản thứ nhất chạy được, làm tương tự với các notebook riêng:

- [Tài khoản 2](D:/_coder/colin-tts-compute-service/colab/Colin-TTS-Worker-google-pro-2.ipynb)
- [Tài khoản 3](D:/_coder/colin-tts-compute-service/colab/Colin-TTS-Worker-google-pro-3.ipynb)

Mỗi notebook dùng ID khác nhau. Bạn tự đăng nhập từng tài khoản; Studio không lưu cookie hay mật khẩu Google. Trạng thái gói Colab và compute units của từng tài khoản chưa được kiểm tra trong lần phục hồi này. Colab có hạn mức và quy định riêng về worker, đồng thời cấm dùng nhiều tài khoản để vượt hạn mức: [Colab FAQ](https://research.google.com/colaboratory/faq.html).

## 4. Chọn chính sách chuyển worker

- **Chỉ worker đã chọn:** lỗi thì dừng ở worker đó.
- **Hỏi trước khi chuyển:** khi có lỗi, Studio hỏi trước khi chuyển sang worker dự phòng đang online.
- **Tự chuyển khi có lỗi:** tự chọn worker dự phòng phù hợp sau lỗi retryable hoặc offline; không chuyển sau job thành công.

Nút **Quản lý worker** cho phép bật/tắt và sắp thứ tự dự phòng. Worker dự phòng phải thực sự đang chạy notebook.

## 5. Dữ liệu đã cứu được

- Khi bắt đầu kiểm tra, trên C còn 1.067 tệp WAV và 61 tệp JSON trong thư mục giọng. Số tệp JSON không đồng nghĩa với số profile giọng.
- Đã khôi phục 20 TXT của hàng đợi từ `request.json` lưu ngày 28/9/2026, vào đường dẫn cũ `D:\reup\41-nghich-thien-tv-local\labo-ac-mong-luan-hoi\06-TTS-INPUT`. Bản sao độc lập và manifest ở `C:\Coder\_recovery\colin-tts-20261016\recovered-inputs` và `queue-recovery-manifest.json`.
- Đã dựng lại thêm 16 TXT trong `D:\reup\41-nghich-thien-tv-local\150h-la-bo\FINAL` từ `split_units.json` của các job 31/8 và 1/9/2026. Đối chiếu đủ 14.738 đoạn đọc. Manifest ở `history-input-recovery-manifest.json` trong thư mục recovery trên C.
- Hai nhóm trên là nội dung đã từng gửi vào TTS. Không thể xác nhận các sửa đổi sau snapshot; nhóm 16 TXT giữ nội dung và thứ tự đoạn, không đảm bảo khoảng trắng giống tệp gốc.
- Sau phục hồi, 20/20 nguồn hàng đợi đọc được. Các đường dẫn D được lịch sử tham chiếu đã tồn tại trở lại. Lịch sử còn 81 đường dẫn nguồn H chưa tìm thấy ở đường dẫn cũ; chưa chỉnh sửa hay phục hồi nhóm H.
- Database broker cũ trên D chưa khôi phục được. Broker đang dùng database mới; lịch sử Studio trên C được giữ nguyên.

Lần này khôi phục phần Colin TTS và các đầu vào tìm được từ snapshot, không phải toàn bộ dữ liệu ổ D.

Các mục hàng đợi cũ vẫn giữ trạng thái để bạn xem lại. Nên thử một câu ở tab Văn bản trước, rồi chọn từng file cần chạy; không cần chạy lại toàn bộ 20 file ngay.

## 6. Nếu gặp lỗi

| Hiện tượng | Việc làm tiếp |
| --- | --- |
| Không thấy phần Điện toán Colab | Mở `run_qt.bat`, chọn đúng ZeroTTS 202M Official |
| `Broker: ok`, cả ba worker offline | Broker đã chạy; mở notebook của tài khoản bạn muốn dùng |
| Broker không kết nối được | Bấm `Start-Compute-Broker.bat`, xem log tại `C:\Coder\colin-tts-compute-runtime\logs` nếu vẫn lỗi |
| Colab trả HTTP 401 | Cập nhật secret broker bằng token mới trên C và chạy lại cell worker |
| Clone repository private bị từ chối | Kiểm tra `COLIN_GITHUB_TOKEN`, quyền Contents Read và ngày hết hạn |
| Thiếu secret hoặc notebook chưa được truy cập secret | Kiểm tra đúng tên và bật Notebook access trong Secrets |
| Colab ngắt runtime | Kết nối lại, chạy lại notebook; hoặc dùng CPU trên máy trong lúc đó |

## 7. Những thư mục cần giữ

- Studio: `C:\Coder\tts-voice-cloning-OMNI`.
- Dữ liệu broker, khóa và log: `C:\Coder\colin-tts-compute-runtime`.
- Source service có thể clone lại: `D:\_coder\colin-tts-compute-service`.
- Báo cáo và văn bản phục hồi: `C:\Coder\_recovery\colin-tts-20261016`.
- Bản sao phục hồi tạo trong lần này: `C:\Coder\_backups\colin-tts-recovery-20261016`.

Khóa không được đưa lên GitHub. Có thể khôi phục source từ GitHub, còn khóa và dữ liệu riêng cần giữ bản sao ngoài repository.
