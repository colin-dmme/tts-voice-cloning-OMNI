# VieNeu v3 qua Colab: giọng dựng sẵn và clone từ Profile

Áp dụng cho Colin TTS Studio Qt, VieNeu v3 Turbo SDK **3.6.4**, audio mono 48 kHz.
Không dùng model Ngọc Huyền 0.3B cũ. **Ngọc Huyền trong danh sách 23 preset v3 vẫn có đầy đủ.**

**Cách dễ hơn, nên dùng:** [Kết nối Colab bằng mã — không cần Secrets](C:/Coder/tts-voice-cloning-OMNI/HUONG-DAN-KET-NOI-COLAB-BANG-MA.md). Studio có nút **Kết nối Colab bằng mã**, dùng notebook `Colin-TTS-Pairing-...`; bạn không cần vào GitHub hay thiết lập Secrets cho tài khoản 2/3. Các phần Secrets dưới đây chỉ áp dụng cho notebook cũ để dự phòng. Phần chọn preset/clone của Studio vẫn dùng chung.

Notebook VieNeu v3 tài khoản 1 đã tải lên Drive ngày 16/10/2026, tên **Colin-TTS-VieNeu-v3-google-pro-1.ipynb**. Mở bằng đúng tài khoản Google đã dùng khi thiết lập; có thể tìm tên này trong Google Drive hoặc đánh dấu trang notebook riêng trong Chrome. Không đưa liên kết Drive cá nhân hay địa chỉ tài khoản vào tài liệu được push lên GitHub.

Phạm vi thiết lập lần này: hai Secret cho tài khoản trên và quyền đọc của notebook VieNeu v3 tài khoản 1. Chưa thiết lập giúp tài khoản 2/3, chưa khởi động runtime GPU và chưa có kết quả suy luận trên Google Colab. Mở notebook đã lưu không tự chạy model.

## Đọc trước: bạn đang dùng những gì?

Studio trên PC là nơi nhập văn bản, chọn giọng và nhận audio. Colab là máy tính từ xa chạy model; broker trên PC là nơi chuyển công việc và kết quả giữa hai bên. Vì vậy **PC vẫn phải bật và có mạng**, dù GPU xử lý nằm trên Colab.

Hai token dưới đây là hai chiếc chìa khóa khác nhau, không phải tên tài khoản hay mật khẩu Google:

| Tên Secret phải nhập chính xác | Dùng để làm gì? | Giá trị lấy ở đâu? |
| --- | --- | --- |
| `COLIN_GITHUB_TOKEN` | Cho Colab tải mã nguồn compute service từ repo GitHub private | GitHub tạo một chuỗi token sau khi bạn cấp quyền đọc đúng repo |
| `COLIN_COMPUTE_BROKER_TOKEN` | Cho worker xác thực với broker của bạn | **Nội dung bên trong** `C:\Coder\colin-tts-compute-runtime\secrets\broker-token.txt` |

**Name** là tên biến ở cột đầu; **Value** là chuỗi khóa thật. Không dán đường dẫn tệp, tên token `Colin-Colab`, hoặc dòng mô tả quyền vào Value. Không thêm dấu nháy, khoảng trắng hay xuống dòng. Đây không phải Gemini API key và không tự xuất hiện chỉ vì bạn có Google AI Pro.

## Thiết lập lần đầu: hai Secret

### A. Tạo khóa GitHub chỉ có quyền đọc

Nếu đã thiết lập xong thì bỏ qua phần này; không tạo token mới mỗi lần mở Colab.

