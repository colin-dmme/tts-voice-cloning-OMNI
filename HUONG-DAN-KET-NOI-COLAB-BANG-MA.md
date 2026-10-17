# Kết nối Colab bằng mã — không cần Secrets

Áp dụng cho Colin TTS Studio Qt, VieNeu v3 Turbo 3.6.4 (preset + clone Profile) và ZeroTTS.

Broker trên PC có thể chạy nền hoàn toàn, không cần giữ cửa sổ đen. Trong **Điện toán Colab**, bấm **Trạng thái / Bật tắt broker nền**, hoặc mở [Manage-Compute-Broker.vbs](C:/Coder/tts-voice-cloning-OMNI/Manage-Compute-Broker.vbs) khi chưa mở Studio. Xem [cách bật/tắt và kiểm tra broker nền](C:/Coder/tts-voice-cloning-OMNI/HUONG-DAN-QUAN-LY-BROKER-NEN.md).

## Dùng mỗi ngày

1. Giữ PC bật và có mạng. Bấm [Check-Colab.bat](C:/Coder/tts-voice-cloning-OMNI/Check-Colab.bat). Broker cần báo `ok`; chưa chạy notebook thì worker báo `OFFLINE` là bình thường.
2. Mở [run_qt.bat](C:/Coder/tts-voice-cloning-OMNI/run_qt.bat). Chọn model **VieNeu v3 Turbo** và thiết bị **Colab từ xa** (hoặc ZeroTTS nếu muốn dùng ZeroTTS).
3. Mở **Điện toán Colab**, chọn **Google AI Pro 1**, **2** hoặc **3**, rồi bấm **Kết nối Colab bằng mã**.
4. Trong cửa sổ mới, bấm **1. Mở notebook Colab**. Kiểm tra đúng tài khoản Google ở góc phải Colab. Nếu muốn lưu bản riêng, chọn **File > Save a copy in Drive**; bản này không chứa khóa.
5. Trong notebook, chọn:

   - `COMPUTE_PROVIDER = vieneu_v3` để dùng VieNeu v3. Chọn `VIENEU_DEVICE = cuda` với runtime GPU, hoặc `cpu` với runtime không GPU.
   - `COMPUTE_PROVIDER = zerotts` để dùng ZeroTTS. Worker ZeroTTS hiện dùng CPU, nên chọn runtime không GPU để tránh lãng phí.

6. Bấm chạy **cell code duy nhất**. Colab có thể yêu cầu bạn xác nhận chạy notebook hoặc cấp runtime; đọc thông báo rồi tự xác nhận nếu đồng ý. Đăng nhập/2FA/CAPTCHA do bạn thực hiện. Chưa cần mở Secrets.
7. Khi notebook hiện `MÃ GHÉP NỐI: ABCD-EFGH`, sao chép mã đang hiện đó sang ô mã trong Studio. `ABCD-EFGH` ở đây chỉ là ví dụ, không phải mã cố định.
8. Bấm **2. Kiểm tra mã**. Studio phải hiện đúng worker, model và CPU/CUDA bạn vừa chọn. Chỉ khi đúng notebook của bạn mới bấm **3. Xác nhận ghép nối**.
9. Quay lại Colab, chờ tải source, môi trường và model. **Đã ghép nối chưa có nghĩa model đã sẵn sàng.** Chờ dòng `COLIN TTS COMPUTE WORKER READY`.
10. Giữ cell Colab đang chạy, đóng cửa sổ ghép nối trong Studio rồi bấm **Kiểm tra kết nối**. Khi thấy worker online đúng model, bạn có thể tạo audio.

Trong VieNeu v3, chọn **23 giọng dựng sẵn** → **Ngọc Huyền** để dùng preset, hoặc **Clone từ Profile** để dùng mẫu giọng của bạn. Không cần model Ngọc Huyền 0.3B cũ. Cách chuẩn bị mẫu sạch, preset, clone và hàng đợi xem [hướng dẫn VieNeu đầy đủ](C:/Coder/tts-voice-cloning-OMNI/HUONG-DAN-VIENEU-V3-COLAB.md).

## Hai nút cần nhớ

- **Kết nối Colab bằng mã:** ghép notebook bạn chủ động chạy với đúng worker trong Studio.
- **Ngắt quyền Colab:** thu hồi ngay các phiên **ghép nối mới** của worker đang chọn. Không xóa tài khoản Google, notebook, model hay Secrets. Job đang chạy có thể bị gián đoạn.

