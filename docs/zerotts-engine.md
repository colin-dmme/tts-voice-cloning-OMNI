# ZeroTTS 202M Official

Tài liệu này ghi lại kết quả nghiên cứu source ZeroTTS và hợp đồng tích hợp
thực tế trong Colin TTS Studio. Mốc source được kiểm tra là package
`zerotts==0.1.2`, Git commit
`9d85578bee9321d6ef8305a4d454baf33e3fe861` và snapshot model Hugging Face
`8a0c3c29f6f047011f5cae02d0b14475a690be86`.

Nguồn chính thức:

- [GitHub zeroweight-ai/ZeroTTS](https://github.com/zeroweight-ai/ZeroTTS)
- [Model zeroweight-ai/ZeroTTS](https://huggingface.co/zeroweight-ai/ZeroTTS)
- [Model zeroweight-ai/ZeroTTS-GGUF](https://huggingface.co/zeroweight-ai/ZeroTTS-GGUF)
- [ZeroBench-TTS](https://huggingface.co/datasets/zeroweight-ai/ZeroBench-TTS)
- [Package zerotts trên PyPI](https://pypi.org/project/zerotts/)
- [Chi tiết benchmark](https://github.com/zeroweight-ai/ZeroTTS/blob/main/docs/BENCHMARKS.md)
- [Danh sách voice pack](https://github.com/zeroweight-ai/ZeroTTS/blob/main/docs/VOICES.md)

## Kết luận kỹ thuật

- Model có 202 triệu tham số, dùng graph ONNX FP32 và codec MOSS, xuất mono
  48 kHz. Payload tải thực tế trong app là 865,92 MB.
- Upstream định vị đây là model tiếng Việt có khả năng đọc English code-switch,
  không công bố chất lượng tiếng Anh độc lập. Catalog vì vậy chỉ cho chọn ngôn
  ngữ `vi`; nội dung tiếng Anh vẫn có thể nằm trong câu tiếng Việt.
- Runtime sinh giọng chỉ cần CPU, không kéo PyTorch. Worker được cô lập tại
  `engines/zerotts_worker` để không làm thay đổi dependency của app chính.
- Source có đường streaming thật qua `synthesize_stream()`. Decoder có thể trả
  chunk đầu từ một frame rồi tăng dần đến trần frame đã cấu hình.
- Text dài cần được chuẩn hóa, chia theo thời lượng ước lượng và dọn dấu câu
  trước khi gọi model. Logic này thuộc worker ZeroTTS, không dùng splitter ký
  tự chung của Core.
- Package có tám voice latent chính thức và một chế độ không điều kiện.
- Bản mã nguồn mở không có voice encoder. Nó chỉ nạp latent `.npz` có sẵn,
  vì vậy không thể clone từ WAV hay Profile giọng. Không có flag ẩn hoặc extra
  dependency nào mở được chức năng này.
- Tổ chức ZeroWeight hiện phát hành hai repo model, gồm bản ONNX và bản GGUF của
  cùng ZeroTTS 202M. Catalog tích hợp cả ba file GGUF chính thức: F32, Q8_0 và
  Q4_0, không mô tả chúng như ba model được huấn luyện độc lập.

## Ba biến thể GGUF

Snapshot `zeroweight-ai/ZeroTTS-GGUF` được ghim revision
`92ca8651645d4733df56620b3aadc768a76f7c46`.

| Model ID trong app | File chính thức | Kích thước file | Mục đích so sánh |
|---|---|---:|---|
| `zerotts_202m_gguf_f32` | `zerotts-f32.gguf` | 809.299.360 byte | Mốc F32, cùng frame code với ONNX khi dùng cùng random draw |
| `zerotts_202m_gguf_q8_0` | `zerotts-q8_0.gguf` | 215.556.512 byte | Bản nén vừa, upstream đo 4,9% code drift |
| `zerotts_202m_gguf_q4_0` | `zerotts-q4_0.gguf` | 130.228.640 byte | Bản nhỏ nhất, upstream đo 36,5% code drift |

Runtime C++ upstream chỉ sinh frame codebook. Nó không chứa codec hoặc voice
encoder. Tích hợp hoàn chỉnh vì `zerotts_gguf_worker` giữ model ggml resident,
gửi text token và voice latent vào runtime native, nhận frame `(T, 16)`, rồi
giải mã bằng MOSS codec ONNX đi kèm snapshot để tạo WAV mono 48 kHz.

GGUF upstream chưa hỗ trợ CFG. Ba model GGUF vì vậy công bố 20 setting và loại
`cfg_scale`, `warmup` khỏi form Qt, Tkinter và hợp đồng MCP. Core cũng từ chối
hai key này nếu client tự gửi, thay vì âm thầm bỏ qua. `intra_op_num_threads`
được dùng làm số luồng ggml ở GGUF và số luồng ONNX model ở bản ONNX.

## Kiến trúc model đã kiểm tra

```text
text
  -> tokenizer và text_encoder.onnx
  -> prefix_step.onnx, global autoregressive transformer
  -> local_frame_decode.onnx, sinh audio token theo frame
  -> MOSS codec decoder ONNX
  -> PCM mono 48 kHz
```

Voice pack là tensor float32 dạng `(1, 10, 768)`, khoảng 30 KB. Nó được chèn
vào prefix của chuỗi. Khi không có voice pack, model dùng
`null_voice_emb.npy`; danh tính giọng khi đó không ổn định giữa các lần sinh.

## Kiến trúc tích hợp trong Colin TTS Studio

```text
Qt, Tkinter hoặc MCP
  -> AppController
  -> TtsService và validation chung
  -> PresetOnnxSubprocessEngine
  -> zerotts_worker hoặc zerotts_gguf_worker, JSON Lines
  -> ONNX model hoặc ggml/GGUF sinh frame
  -> MOSS codec ONNX giải mã PCM 48 kHz
```

Nguồn khai báo nằm trong `config/models.yaml`. `provider_registry.py` cung cấp
metadata cho Core, Qt, Tkinter và MCP cùng lúc. Không có nhánh ZeroTTS riêng
trong GUI. `get_generation_contract` trả cả `provider_settings`, nên agent đọc
được đúng kiểu, khoảng giá trị, mặc định, lựa chọn và tooltip trước khi tạo job.

Provider dùng `automatic_chunk_join: native` và
`native_text_preprocessing: true`. Core giữ nguyên văn bản đầu vào để tùy chọn
`normalize_vi_text` có ý nghĩa thật; worker mới thực hiện chuẩn hóa và chia đoạn.
Output, SRT, hàng đợi, hủy job, lịch sử, quy tắc phát âm và khóa liên tiến trình
tiếp tục dùng pipeline chung của ứng dụng.

## Voice có sẵn

| ID | Nhãn trong ứng dụng |
|---|---|
| `maichi` | Mai Chi, nữ trẻ, kể chuyện nhẹ nhàng |
| `baotrang` | Bảo Trang, nữ trưởng thành, tin tức rõ ràng |
| `kimoanh` | Kim Oanh, nữ trung niên, kể chuyện ấm áp |
| `hamy` | Hà My, nữ trẻ, hoạt hình biểu cảm |
| `giahuy` | Gia Huy, nam trẻ, kể chuyện trầm ấm |
| `huuduc` | Hữu Đức, nam lớn tuổi, điềm đạm |
| `quangminh` | Quang Minh, nam trẻ, tin tức dứt khoát |
| `tiendat` | Tiến Đạt, nam trẻ, bình luận năng lượng cao |
| `__unconditioned__` | Không điều kiện, danh tính không ổn định |

`maichi` là mặc định. Profile clone và Voice Design bị tắt theo capability thật
của bản phát hành. Nếu có latent hợp lệ từ dịch vụ ngoài, package upstream có
thể nạp từ `voices/<id>/voice.npz`, nhưng catalog hiện không tự tạo latent từ
audio và không quảng bá đó là clone local.

## Toàn bộ thiết lập provider

| Key | Mặc định | Phạm vi hoặc lựa chọn | Ý nghĩa |
|---|---:|---|---|
| `normalize_vi_text` | `true` | bật, tắt | Đọc số, ngày, giờ và viết tắt thành tiếng Việt |
| `normalize_punctuation` | `true` | bật, tắt | Chuẩn hóa dấu câu trước khi chia đoạn |
| `clean_segment_punctuation` | `true` | bật, tắt | Dọn dấu câu ở ranh giới đoạn |
| `max_chunk_sec` | `15` | 5 đến 25 giây | Mục tiêu tối đa của đoạn nội bộ |
| `segment_gap_seconds` | `0.08` | 0 đến 2 giây | Khoảng lặng giữa đoạn nội bộ |
| `cfg_scale` | `1.0` | 1 đến 4 | Tăng bám danh tính voice; lớn hơn 1 làm tăng chi phí mỗi frame |
| `text_temperature` | `1.0` | 0,01 đến 4 | Độ ngẫu nhiên token văn bản nội bộ |
| `text_topk` | `50` | 1 đến 8192 | Giới hạn ứng viên token văn bản |
| `audio_temperature` | `0.8` | 0,1 đến 1,5 | Độ ngẫu nhiên audio token |
| `audio_topk` | `25` | 1 đến 200 | Giới hạn ứng viên audio token |
| `audio_topp` | `0.95` | 0,1 đến 1 | Nucleus sampling cho audio token |
| `audio_repetition_penalty` | `1.2` | 1 đến 2 | Hạn chế lặp và dead air |
| `min_frames` | `4` | 0 đến 1500 | Số frame tối thiểu trước khi được dừng |
| `max_frames` | `1500` | 1 đến 1500 | Trần frame cho mỗi đoạn |
| `eoa_extra_frames` | `1` | 0 đến 4 | Giữ thêm đuôi sau tín hiệu kết thúc |
| `seed` | `-1` | -1 hoặc số nguyên không âm | -1 là ngẫu nhiên, số không âm để tái lập |
| `streaming_decoder` | `true` | bật, tắt | Dùng đường decoder streaming thật |
| `first_chunk_frames` | `1` | 1 đến 64 | Số frame của chunk đầu |
| `max_chunk_frames` | `16` | 1 đến 64 | Trần frame của chunk streaming tiếp theo |
| `intra_op_num_threads` | `4` | 1 đến 64 | Luồng ONNX Runtime hoặc ggml cho model đang chọn |
| `codec_intra_op_num_threads` | `0` | 0 đến 64 | Luồng codec; 0 dùng mặc định của runtime |
| `warmup` | `true` | bật, tắt | Chạy warmup khi nạp model |

Validation Core chặn giá trị ngoài phạm vi. Worker còn kiểm tra quan hệ
`min_frames <= max_frames` và `first_chunk_frames <= max_chunk_frames`.
Chế độ không điều kiện luôn ép `cfg_scale=1.0`, đúng giới hạn của source model.

Hai đối số API không được biến thành control âm thanh: `providers` là lựa chọn
backend khởi tạo và hiện được khóa rõ ở `CPUExecutionProvider`; `timing` là dict
nhận số đo chẩn đoán từ `synthesize()`, không thay đổi kết quả sinh. Voice object
hoặc latent array cũng là dạng dữ liệu đầu vào, không phải setting. Như vậy 22
control ở trên bao phủ toàn bộ tùy chọn có thể cấu hình cho preprocessing,
sampling, độ dài, streaming và runtime CPU của tích hợp này.

## Benchmark và cách đọc đúng số liệu

Các con số sau là kết quả do tác giả ZeroTTS công bố trên ZeroBench-TTS, không
phải phép đo độc lập của dự án này:

- Raw text: WER 1,03%, UTMOS 2,91, SSIM 0,936, excess silence 0,029 giây.
- CPU: RTF trung bình khoảng 0,50 và time to first audio khoảng 70 ms.
- Bài speed test dùng một request, 8 inference thread, ba độ dài văn bản, chạy
  sáu lần và bỏ hai lần cold-cache đầu.
- ZeroBench-TTS có 137 mục, 59 reference voice và bốn tập con. Scorer lấy WER
  tốt nhất giữa Whisper Large v3 và PhoWhisper Large qua các cách đọc hợp lệ.

Không nên diễn giải SSIM là ZeroTTS thắng tuyệt đối: chính bảng công bố cho
thấy OmniVoice nhỉnh hơn về similarity. TTFA cũng không hoàn toàn đối xứng vì
ba baseline trong môi trường benchmark không có đường streaming CPU hoạt động.

Giấy phép code và weights là MIT. Codec MOSS đi kèm là Apache-2.0.
ZeroBench-TTS là CC-BY-NC-4.0, nên không lấy giấy phép dataset áp sang model.

## Xác minh thực tế trong ứng dụng

Ngày 2026-09-13, luồng MCP stdio thật đã chạy trên máy phát triển với
`maichi`, seed `20260913`, bốn ONNX thread và streaming decoder:

- Model do `ModelStorage` tải thành công: 865,92 MB, đúng revision đã pin.
- MCP công bố đủ 22 setting trong `get_generation_contract`.
- Job nền kết thúc `succeeded`, sinh WAV và SRT qua AppController, Core và worker.
- WAV mono 48 kHz, 307.200 frame, dài 6,4 giây, peak 0,60446, RMS 0,12435,
  không có NaN hoặc infinity.
- SRT giữ đúng văn bản đầu vào và timeline 00:00:00,000 đến 00:00:06,400.
- Job đối chứng dùng `streaming_decoder=false`, `normalize_vi_text=false`,
  voice không điều kiện và câu tiếng Việt code-switch cũng `succeeded`. WAV
  mono 48 kHz dài 3,68 giây, peak 0,91953, RMS 0,09403 và toàn bộ mẫu hữu hạn.
- Desktop Coworker Control Center đã forced-test lại upstream
  `colin-studio-tts` sau thay đổi source. Read-back báo `connected`, health
  `connected`, 10/10 tool callable, chế độ exposure `direct` và danh sách proxy
  có đủ `tts__get_generation_contract` cùng hai tool tạo job.

Đây là smoke test tích hợp và tín hiệu audio, chưa phải benchmark chất lượng
137 mục hay phép đo TTFA tương đương phương pháp của tác giả.

Phép đo riêng với model đã resident trên Intel Core i9-10900, 10 core và 20
logical processor, cùng một câu tiếng Việt độ dài vừa phải cho kết quả:

| Cấu hình | TTFA ba lần | RTF ba lần | Nạp model và warmup |
|---|---|---|---:|
| 4 thread | 200,0 / 161,7 / 175,4 ms | 1,600 / 1,450 / 1,605 | 9,38 giây |
| 8 thread | 246,8 / 186,6 / 227,9 ms | 1,713 / 1,534 / 1,540 | 10,12 giây |

Như vậy máy này chưa tái lập được claim TTFA khoảng 70 ms hoặc RTF 0,50.
Tăng từ bốn lên tám thread cũng không cải thiện workload thử nghiệm này. Đây
chỉ là ba lần chạy trên một câu và không dùng pinning core pool như benchmark
của tác giả, nhưng đủ để không gắn nhãn tốc độ marketing như kết quả đã xác
minh cục bộ. Catalog vì thế để `speed_score: 3` và trạng thái `risk: test`.

Ngày 2026-09-13, ba snapshot GGUF đã được tải và chạy WAV thật trên cùng máy:

| Biến thể | Payload app đo được | Thời gian cold smoke test | WAV |
|---|---:|---:|---|
| F32 | 819,33 MB | 10,01 giây | mono 48 kHz, hữu hạn |
| Q8_0 | 253,10 MB | 5,42 giây | mono 48 kHz, hữu hạn |
| Q4_0 | 171,72 MB | 3,21 giây | mono 48 kHz, hữu hạn |

Đây là smoke test một câu với tám thread, gồm nạp model, sinh frame và decode
codec. Nó xác nhận đường chạy nhưng chưa phải benchmark lặp có warm cache.
Ngoài worker trực tiếp, một job Core với Q8_0 và một job MCP nền với Q4_0 đều
hoàn tất thành công. MCP `list_models(provider_id="zerotts")` trả bốn model;
bản ONNX có 22 setting, mỗi bản GGUF có 20 setting và không có CFG hoặc warmup.

## Cài và sử dụng

Trong trang Quản lý model, chọn provider `ZeroTTS`, sau đó:

1. Bấm `Cài worker/môi trường`.
2. Bấm `Tải model`.
3. Chọn ONNX, GGUF F32, GGUF Q8_0 hoặc GGUF Q4_0 trong Studio.
4. Chọn voice pack và chỉnh section `Tinh chỉnh riêng` nếu cần.

Cài worker thủ công trên Windows:

```powershell
.\install_zerotts_worker.bat
.\install_zerotts_gguf_worker.bat
```

Request MCP tối thiểu:

```json
{
  "request": {
    "text": "Xin chào từ ZeroTTS.",
    "model_id": "zerotts_202m_gguf_q8_0",
    "voice": {"mode": "fixed", "voice_id": "maichi"},
    "generation": {
      "language": "vi",
      "runtime_target": "cpu",
      "provider_options": {
        "normalize_vi_text": true,
        "audio_temperature": 0.8,
        "audio_topk": 25,
        "audio_topp": 0.95,
        "audio_repetition_penalty": 1.2,
        "streaming_decoder": true
      }
    }
  }
}
```
