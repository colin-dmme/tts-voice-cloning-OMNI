# Colin TTS Local v0.1.0

App TTS local ưu tiên tiếng Việt, có lõi tách khỏi giao diện để sau này đổi Gradio sang CustomTkinter, PyQt6 hoặc giao diện khác mà không phải viết lại logic model.

Tkinter và PySide6 phân biệt rõ **Giọng cố định** và **Clone từ Profile** theo
contract của từng model. Catalog hiện có 33 model Piper tiếng Việt, tải/gỡ từng
package; VIVOS x-low còn cho chọn đủ 65 speaker. VieNeu v3 Turbo cung cấp preset
48 kHz và clone Profile trong hai chế độ tách biệt. Xem
[quản lý giọng cố định](docs/fixed-voice-packages.md).

## Mục tiêu thiết kế

- Model nằm trong thư mục dự án tại `models/`.
- Quản lý môi trường bằng `uv`.
- UI không gọi trực tiếp OmniVoice.
- Core xử lý model, chia câu, chuẩn hóa text, sinh audio và tạo SRT.
- Mỗi file source nên nhỏ, giới hạn kiểm tra là 700 dòng.

## Chạy app

Chạy 1-click cho máy làm việc hoặc máy thuê:

```bat
Start-ColinTTS.bat
```

Đây là file chính cần bấm sau khi clone repo sang máy khác. File này tự chuẩn bị môi trường `uv`, pull source mới nhất nếu có Git, restore `user_state/` vào profile/setting runtime rồi mở giao diện Tkinter.
Sau lần chạy đầu, script cũng tạo shortcut `Colin TTS Local` ngoài Desktop để mở lại nhanh.

