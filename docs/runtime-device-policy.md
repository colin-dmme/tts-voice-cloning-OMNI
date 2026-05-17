# Runtime Device Policy cho app đa engine

Cập nhật: 2026-05-16

## Mục tiêu

App phải tách rõ hai khái niệm:

- Model là danh tính model, ví dụ `VieNeu Ngọc Huyền 0.3B PyTorch`, `OmniVoice Vietnamese`, `Qwen3 TTS 0.6B`.
- Thiết bị xử lý là lựa chọn runtime: `Auto`, `CPU`, hoặc `GPU CUDA`.

Không nên nhân đôi model chỉ vì khác thiết bị chạy. Các dòng `_cuda` cũ được giữ để tương thích, nhưng chuyển sang nhóm debug/legacy và không nên dùng làm hướng production mới.

## Phase triển khai

| Phase | Nội dung | Trạng thái |
|---|---|---|
| 0 | Rà cấu trúc provider/model/runtime hiện tại | Đã xong |
| 1 | Thêm detector/policy chung cho runtime device | Đã xong |
| 2 | Thêm lựa chọn `Thiết bị xử lý` vào request/UI/preferences | Đã xong |
| 3 | Nối policy vào OmniVoice, VieNeu, Qwen, Valtec | Đã xong |
| 4 | Chuyển các dòng CUDA cũ sang legacy/debug và cập nhật docs | Đã xong |
| 5 | Smoke test trên CPU hiện tại, test CUDA khi có worker GPU | Đã xong trên máy test |

## Quy ước UI

Dropdown model chỉ nên giúp user chọn model.

Tùy chọn thiết bị nằm ở tab Nâng cao:

- `Auto (khuyến nghị)`: giữ hành vi an toàn hiện tại. Engine tự chọn nếu runtime đã sẵn sàng.
- `CPU`: ép chạy CPU, hữu ích khi GPU thiếu VRAM hoặc muốn tránh lỗi CUDA.
- `GPU CUDA`: ép CUDA. Nếu runtime CUDA chưa sẵn sàng, app phải báo lỗi rõ và gợi ý script cài phù hợp.

## Chính sách theo engine

| Engine | Auto | CPU | GPU CUDA |
|---|---|---|---|
| OmniVoice | Dùng CUDA nếu PyTorch CUDA khả dụng, ngược lại CPU | Ép `device_map=cpu` | Ép `device_map=cuda:0`, báo lỗi nếu thiếu CUDA |
| VieNeu Standard/PyTorch | Dùng CUDA nếu worker đủ CUDA; nếu không giữ CPU/runtime hiện tại | Ép `backbone_device`, `codec_device`, `pytorch_device` sang CPU | Ép sang CUDA; GGUF cần llama.cpp GPU offload |
| VieNeu Turbo | Dùng CUDA nếu worker có `onnxruntime-gpu`; nếu không giữ CPU/runtime hiện tại | Ép `device=cpu` | Ép `device=cuda`; cần `onnxruntime-gpu` |
| Qwen3 TTS | Worker tự dùng CUDA nếu PyTorch CUDA khả dụng | Gửi `device_map=cpu` | Gửi `device_map=cuda:0`, báo lỗi nếu thiếu CUDA |
| Valtec | Mặc định CPU | Gửi `device=cpu` | Gửi `device=cuda`, chỉ dùng khi worker có PyTorch CUDA |

## Điểm code chính

- `src/omni_tts_shared/schemas.py`: `GenerateSpeechRequest.runtime_target`.
- `src/omni_tts_core/runtime_devices.py`: detector và policy chung.
- `src/omni_tts_core/worker_installation.py`: chọn script cài GPU theo provider.
- `src/omni_tts_core/engines/*_engine.py`: áp dụng policy vào payload hoặc loader.
- `src/omni_tts_ui_tkinter/*`: lưu và hiển thị lựa chọn runtime target.
- `src/omni_tts_ui_gradio/*`: thêm dropdown runtime target.
- `config/models.yaml`: các dòng VieNeu `_cuda` là legacy shortcut, không phải hướng thêm model mới.
- `runtime_wheels/windows/cp312/cuda/`: wheel nội bộ cho backend cần build native, hiện có `llama-cpp-python` CUDA cho VieNeu GGUF.

## Quy tắc thêm model mới

Khi thêm model mới:

