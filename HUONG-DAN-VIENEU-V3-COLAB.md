# VieNeu v3 qua Colab: giọng dựng sẵn và clone từ Profile

Áp dụng cho Colin TTS Studio Qt, VieNeu v3 Turbo SDK **3.6.4**, audio mono 48 kHz.
Không dùng model Ngọc Huyền 0.3B cũ. **Ngọc Huyền trong danh sách 23 preset v3 vẫn có đầy đủ.**

## 1. Mở một worker VieNeu trên Colab

1. Trên PC, bấm [Check-Colab.bat](C:/Coder/tts-voice-cloning-OMNI/Check-Colab.bat). Broker phải báo `ok`. Nếu không, bấm [Start-Compute-Broker.bat](C:/Coder/tts-voice-cloning-OMNI/Start-Compute-Broker.bat).
2. Đăng nhập tài khoản Google bạn muốn dùng tại [Google Colab](https://colab.research.google.com/).
3. Chọn **File > Upload notebook** rồi mở notebook đúng tài khoản:

   - [Google AI Pro 1: VieNeu v3](D:/_coder/colin-tts-compute-service/colab/Colin-TTS-VieNeu-v3-google-pro-1.ipynb)
   - [Google AI Pro 2: VieNeu v3](D:/_coder/colin-tts-compute-service/colab/Colin-TTS-VieNeu-v3-google-pro-2.ipynb)
   - [Google AI Pro 3: VieNeu v3](D:/_coder/colin-tts-compute-service/colab/Colin-TTS-VieNeu-v3-google-pro-3.ipynb)

4. Trong **Secrets**, tạo hoặc cập nhật hai secret, bật **Notebook access**:

   | Secret | Giá trị |
   | --- | --- |
   | `COLIN_GITHUB_TOKEN` | GitHub fine-grained token có `Contents: Read-only` cho repository private `colin-dmme/colin-tts-compute-service` |
   | `COLIN_COMPUTE_BROKER_TOKEN` | Nội dung tệp [broker-token.txt](C:/Coder/colin-tts-compute-runtime/secrets/broker-token.txt) |

   Token broker đã đổi khi phục hồi ổ D. Không dán token vào ô code, chat hoặc commit lên GitHub.

5. Chọn **Runtime > Change runtime type > GPU**. Cell đầu giữ `COMPUTE_PROVIDER = 'vieneu_v3'`, `VIENEU_DEVICE = 'cuda'`.
6. Chạy lần lượt ba cell code. Lần đầu cần tải môi trường và model. Chờ dòng `COLIN TTS COMPUTE WORKER READY` có `vieneu_v3_turbo:cuda`.
7. Giữ cell cuối đang chạy trong lúc dùng Studio. Dừng runtime khi xong để tránh tiêu tốn tài nguyên không cần thiết.

Nếu muốn chạy CPU trên Colab, đổi `VIENEU_DEVICE = 'cpu'` và chọn runtime không GPU. Worker sẽ công bố `vieneu_v3_turbo:cpu`. Khi chọn CUDA mà Colab chưa cấp GPU, notebook báo lỗi rõ ràng, không âm thầm đổi sang CPU.

Notebook giữ model trong RAM giữa các job; GPU nhận tối đa 4 đoạn mỗi batch từ Studio. Không cần tải model VieNeu hoặc cài CUDA trên PC nếu chỉ dùng chế độ Colab.

## 2. Đọc bằng preset Ngọc Huyền v3

1. Đóng và mở lại Studio bằng [run_qt.bat](C:/Coder/tts-voice-cloning-OMNI/run_qt.bat) để nạp mã mới.
2. Chọn nhà cung cấp **VieNeu**, model **VieNeu v3 Turbo 3.6.4 · 48 kHz**.
3. Ở thiết bị, chọn **Colab từ xa · preset + clone giọng**.
4. Trong **Điện toán Colab**, chọn tài khoản đang chạy notebook, bấm **Kiểm tra kết nối**. Cần thấy `online · CUDA · preset + clone` hoặc `CPU` nếu bạn chọn CPU.
5. Chọn nguồn giọng **23 giọng dựng sẵn VieNeu v3.6.4** rồi preset **Ngọc Huyền · Nữ · Bắc · Tự nhiên**. Có thể chọn bất kỳ preset nào trong 23 giọng.
6. Thử một câu ngắn trong tab **Văn bản**, bấm **Tạo giọng đọc**, rồi nghe thử.

Không chọn các model Ngọc Huyền cũ trong danh sách model. Tên preset giống nhau không đồng nghĩa cùng model.

## 3. Clone giọng từ audio mẫu

1. Chuẩn bị audio của bạn hoặc giọng bạn được phép sử dụng: một người nói rõ, không nhạc nền, ít vang và không có giọng khác xen vào.
2. Trong phần quản lý giọng/Profile của Studio, tạo hoặc chọn Profile chứa audio mẫu. Nên dùng **3..5 giây**, tối đa khoảng **8 giây** hữu ích với SDK hiện tại. Không cần bản chép lời cho VieNeu v3.
3. Vẫn chọn model VieNeu v3 và thiết bị Colab như mục 2.
4. Chuyển nguồn giọng sang **Clone từ Profile (3-5 giây)**, chọn Profile cần clone. Khi đó audio Profile được dùng, không phải preset đang hiển thị trước đó.
5. Thử một câu có nội dung khác audio mẫu trước, nghe và chỉnh audio mẫu nếu cần. Sau đó mới chạy văn bản dài hoặc hàng đợi tệp.

Studio chuyển audio mẫu thành WAV PCM mono rồi gửi qua HTTPS tới broker có xác thực. Chỉ mã SHA-256 của audio được đặt trong job; đường dẫn tệp cá nhân trên PC không gửi vào job. Worker tải đúng audio theo hash và kiểm tra hash trước khi dùng.

Audio mẫu được giữ tại `C:\Coder\colin-tts-compute-runtime\reference_audio` để tái sử dụng. Worker Colab có cache WAV tạm và cache mã giọng trong RAM; đổi/đóng runtime sẽ mất cache Colab. Cache RAM tối đa 16 giọng theo audio + thiết lập khử nhiễu. Không đưa audio mẫu hoặc token lên GitHub. Việc lưu cache broker chưa có tự xóa theo thời hạn; không dùng bản ghi nhạy cảm nếu bạn không muốn lưu bản sao ở đó.

Giới hạn truyền audio mẫu là 10 MiB và 0,1..30 giây để chặn đầu vào lỗi; SDK chỉ sử dụng khoảng 8 giây sau xử lý, nên gửi bản ngắn, sạch. Clone không bảo đảm giống hoàn toàn; chất lượng bản thu và nội dung tiếng Việt ảnh hưởng rõ rệt.

## 4. Ba tài khoản và chuyển khi lỗi

Mỗi tài khoản dùng notebook tương ứng `google-pro-1`, `google-pro-2`, `google-pro-3`. Bạn tự đăng nhập Google. Studio không lưu cookie, mật khẩu hoặc tự mở runtime Google.

**Mỗi WORKER_ID chỉ chạy một notebook tại một thời điểm.** Notebook ZeroTTS và VieNeu của tài khoản 1 dùng chung ID `google-pro-1`: dừng cái cũ trước khi mở cái mới. Ba tài khoản có thể chọn model khác nhau, nhưng worker dự phòng chỉ được dùng khi đang chạy đúng model và hỗ trợ tính năng job yêu cầu.

Ở **Khi worker lỗi**, có ba tùy chọn:

- **Chỉ worker đã chọn:** không tự chuyển.
- **Hỏi trước khi chuyển:** Studio hỏi khi cần dùng worker dự phòng.
- **Tự chuyển khi có lỗi:** chỉ chuyển sau lỗi có thể thử lại hoặc worker offline. Không xoay tài khoản sau mỗi job thành công. Trong cùng lượt sinh nhiều batch, Studio giữ worker vừa chạy thành công sau khi chuyển.

Để dự phòng VieNeu, worker dự phòng cũng phải chạy VieNeu v3 mới. Worker chỉ chạy ZeroTTS không nhận nhầm job clone VieNeu. Nếu Colab mất hẳn kết nối lúc đang xử lý, Studio có thể cần chờ lease hết hạn, tối đa khoảng 5 phút kể từ lần gia hạn cuối, rồi mới chuyển an toàn.

Chỉ dùng các runtime/tài khoản có quyền chạy tác vụ này. Google cấm dùng nhiều tài khoản để vượt giới hạn; Google AI Pro trả phí đủ điều kiện có thể kèm compute units nhưng gói dùng thử không được áp dụng quyền lợi đó. Kiểm tra **Settings > Subscription** và tài nguyên thực tế của từng tài khoản: [Colab FAQ](https://research.google.com/colaboratory/faq.html). Đây là dự phòng worker do bạn chủ động mở, không phải cơ chế vượt quota.

## 5. Lỗi thường gặp

| Hiện tượng | Cách xử lý |
| --- | --- |
| Không thấy thiết bị Colab cho VieNeu | Mở lại `run_qt.bat`, chọn đúng VieNeu v3 Turbo, không phải v2/Ngọc Huyền 0.3B |
| Online nhưng báo model khác | Dừng notebook ZeroTTS của tài khoản đó, mở notebook VieNeu v3 |
| Notebook cũ, thiếu clone/batch | Upload bản notebook VieNeu v3 mới và chạy lại |
| CUDA không khả dụng | Chọn GPU runtime, hoặc chủ động chuyển `VIENEU_DEVICE='cpu'` |
| HTTP 401 hoặc 403 | Kiểm tra token broker, quyền truy cập và hạn dùng token; không tự thử token khác |
| Clone nghe không đúng | Kiểm tra đúng Profile, cắt mẫu sạch 3..5 giây, tránh nhạc hoặc nhiều người nói |
| Không có worker phù hợp | Mở notebook đúng model hoặc chọn CPU local để làm việc trong lúc chờ |

Broker chạy trên PC, nên khi dùng Colab cần giữ PC bật, có mạng và task broker hoạt động. Tên miền vẫn là `https://tts-compute.tainguyenso.online`; không cần port cố định. Supervisor tự chọn port trống trong dải `18787..18849`.

## 6. Kiểm chứng và thư mục nguồn

- Studio: `C:\Coder\tts-voice-cloning-OMNI`.
- Compute service private: `D:\_coder\colin-tts-compute-service`.
- Dữ liệu/khóa broker: `C:\Coder\colin-tts-compute-runtime`.
- Script thử audio thật: `scripts/verify_vieneu_compute.py`. Script tạo worker tạm **trên PC**, gửi preset và clone qua broker, không đổi lựa chọn worker đang lưu của bạn.

Chưa có xác nhận chạy thành công trên runtime Google Colab của bạn nếu bạn chưa đăng nhập và chạy notebook. Kiểm thử worker PC qua broker không thay thế bằng chứng GPU/Colab thực tế.

Ngày 16/10/2026 đã thử thật qua broker công khai với worker CPU trên PC: 2 đoạn preset Ngọc Huyền v3, 2 đoạn clone từ audio preset vừa tạo và 1 đoạn clone tái sử dụng cùng mẫu; tất cả WAV mono 48 kHz, dài 2,80..3,60 giây, không rỗng/không im lặng. Bài thử này xác nhận luồng clone và truyền file, không đánh giá độ giống giọng của Profile riêng của bạn. Mẫu và SHA-256 được giữ trong [thư mục kiểm tra](C:/Coder/tts-voice-cloning-OMNI/outputs/vieneu-colab-20261016-pc-check/verification.json).