Nếu máy thuê chưa có source, chạy bootstrap từ GitHub bằng PowerShell:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://raw.githubusercontent.com/colin-dmme/tts-voice-cloning-OMNI/main/scripts/install_from_github.ps1 | iex"
```

Nếu máy thuê là Docker GPU Linux, mở container template `pytorch`, expose port `7860`, rồi chạy:

```bash
git clone https://github.com/colin-dmme/tts-voice-cloning-OMNI.git
cd tts-voice-cloning-OMNI
bash Start-ColinTTS-Docker-GPU.sh
```

Sau đó mở URL port `7860` do nhà cung cấp cloud hiển thị. Xem thêm `docs/docker_gpu_webui.md`.

Chạy giao diện web Gradio bằng cùng launcher chính:

```bat
Start-ColinTTS.bat -Web
```

Các file `run_app.bat` và `run_tkinter.bat` chỉ giữ lại cho dev/debug. Khi dùng hằng ngày hoặc sang máy mới, ưu tiên `Start-ColinTTS.bat`.

Chạy giao diện Tkinter thủ công trong lúc debug:

```bat
run_tkinter.bat
```

Nếu muốn dừng app đang chạy nền:

```bat
stop_app.bat
```

Hoặc chạy thủ công:

```bat
uv sync
uv run omni-tts-gradio
```

`run_app.bat` dùng `uv sync --inexact` để không gỡ các thư viện TTS optional đã cài trước đó.

## Cài thêm engine TTS

Bản UI và quản lý model chạy với nhóm thư viện nhẹ. Khi muốn dùng model nào, mở tab `Quản lý model`, chọn model đó rồi dùng các nút:

- `Tải model`: tải payload/cache cần cho model.
- `Cài worker/môi trường`: cài worker riêng hoặc thư viện TTS chính.
- `Cài GPU/CUDA`: cài bộ tăng tốc CUDA phù hợp với provider/model.

Các file `install_*.bat` vẫn tồn tại để core chạy đúng tác vụ trên Windows, nhưng không cần bấm trực tiếp khi dùng app. VieNeu, Qwen, Valtec, F5-TTS và Chatterbox chạy trong worker riêng dưới `engines/`, tách khỏi môi trường chính để tránh xung đột dependency với OmniVoice.

### Higgs TTS 3 trên GPU từ xa

Trong giao diện Qt, chọn nhà cung cấp `Higgs Remote GPU` và model
`Higgs TTS 3 · Remote GPU`. Model này không tải payload/worker vào máy hiện tại:

1. Dán URL gốc hoặc URL đầy đủ `/v1/audio/speech` vào `URL endpoint`.
2. Bấm `Kiểm tra kết nối` để kiểm tra `/health` và đọc ID thực từ `/v1/models`.
3. Có thể để `Model API` trống để dùng model server đang serve, hoặc điền đúng ID
   vừa kiểm tra. `voice=default` là lựa chọn thông thường.
4. Chọn `Clone từ Profile` để app gửi audio tham chiếu dưới dạng Data URI kèm
   transcript. Bật streaming PCM để nhận dữ liệu sớm qua proxy.

URL TryCloudflare Quick Tunnel có thể đổi khi tunnel khởi động lại; URL được lưu
trong preferences, không hardcode trong source. Phiên bản hiện tại không gửi
Authorization. Lớp endpoint đã hỗ trợ cấu hình Bearer token qua biến môi trường
để có thể đặt gateway bảo vệ phía trước khi chuyển sang GPU thuê ngoài.

## Giao diện mới Colin TTS Studio (PySide6)

Giao diện studio mới nằm song song trong `src/omni_tts_ui_qt/`, **không dùng chung
code với Tkinter** nên có thể xóa `src/omni_tts_ui_tkinter/` sau này mà không ảnh
hưởng. Chạy bằng file 1-click ở gốc repo:

```bat
run_qt.bat
```

File này tự `uv sync --inexact --extra qt` (cài PySide6) rồi mở `omni-tts-qt`.

Điểm khác so với Tkinter:

- Một cửa sổ studio: rail trái chuyển trang **Studio / Model / Giọng / Bản quyền /
  Liên hệ**; giữa là danh sách giọng + bảng hàng đợi + tab văn bản; phải là panel
  thiết lập gập/mở theo từng model (dựa trên `generation_form_descriptor` và
  `provider_registry`, không hardcode logic vào GUI).
- **Chọn model theo nhà cung cấp**: catalog có hơn 40 model nên cả hai giao diện
  (Qt và Tkinter) đều có combobox `Nhà cung cấp` kèm số lượng
  (`VieNeu (19)`, `Piper ONNX (33)`…) đứng trước combobox `Model TTS`; chọn nhà cung
  cấp trước rồi mới chọn model. Danh sách mở sẵn ở nhà cung cấp của model đang lưu.
  Tab **Quản lý model** dùng đúng cơ chế đó: có bộ lọc `Nhà cung cấp` + ô tìm kiếm,
  bảng luôn **nhóm theo nhà cung cấp** (thứ tự khai báo trong provider registry) rồi
  xếp theo tên, cột Provider hiện nhãn thân thiện (`Piper ONNX` thay cho `piper`).
  Logic nhóm nằm ở `omni_tts_core/ui_presenters/model_groups.py` để hai giao diện
  dùng chung.
- **Tìm kiếm không dấu**: mọi ô tìm kiếm (model, hàng đợi file, danh sách giọng) đi
  qua `omni_tts_core/ui_presenters/search.py`, nên gõ `ngoc` vẫn ra `Piper Ngọc
  Huyền` và `dat` vẫn ra `Đạt Phi`.
- **Chọn nhiều model + nút tự khoá đúng ngữ cảnh**: bảng model cho chọn nhiều dòng
  (Ctrl/Shift click) ở cả hai giao diện. `omni_tts_core/ui_presenters/model_actions.py`
  quyết định nút nào bật/tắt và **chạy trên đúng những model nào**:
  - `Cài GPU/CUDA` tắt với Piper/Valtec vì không có script CUDA (trước đây bấm vào
    là lỗi `ConfigError`).
  - `Gỡ model` bỏ qua model bắt buộc và model chưa tải.
  - `Tải model` chỉ chạy cho các model còn thiếu trong nhóm đang chọn.
  - Tác vụ cấp provider (`Cài worker`, `Cài GPU/CUDA`) chỉ chạy **một lần cho mỗi
    nhà cung cấp** — chọn 33 giọng Piper vẫn chỉ cài worker Piper một lần.
  - `Mở nơi lưu` chỉ bật khi chọn đúng một model.
  Nút bị tắt luôn kèm tooltip nói rõ lý do.
- Thanh phần cứng trên cùng (GPU/VRAM/CPU/RAM) + biểu đồ nhiệt độ có đường cảnh báo
  đứt nét, học theo cách hiển thị của S3Voice, và **theo dõi toàn cục** chứ không gắn
  vào một model.
- **Thông số bám theo model, không có nút "ảo"**: mỗi model khai báo khả năng trong
  `capabilities` của `config/models.yaml`, còn runtime cho biết CUDA có thật hay
  không. `omni_tts_core/ui_presenters/control_policy.py` gộp hai nguồn đó thành một
  policy dùng chung cho cả hai giao diện:
  - Ngôn ngữ chỉ liệt kê thứ model hỗ trợ (Piper chỉ `vi`, Chatterbox chỉ `en`).
  - Thiết bị chỉ hiện những gì chạy được — model không có CUDA thì mất luôn mục
    `GPU CUDA` (trước đây chọn vào sẽ lỗi `ConfigError` lúc chạy).
  - `Tốc độ đọc` / `Pitch shift` bị ẩn hoặc khoá kèm lý do khi model không hỗ trợ,
    và request luôn gửi giá trị trung tính (1.00 / 0.0) thay vì giá trị rác.
  - Thông số riêng của provider gom vào **một** section động
    `Tinh chỉnh riêng · <Provider>`, chỉ hiện đúng những dòng model hỗ trợ (ví dụ
    VieNeu v3 Turbo có temperature/top-k nhưng không có codec và cảm xúc). Tắt
    `ACTIVE` ở section này sẽ gửi mặc định của model thay vì giá trị đang nhập.
    Provider không có thông số riêng (OmniVoice, Piper, Qwen, Valtec) thì section
    biến mất và app nói rõ lý do thay vì để trống.
  - Giá trị đang tinh chỉnh **chỉ bị nạp lại mặc định khi đổi model**; đổi
    `Giọng cố định ↔ Clone từ Profile` không còn xóa seed/temperature đang nhập,
    và các giá trị này được nhớ lại cho lần mở app sau.
  - `Ký tự tối đa mỗi đoạn nhỏ` là **chia ở tầng app, không phải model tự cắt**:
    ưu tiên cắt hết câu → dấu phẩy → theo từ, không bao giờ cắt giữa từ (xem
    `omni_tts_core/text/splitter.py`). Tooltip giải thích ngay trên cả hai giao diện.
- **Bảo vệ GPU toàn cục**: mọi model chạy CUDA đều được chặn/chờ trước khi chạy khi
  GPU nóng hoặc thiếu VRAM (không chỉ Chatterbox). Chatterbox vẫn tự bảo vệ trong
  worker như cũ nên được bỏ qua ở lớp gate ngoài để tránh chờ đôi. Vì ngưỡng dùng
  chung nên **cả hai giao diện đặt phần này thành mục riêng** (Tkinter: tab
  `Bảo vệ GPU`; Qt: section `Bảo vệ GPU (toàn cục)`), không còn nằm trong nhóm
  Chatterbox, và chỉ khoá lại khi model đang chạy CPU. Mỗi model hiển thị một dòng
  cho biết ai đang thực thi bảo vệ.

Toàn bộ logic dùng chung nằm trong core (`omni_tts_core.app_controller`,
`omni_tts_core.ui_presenters`, `omni_tts_core.hardware_monitor`,
`omni_tts_core.safety_coordinator`); GUI chỉ hiển thị.

Hai thứ dưới đây được rút hẳn vào core để hai giao diện không thể lệch nhau:

- `ui_presenters/field_limits.py`: dải min/max/bước nhảy của mọi ô số **đọc trực
  tiếp từ `GenerateSpeechRequest`**. GUI không tự đặt dải nữa, nên không còn nhập
  được giá trị mà core sẽ từ chối lúc chạy (ví dụ Top-K 5000 hay 100 °C).
- `ui_presenters/tooltips.py`: một bộ tooltip tiếng Việt duy nhất cho mọi thiết
  lập, kể cả nhóm Bảo vệ GPU và nhóm Đầu ra. Thiết lập được hỗ trợ có tooltip
  hướng dẫn; thiết lập bị khoá hiện đúng lý do model không dùng được.

Thiết lập được nhớ trong
`config/ui_qt.json` (Tkinter vẫn dùng `config/ui_tkinter.json` riêng). Cả hai giao
diện dùng chung `config/file_queue.sqlite3`, nên **chỉ mở một giao diện tại một thời
điểm** để tránh ghi đè hàng đợi.

## Quy ước model local

Model được khai báo trong `config/models.yaml` và tải về `models/`:

```text
models/
  omnivoice/
    vietnamese/
    base/
  tokenizer/
  asr/