Khi dùng xong, dừng cell và chọn **Runtime > Disconnect and delete runtime** trên Colab để trả máy tạm. Thao tác này không xóa notebook đã lưu trên Drive. Có thể ngắt quyền trong Studio trước/sau khi dừng; chỉ thu hồi quyền mà không dừng runtime không đảm bảo Google ngừng tính tài nguyên.

## Vì sao cách mới không cần token?

Bạn vẫn được xác thực, nhưng hệ thống làm phần quản lý khóa thay bạn:

1. Notebook xin một mã ngắn có hiệu lực **10 phút**. Lúc này chưa được tải source private hay nhận job.
2. Bạn đối chiếu và duyệt mã trong Studio trên PC. Studio giữ khóa quản trị broker tại PC, không đưa khóa đó sang Colab.
3. Broker cấp **khóa worker riêng của phiên**: chỉ worker/model/thiết bị vừa duyệt, tối đa **12 giờ**. Khóa nằm trong bộ nhớ và môi trường tiến trình runtime, không viết vào notebook, URL hoặc Git. Không lưu khóa này vào Secrets.
4. Worker tải gói source cần thiết từ PC qua HTTPS và kiểm tra SHA-256. Gói chỉ lấy các tệp worker đã commit trong hai repo, không đóng gói thư mục dữ liệu, khóa, audio hay file chưa được Git theo dõi. Repo compute service vẫn private; không cần token GitHub trên Colab.

Worker ghép nối không được tạo/hủy job hoặc xem danh sách công việc của Studio. Với clone giọng, chỉ được tải audio mẫu của job đang có lease thuộc chính worker đó. Nội dung audio mẫu vẫn được gửi tới Colab để chạy clone; ghép nối không làm thay đổi nơi xử lý audio.

Giữ mã ghép nối cho mình và chỉ xác nhận mã bạn vừa thấy trong notebook của bạn. Nếu người khác gửi mã nhờ duyệt thì không duyệt: bạn có thể vô tình cho máy của họ tải source và nhận công việc.

## Lần sau có phải làm lại không?

- Runtime cũ còn chạy và phiên chưa hết hạn: không cần ghép lại.
- Colab cấp runtime mới, bạn chạy lại cell, hoặc phiên hết 12 giờ: lấy mã mới và duyệt lại. Không cần vào GitHub tạo khóa.
- Mỗi `WORKER_ID` chỉ chạy một notebook. Dừng notebook cũ trước khi chạy lại/đổi model; ghép phiên mới sẽ thu hồi phiên ghép nối cũ cùng worker.
- Nếu worker còn đang xử lý job, broker từ chối thay phiên để tránh cắt ngang audio. Chờ hoàn tất rồi dừng notebook cũ và ghép lại.

Thời hạn 12 giờ là giới hạn quyền của ứng dụng, **không phải** cam kết Colab sẽ cấp GPU hoặc giữ runtime 12 giờ. Không có thao tác giả giữ phiên, tự đăng nhập Google hoặc tự mở thêm tài khoản. Dự phòng của Studio vẫn chỉ chuyển khi lỗi theo chính sách bạn chọn; không dùng nhiều tài khoản để vượt giới hạn Google.

## Ba tài khoản: mở đúng notebook