- Không tạo thêm bản `*_cuda` nếu chỉ khác thiết bị chạy.
- Điền `catalog_info.origin` để biết official/community.
- Dùng `catalog_info.category` cho nhóm vận hành như `community`, `experimental`, `support`.
- Ghi `recommend_for` theo trường hợp sử dụng, không dùng category để nói CPU/GPU.
- Nếu model cần GPU mạnh, ghi vào `recommend_for` hoặc `notes`, còn việc chọn GPU để runtime policy xử lý.

## Việc còn nên làm dài hạn

- Thêm nút kiểm tra GPU riêng trong tab Quản lý model.
- Bổ sung thêm script GPU riêng cho Valtec nếu quyết định hỗ trợ GPU Valtec production.
- Lưu log effective device sau khi worker thực sự load model.
- Bổ sung test CUDA trên máy có GPU worker thật cho VieNeu Standard, Turbo, PyTorch Full, Qwen, Valtec.

## Smoke test 2026-05-15

- Valtec CPU preset `NF`: tạo WAV thành công, 1 đoạn, khoảng 3.37 giây.
- VieNeu Turbo CPU preset mặc định: tạo WAV thành công, 1 đoạn, khoảng 3.24 giây.
- VieNeu Turbo legacy CUDA khi worker CUDA chưa cài: app báo `CUDA chưa khả dụng cho vieneu`, không để lỗi rơi xuống worker.
- Sau khi cài CUDA worker: VieNeu Turbo `Auto` và `GPU CUDA` tạo WAV thành công trên GTX 1080 Ti.
- Tại thời điểm 2026-05-15, VieNeu Standard/GGUF CUDA vẫn thiếu `llama-cpp-python` có GPU offload, nên tạm dùng CPU cho GGUF.
- VieNeu Turbo với câu có từ tiếng Anh `Auto` tạo audio dài bất thường cả ở `Auto` lẫn `CPU`; đây là hành vi model/text riêng, không phải lỗi selector thiết bị.

## Smoke test 2026-05-16

- Đã cài Visual Studio Build Tools 2022 tại `D:\Microsoft-Visual-Studio\2022\BuildTools` và build được `llama-cpp-python==0.3.16` với `GGML_CUDA=ON`, `CMAKE_CUDA_ARCHITECTURES=61` cho GTX 1080 Ti.
- Wheel CUDA nội bộ: `runtime_wheels/windows/cp312/cuda/llama_cpp_python-0.3.16-cp312-cp312-win_amd64.whl`, SHA256 `1191E0DD8DE468D1628BBB29270706D04DACB8CF9A6AA54A7E65840B23AEBE38`.
- `install_vieneu_worker_cuda.bat` đã ưu tiên cài wheel nội bộ này, rồi re-apply PyTorch `cu118` để tránh dependency kéo worker về CPU.
- Probe worker sau cài: `torch.cuda.is_available() == True`, `llama_cpp.llama_supports_gpu_offload() == True`.
- `VieNeu TTS v2 Standard (CUDA)` tạo WAV thành công: `outputs/jobs/20260516_065613_815765ff/output.wav`, 1 đoạn, khoảng 4.5 giây.
- Khi truyền trực tiếp Profile giọng/ref audio vào `VieNeu TTS v2 Standard (CUDA)`, worker từng crash native `0xC0000005` sau warning PyTorch. Đã đổi sang luồng an toàn hơn: encode audio mẫu trong process riêng thành `ref_codes.npy`, cache theo profile/sample/model, rồi Standard/GGUF generate bằng `ref_codes + ref_text`.
- Smoke test sau chỉnh: `VieNeu TTS v2 Standard (CUDA)` + profile `ngoc-huyen-10s` + Distill tạo WAV thành công tại `outputs/jobs/20260516_143613_5c9100d9/output.wav`; chạy lại dùng cache tại `outputs/jobs/20260516_143710_17f2dbd3/output.wav`.
- Smoke test sau chỉnh: `VieNeu TTS v2 Standard (CUDA)` + profile `ngoc-huyen-10s` + codec ONNX mặc định vẫn tạo WAV thành công tại `outputs/jobs/20260516_144007_80dc4351/output.wav`; app tự dùng Distill để encode profile ở bước nền rồi dùng ONNX để decode.
- Smoke test sau chỉnh: `VieNeu TTS v2 Standard (CUDA)` + file audio mẫu thủ công + codec ONNX mặc định tạo WAV thành công tại `outputs/jobs/20260516_144507_0899df5e/output.wav`; app pre-encode vào thư mục tạm của job.
- Smoke test sau chỉnh: `VieNeu TTS 0.3B Q8 GGUF` + profile `ngoc-huyen-10s` + codec ONNX mặc định tạo WAV thành công tại `outputs/jobs/20260516_144034_1dfaa354/output.wav`.