```

App sẽ ưu tiên load model từ đường dẫn local trong dự án.
VieNeu dùng worker riêng và cache Hugging Face chung trong `.hf_cache/`.

## Giao diện Tkinter

Source code nằm riêng trong `src/omni_tts_ui_tkinter/` và chỉ gọi core qua controller. Giao diện này hỗ trợ:

- Tiếng Việt trên toàn bộ UI.
- Tạo audio từ văn bản nhập trực tiếp.
- Kéo thả hoặc chọn nhiều file nguồn `.txt`, `.md`, `.srt`.
- Mặc định xuất WAV/SRT cùng thư mục với file nguồn và dùng tên file nguồn.
- Có thể chọn thư mục xuất riêng.
- Có checkbox `Tách dòng SRT/đoạn văn thành file riêng`, mặc định bật và Tkinter sẽ nhớ trạng thái cho lần mở sau.
- Quản lý profile giọng trong tab `Profile giọng`, lưu theo tên, dự án, transcript và ghi chú.
- Quản lý model và tải các model bắt buộc còn thiếu.

Khi bật chế độ tách file, `.srt` sẽ xuất mỗi cue/dòng subtitle thành một cặp file riêng như `tenfile_001.wav` và `tenfile_001.srt`. Nếu nhập văn bản trực tiếp, mỗi đoạn cách nhau bằng một dòng trống sẽ thành một file audio riêng. `Nghỉ giữa câu/chunk` áp dụng bên trong đoạn dài bị chia nhỏ; `Nghỉ giữa đoạn trong file tổng` áp dụng giữa các đoạn gốc khi xuất một file liền mạch, nối thêm file tổng, hoặc tạo SRT timeline.

Profile giọng được lưu trong `voices/profiles/`, còn file audio mẫu được copy vào `voices/samples/`. Các giao diện chỉ chọn `profile_id`; core sẽ tự lấy file giọng mẫu và transcript khi tạo audio.

Cache Hugging Face cũng được trỏ về `.hf_cache/` khi chạy qua các file `.bat`, để dữ liệu không bị rải sang cache hệ thống.

## Bảo vệ GPU

Bảo vệ GPU áp dụng cho **mọi model chạy CUDA**. App kiểm tra `nvidia-smi` trước mỗi lần tạo và trước mỗi file trong hàng đợi, chỉ bắt đầu sau khi GPU an toàn qua nhiều mẫu liên tiếp. Mặc định app sẽ chờ nếu GPU nóng hơn `75°C`, còn dưới `6000 MB` VRAM trống, GPU đang bận trên `20%`, hoặc NVENC đang dùng trên `5%`. Riêng Chatterbox tự bảo vệ ngay trong worker (chờ trước khi chạy và tạm nghỉ giữa chừng) nên được bỏ qua ở lớp gate ngoài để tránh chờ đôi.

Các ngưỡng nằm ở mục riêng của từng giao diện: Tkinter là tab `Bảo vệ GPU`, Qt là section `Bảo vệ GPU (toàn cục)`. Model đang chạy CPU thì phần này bị khóa kèm lý do. Di chuột lên từng tên/ô nhập để xem tooltip về đơn vị, cách dùng và mức khuyến nghị. Giao diện đọc các mốc target/giảm xung/tự tắt từ `nvidia-smi`; với GTX 1080 Ti, mức max NVIDIA công bố là `91°C`. Mốc `82°C` chỉ bắt đầu đếm và mặc định phải nóng liên tục `10 giây` mới chuyển sang cooldown; nếu nhiệt độ hạ dưới ngưỡng thì bộ đếm được xóa. Khi nhiệt độ, VRAM hoặc NVENC vượt ngưỡng runtime, app suspend worker thật sự và kiểm tra lại theo backoff `10s → 20s → 40s → 80s...`. Nếu GPU phục hồi, worker tự resume; mặc định chỉ báo lỗi sau tổng cộng `300 giây`, và thời gian tối đa này chỉnh được từ giao diện. Mốc nguy cấp mặc định `90°C` cũng chỉnh được, nhưng tăng quá vùng giảm xung/tự tắt của card sẽ khiến bảo vệ không kịp can thiệp. Nếu một tiến trình nhẹ luôn giữ VRAM, có thể hạ `VRAM trống trước khi chạy` từ `6000` xuống `5000 MB`; không nên tắt toàn bộ bảo vệ.

Trong lúc sinh giọng, app tiếp tục theo dõi nhiệt độ, NVENC và VRAM. Tác vụ sẽ dừng ở `82°C`, khi một tiến trình encode khác xuất hiện, hoặc khi VRAM trống xuống dưới `700 MB`. Lỗi CUDA toàn cục như `CUFFT_INTERNAL_ERROR`, mất CUDA driver hoặc `torch.cuda` không khả dụng sẽ dừng cả queue; các file chưa chạy vẫn ở trạng thái chờ.

Các chunk Chatterbox hoàn thành được giữ tại `outputs/checkpoints/chatterbox/` và tự động được dùng lại khi chạy đúng nội dung, profile giọng và thiết lập cũ. Chẩn đoán GPU được ghi theo JSON Lines tại `logs/gpu_safety.jsonl`. Thiết lập thủ công được nhớ trong `config/ui_tkinter.json`; giá trị mặc định kỹ thuật nằm ở phần `runtime` của model Chatterbox trong `config/models.yaml`.

## Đồng bộ máy thuê

Máy chính là nguồn chuẩn cho profile giọng và setting dùng chung. Khi muốn đưa state hiện tại lên GitHub:

```bat
Sync-State-To-Git.bat
```

Script này export `voices/profiles`, `voices/samples` và các setting UI portable vào `user_state/`, commit riêng phần state đó rồi push lên branch hiện tại. Trên máy thuê mới, `Start-ColinTTS.bat` sẽ restore `user_state/` trước khi mở app. Model, cache tải model, output và license vẫn không đưa vào Git.

Nếu dùng GTX 1080 Ti, chạy:

```bat
install_tts_deps_cuda126.bat
```

Thông thường bạn có thể bấm `Cài GPU/CUDA` trong tab `Quản lý model`. Lệnh thủ công này chỉ còn dùng khi debug hoặc cần cài trực tiếp ngoài app; nó cài nhóm TTS rồi ép cài lại `torch==2.7.1+cu126` và `torchaudio==2.7.1+cu126`, phù hợp hơn với GTX 1080 Ti.

Nếu dùng RTX 50xx/5090 Blackwell và gặp lỗi `CUDA capability sm_120` hoặc `no kernel image is available`, chạy:

```bat
Fix-RTX50-CUDA.bat
```

Với source checkout có thể cài riêng Qwen worker Blackwell bằng:

```bat
install_qwen_worker_blackwell.bat
```