1. Đăng nhập GitHub đúng tài khoản có repo `colin-dmme/colin-tts-compute-service`.
2. Mở [Fine-grained personal access tokens](https://github.com/settings/personal-access-tokens), chọn **Generate new token**. Nếu GitHub yêu cầu xác nhận mật khẩu/2FA, tự xác nhận ngay trên GitHub.
3. Đặt tên dễ nhớ, ví dụ `Colin-Colab`. Chọn thời hạn phù hợp, không mặc định dùng khóa không hết hạn.
4. **Resource owner:** `colin-dmme`. **Repository access:** chọn **Only select repositories**, chỉ chọn `colin-tts-compute-service`.
5. Trong **Repository permissions**, thêm **Contents: Read-only**. **Metadata: Read-only** là quyền đi kèm. Không cấp Contents Write, Administration hoặc toàn bộ repository.
6. Kiểm tra lại phạm vi rồi tạo token. Sao chép chuỗi khóa vừa hiện; GitHub chỉ hiện đầy đủ ở bước này. Lưu trong trình quản lý mật khẩu nếu muốn giữ một bản riêng, không lưu vào repo.
7. Dán chuỗi đó vào Value của Secret `COLIN_GITHUB_TOKEN` trên Colab như phần C.

Khóa `Colin-Colab` được tạo trong lần hỗ trợ ngày **16/10/2026**, đặt hạn **15/11/2026**. Sau ngày đó cần cập nhật khóa; đây không phải thời hạn sử dụng của phần mềm. Khóa chỉ đọc nguồn private, không được dùng để push commit.

### B. Lấy khóa broker hiện tại

1. Trên PC, mở tệp [broker-token.txt](C:/Coder/colin-tts-compute-runtime/secrets/broker-token.txt) bằng Notepad.
2. Sao chép đúng chuỗi bên trong, không sao chép tên/đường dẫn tệp.
3. Dán vào Value của Secret `COLIN_COMPUTE_BROKER_TOKEN`.

Token broker đã đổi trong lần phục hồi dữ liệu ổ D. Nếu đã lưu token cũ trên Colab thì **thay Value bằng nội dung tệp hiện tại**, không tạo thêm tên Secret gần giống. Không tự tạo chuỗi bất kỳ: token trên Colab phải khớp broker.

### C. Thêm vào Colab và cấp quyền đúng notebook

1. Đăng nhập đúng tài khoản Google, mở notebook **VieNeu v3** bạn muốn dùng. Không nhầm với notebook `Colin-TTS-Worker-...` dành cho ZeroTTS.
2. Bấm biểu tượng **chìa khóa / Secrets** ở thanh bên trái, rồi **Add new secret**.
3. Điền Name `COLIN_GITHUB_TOKEN`, Value là khóa GitHub từ phần A.
4. Chuyển ra ngoài ô nhập và chờ Colab lưu. Kiểm tra hàng đã mang đúng tên Secret, không còn nhãn `Name of new secret`. Không bấm thêm nhiều lần khi giao diện đang lưu chậm.
5. Thêm hàng thứ hai: Name `COLIN_COMPUTE_BROKER_TOKEN`, Value từ phần B.
6. Bật công tắc **Notebook access** cho **cả hai** trên notebook VieNeu v3 này. Công tắc tắt nghĩa là khóa có tồn tại nhưng notebook không được đọc.
7. Bấm biểu tượng mắt để **ẩn** giá trị trước khi chụp màn hình/chia sẻ. Đóng rồi mở lại Secrets để kiểm tra hai tên vẫn còn và hai công tắc vẫn bật.

Secrets được lưu theo **tài khoản Google**; quyền Notebook access lại cấp cho **từng notebook**. Upload một notebook mới trong cùng tài khoản thường không cần nhập lại hai Value, nhưng phải kiểm tra quyền của notebook mới. Tài khoản Google khác không tự nhận Secrets từ tài khoản này: phải thiết lập riêng.

Chỉ cấp quyền cho notebook bạn tin tưởng. Mã chạy trong notebook được cấp quyền có thể đọc khóa. Không đưa token vào cell code, chat, ảnh chụp, file hướng dẫn hoặc GitHub; không chia sẻ notebook đang chứa token viết thẳng trong code.

## 1. Mở một worker VieNeu trên Colab

1. Trên PC, bấm [Check-Colab.bat](C:/Coder/tts-voice-cloning-OMNI/Check-Colab.bat). Broker phải báo `ok`. Nếu không, bấm [Start-Compute-Broker.bat](C:/Coder/tts-voice-cloning-OMNI/Start-Compute-Broker.bat).
2. Đăng nhập tài khoản Google bạn muốn dùng tại [Google Colab](https://colab.research.google.com/).
3. Nếu đã có notebook trên Drive, mở lại notebook đó. Chỉ khi cài lần đầu/cập nhật notebook mới, chọn **File > Upload notebook** rồi mở tệp đúng tài khoản:

   - [Google AI Pro 1: VieNeu v3](D:/_coder/colin-tts-compute-service/colab/Colin-TTS-VieNeu-v3-google-pro-1.ipynb)
   - [Google AI Pro 2: VieNeu v3](D:/_coder/colin-tts-compute-service/colab/Colin-TTS-VieNeu-v3-google-pro-2.ipynb)
   - [Google AI Pro 3: VieNeu v3](D:/_coder/colin-tts-compute-service/colab/Colin-TTS-VieNeu-v3-google-pro-3.ipynb)

4. Trong **Secrets**, kiểm tra có đúng hai tên `COLIN_GITHUB_TOKEN` và `COLIN_COMPUTE_BROKER_TOKEN`, bật **Notebook access** cho cả hai. Nếu chưa có, làm phần “Thiết lập lần đầu” ở trên.

5. Chọn **Runtime > Change runtime type > GPU**. Cell đầu giữ `COMPUTE_PROVIDER = 'vieneu_v3'`, `VIENEU_DEVICE = 'cuda'`.
6. Chạy lần lượt ba cell code. Lần đầu cần tải môi trường và model. Chờ dòng `COLIN TTS COMPUTE WORKER READY` có `vieneu_v3_turbo:cuda`.
7. Giữ cell cuối đang chạy trong lúc dùng Studio. Dừng runtime khi xong để tránh tiêu tốn tài nguyên không cần thiết.

Nếu muốn chạy CPU trên Colab, đổi `VIENEU_DEVICE = 'cpu'` và chọn runtime không GPU. Worker sẽ công bố `vieneu_v3_turbo:cpu`. Khi chọn CUDA mà Colab chưa cấp GPU, notebook báo lỗi rõ ràng, không âm thầm đổi sang CPU.

Notebook giữ model trong RAM giữa các job; GPU nhận tối đa 4 đoạn mỗi batch từ Studio. Không cần tải model VieNeu hoặc cài CUDA trên PC nếu chỉ dùng chế độ Colab.

### Hiểu ba cell để biết đang chờ gì

- **Cell 1:** đọc hai Secret và chọn cấu hình worker. Chưa tạo audio ở bước này.
- **Cell 2:** tải mã nguồn và chuẩn bị môi trường Python riêng. Lần đầu có thể lâu, không bấm chạy lại liên tục khi đang cài.
- **Cell 3:** khởi động worker, tải model và chờ công việc từ Studio. Khi có dòng `COLIN TTS COMPUTE WORKER READY`, cell cuối **tiếp tục chạy** là bình thường, không phải bị treo.

Mỗi lần Colab cấp runtime mới, cần chạy lại ba cell. Secrets và notebook lưu trên tài khoản vẫn còn, nhưng môi trường/model trong runtime cũ có thể đã mất. Chỉ mở trang notebook mà chưa chạy cell cuối thì Studio chưa có worker để sử dụng.

### Những lần dùng sau: làm ngắn gọn như thế này

1. Bật PC, chạy `Check-Colab.bat` để kiểm tra broker.
2. Mở lại notebook VieNeu v3 đã lưu trên Drive, đúng tài khoản Google.
3. Kiểm tra GPU/CPU rồi chạy ba cell theo thứ tự, chờ worker READY.
4. Mở `run_qt.bat`, chọn VieNeu v3 → Colab từ xa → tài khoản tương ứng → kiểm tra kết nối.
5. Chọn preset hoặc Profile rồi tạo audio. Khi xong, dừng worker và **Runtime > Disconnect and delete runtime** để trả tài nguyên (runtime này là môi trường tạm; notebook trên Drive không bị xóa).

Không cần tạo lại GitHub token hay chép lại khóa broker hằng ngày. Chỉ cập nhật khi khóa hết hạn, bị thu hồi hoặc bạn chủ động đổi khóa. Sau khi đổi Secret, dừng worker cũ và chạy lại các cell để Python đọc giá trị mới; sửa trên thanh Secrets không tự thay biến đã nạp trong runtime.

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
| `SecretNotFoundError` | Kiểm tra đúng tài khoản Google, đúng tên viết hoa; Value không được là tên tệp |
| `NotebookAccessError` hoặc không cho đọc Secret | Bật Notebook access cho hai Secret trên chính notebook đang mở |
| Git clone báo 401/403 hoặc Repository not found | Kiểm tra GitHub token còn hạn, đúng owner, chọn repo private và Contents Read-only; repo private có thể báo không tìm thấy khi thiếu quyền |
| Broker báo HTTP 401/403 | Cập nhật Secret broker từ tệp `broker-token.txt` hiện tại, chạy lại cell đọc Secret và worker; không dùng GitHub token thay cho broker token |
| Khóa có vẻ đúng nhưng vẫn xác thực lỗi | Dán lại Value, bỏ dấu nháy/khoảng trắng/xuống dòng; chạy lại cell đọc Secret |
| Khóa GitHub hết hạn sau 15/11/2026 | Tạo khóa mới cùng phạm vi quyền đọc, cập nhật Value của `COLIN_GITHUB_TOKEN`, chạy lại các cell; không đưa repo sang public để chữa lỗi |
| Clone nghe không đúng | Kiểm tra đúng Profile, cắt mẫu sạch 3..5 giây, tránh nhạc hoặc nhiều người nói |
| Không có worker phù hợp | Mở notebook đúng model hoặc chọn CPU local để làm việc trong lúc chờ |

Broker chạy trên PC, nên khi dùng Colab cần giữ PC bật, có mạng và task broker hoạt động. Tên miền vẫn là `https://tts-compute.tainguyenso.online`; không cần port cố định. Supervisor tự chọn port trống trong dải `18787..18849`.

**Vì sao không cần mở port router?** Worker Colab chủ động kết nối HTTPS ra broker qua tên miền Cloudflare Tunnel. Tunnel nối vào dịch vụ broker trên PC; không phải notebook tự mở một URL TryCloudflare mới mỗi phiên. URL công khai ổn định còn port nội bộ có thể đổi. Token broker vẫn bắt buộc: có tên miền không đồng nghĩa ai cũng được dùng dịch vụ.

Nếu nghi khóa đã lộ, thu hồi khóa GitHub tại trang quản lý token rồi cấp lại với quyền tối thiểu. Nếu lộ khóa broker, cần đổi đồng bộ phía broker, Studio và mọi Colab đang dùng; chỉ xóa Secret trên Colab không thu hồi khóa đang còn hiệu lực phía broker.

## 6. Kiểm chứng và thư mục nguồn

- Studio: `C:\Coder\tts-voice-cloning-OMNI`.
- Compute service private: `D:\_coder\colin-tts-compute-service`.
- Dữ liệu/khóa broker: `C:\Coder\colin-tts-compute-runtime`.
- Script thử audio thật: `scripts/verify_vieneu_compute.py`. Script tạo worker tạm **trên PC**, gửi preset và clone qua broker, không đổi lựa chọn worker đang lưu của bạn.

Chưa có xác nhận chạy thành công trên runtime Google Colab của bạn nếu bạn chưa đăng nhập và chạy notebook. Kiểm thử worker PC qua broker không thay thế bằng chứng GPU/Colab thực tế.

Ngày 16/10/2026 đã thử thật qua broker công khai với worker CPU trên PC: 2 đoạn preset Ngọc Huyền v3, 2 đoạn clone từ audio preset vừa tạo và 1 đoạn clone tái sử dụng cùng mẫu; tất cả WAV mono 48 kHz, dài 2,80..3,60 giây, không rỗng/không im lặng. Bài thử này xác nhận luồng clone và truyền file, không đánh giá độ giống giọng của Profile riêng của bạn. Mẫu và SHA-256 được giữ trong [thư mục kiểm tra](C:/Coder/tts-voice-cloning-OMNI/outputs/vieneu-colab-20261016-pc-check/verification.json).