- [Mở Colab cho Google AI Pro 1](https://colab.research.google.com/github/colin-dmme/tts-voice-cloning-OMNI/blob/main/colab/Colin-TTS-Pairing-google-pro-1.ipynb)
- [Mở Colab cho Google AI Pro 2](https://colab.research.google.com/github/colin-dmme/tts-voice-cloning-OMNI/blob/main/colab/Colin-TTS-Pairing-google-pro-2.ipynb)
- [Mở Colab cho Google AI Pro 3](https://colab.research.google.com/github/colin-dmme/tts-voice-cloning-OMNI/blob/main/colab/Colin-TTS-Pairing-google-pro-3.ipynb)

Các số 1/2/3 là nhãn worker do bạn quản lý, không tự xác minh danh tính tài khoản Google. Bạn phải kiểm tra Google đang đăng nhập đúng tài khoản muốn dùng. Không cần tạo Secrets trên tài khoản 2/3 khi dùng notebook `Colin-TTS-Pairing-...` này.

Nếu Colab không mở trực tiếp được GitHub, [tải notebook tài khoản 1 từ broker](https://tts-compute.tainguyenso.online/colab/notebooks/google-pro-1.ipynb) (đổi số 1 thành 2/3 trong địa chỉ nếu cần), rồi **File > Upload notebook**. Các notebook ghép nối công khai này không chứa khóa hay mã nguồn compute service private.

## Khi gặp lỗi

| Thông báo/hiện tượng | Bạn cần làm gì? |
| --- | --- |
| Notebook vẫn hỏi `COLIN_GITHUB_TOKEN` | Đang mở notebook Secrets cũ. Mở `Colin-TTS-Pairing-...` theo liên kết trên |
| Không kết nối được broker | Giữ PC bật/có mạng, chạy `Check-Colab.bat`; nếu cần chạy `Start-Compute-Broker.bat` |
| Broker chưa có gói source worker / HTTP 503 | Cần cập nhật compute service trên PC và khởi động lại broker; không chữa bằng cách đưa repo sang public |
| Không tìm thấy mã / mã hết hạn | Chép đúng mã notebook hiện tại. Nếu quá 10 phút, dừng/chạy lại cell để lấy mã mới |
| Quá nhiều yêu cầu / HTTP 429 | Chờ ít nhất một phút; không chạy lại notebook hoặc gửi mã liên tục |
| Worker/model không khớp | Chọn đúng worker/model ở Studio và notebook. Chưa khớp thì không duyệt |
| Không rõ yêu cầu xác nhận đã thành công chưa | Xem notebook trước. Không bấm gửi lại nhiều lần; nếu cần, ngắt quyền rồi lấy mã mới |
| Đã ghép nhưng Studio vẫn offline | Chờ cài môi trường/model và dòng `WORKER READY`; xem lỗi cài đặt trên Colab nếu có |
| CUDA không khả dụng | Kiểm tra GPU runtime; nếu không được cấp GPU, chủ động chọn CPU và ghép lại đúng thiết bị |
| Phiên bị ngắt/hết hạn / HTTP 401 | Chạy lại cell, lấy mã mới. Không dán khóa quản trị vào notebook |
| Muốn cập nhật mã nguồn worker | Commit bản cần dùng trên PC, khởi động lại broker để tạo gói mới, rồi chạy notebook/ghép lại. Gói lấy từ Git HEAD, không lấy thay đổi chưa commit |

## Cách Secrets cũ có mất không?

Không. Các notebook `Colin-TTS-VieNeu-v3-...` và `Colin-TTS-Worker-...` cũ vẫn được giữ để dự phòng, không tự xóa token đã tạo. Chỉ chúng mới cần hai Secrets và quan tâm hạn token GitHub. **Notebook ghép nối mới không phụ thuộc hạn token GitHub 15/11/2026.**

Nút **Ngắt quyền Colab** chỉ thu hồi khóa phiên mới, không thu hồi khóa quản trị trong Secrets cũ. Muốn ngừng worker cũ thì dừng notebook đó; muốn thu hồi khóa cũ phải đổi khóa đồng bộ như hướng dẫn Secrets. Không chạy notebook cũ và mới cùng worker ID.

## Phạm vi kiểm chứng

Kiểm thử tự động bao gồm mã hết hạn/dùng một lần, duyệt đồng thời, khóa giới hạn worker/model, thu hồi từng worker, chặn đường dẫn ZIP và quyền audio theo lease. Kiểm tra runtime trên PC qua broker không thay thế kiểm chứng GPU thật trên Colab; chỉ khi notebook thực sự báo READY và tạo audio mới xác nhận Colab chạy thành công.

Ngày **16/10/2026**: bộ kiểm thử Studio 453 bài và service 50 bài đều qua. Đã tạo audio thật trên PC bằng worker có khóa phiên giới hạn: preset Ngọc Huyền v3 (3,60 giây) và clone (2,56 giây), WAV mono 48 kHz; thu hồi xong thì khóa cũ bị từ chối. Đã thử riêng vòng ghép nối → duyệt → tải/kiểm SHA-256 gói source → thu hồi qua tên miền HTTPS thật, không đăng ký worker công khai hay chạy Colab. Báo cáo ở [verification.json](C:/Coder/tts-voice-cloning-OMNI/outputs/pairing-20261016-pc-check/verification.json) và [public-handshake.json](C:/Coder/tts-voice-cloning-OMNI/outputs/pairing-20261016-pc-check/public-handshake.json).
