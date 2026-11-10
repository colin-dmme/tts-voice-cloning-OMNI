# ZeroTTS trên máy CPU khác: runtime và đóng gói

Ngày kiểm tra: 09/11/2026. Chỉ nghiên cứu source và tài liệu; chưa cài hay chạy inference trên máy đích.

## 1. Chốt đúng biến thể cho lượt thử đầu

Worker remote hiện chỉ nhận `zerotts_202m_official`, qua `ZeroTtsResidentHandler` và ONNX `CPUExecutionProvider`. Studio local còn có GGUF F32/Q8_0/Q4_0 nhưng các biến thể đó chưa được worker remote công bố hay thực thi. Lượt thử ít thay đổi nhất dùng **ZeroTTS 202M Official ONNX**. Nếu người dùng muốn giữ GGUF F32 đang dùng local, cần bổ sung adapter riêng trước khi gọi đó là cùng một cấu hình.

Nguồn: [worker.py](D:/_coder/colin-tts-compute-service/src/colin_compute_service/worker.py:112), [models.yaml](C:/Coder/tts-voice-cloning-OMNI/config/models.yaml:1695), [ZeroTTS worker](C:/Coder/tts-voice-cloning-OMNI/engines/zerotts_worker/synthesize.py:26).

## 2. Không cần mang cả ứng dụng Studio sang máy phụ

Gói tối thiểu gồm source `colin_compute_service`, manifest và lockfile của service; `engines/zerotts_worker/{synthesize.py,pyproject.toml,uv.lock}`; Python/uv dành riêng cho máy đó; snapshot model; cấu hình worker và thư mục dữ liệu. Service hiện kéo FastAPI/Pydantic/Uvicorn nhưng không cần Qt. ZeroTTS dùng `zerotts==0.1.2`, NumPy, SoundFile và các phụ thuộc đã khóa. Đường inference không cần PyTorch hay GPU. Dùng lại cơ chế ZIP source có manifest revision/SHA-256 hiện có, tránh sao chép cả repo, profile hay dữ liệu tài khoản Studio.

Nguồn: [service manifest](D:/_coder/colin-tts-compute-service/pyproject.toml), [engine manifest](C:/Coder/tts-voice-cloning-OMNI/engines/zerotts_worker/pyproject.toml), [package allowlist](D:/_coder/colin-tts-compute-service/src/colin_compute_service/worker_package.py:14), [ZeroTTS 0.1.2 trên PyPI](https://pypi.org/project/zerotts/0.1.2/).

## 3. Model phải là snapshot đầy đủ, tải một lần rồi giữ tại máy phụ

Ghim `zeroweight-ai/ZeroTTS` tại revision `8a0c3c29f6f047011f5cae02d0b14475a690be86`, giống cấu hình Studio và bootstrap hiện có. Cần `config.json`, tokenizer, `null_voice_emb.npy`, `silence_frame.npy`, các graph `onnx/*`, codec `onnx/codec/*` gồm tệp trọng số ngoài `.data`, `voices/index.json` và voice latent `.npz`. Không chỉ chép một tệp ONNX. Tám voice pack dựng sẵn được hỗ trợ; bản này không tạo latent từ audio để clone giọng. ZIP source hiện không chứa trọng số, nên bộ cài cần bước tải/kiểm tra model riêng và ghi revision/hash vào trạng thái cài đặt.

Nguồn: [required_files](C:/Coder/tts-voice-cloning-OMNI/config/models.yaml:1732), [bootstrap](D:/_coder/colin-tts-compute-service/colab/bootstrap_colab.py:13), [model card chính thức](https://huggingface.co/zeroweight-ai/ZeroTTS).

## 4. Portable về kiến trúc, nhưng bootstrap Colab chưa phải bộ cài Windows

Khuyến nghị chuẩn hóa lượt thử ở Python **3.12 x64**, dùng manifest/lockfile hiện tại. Hai manifest chấp nhận Python 3.10–3.13, nhưng không cần mở rộng ma trận pilot. Lockfile có wheel CPython 3.12 Windows amd64 và Linux x86_64; ONNX Runtime 1.30.0 cho Python này dùng wheel manylinux_2_28. Cần kiểm tra phiên bản OS/glibc thật trước triển khai Linux. Không chép `.venv` từ Windows sang Linux. Bootstrap Colab dùng `/content` và `.venv/bin/python`; launcher Windows phải chọn `.venv/Scripts/python.exe` và thư mục cài riêng.

Nguồn: [engine lock](C:/Coder/tts-voice-cloning-OMNI/engines/zerotts_worker/uv.lock), [bootstrap](D:/_coder/colin-tts-compute-service/colab/bootstrap_colab.py:65), [Windows installer hiện có](C:/Coder/tts-voice-cloning-OMNI/install_zerotts_worker.bat), [Linux installer hiện có](C:/Coder/tts-voice-cloning-OMNI/scripts/install_zerotts_worker_linux.sh).

## 5. Bổ sung bước nạp thử trước khi công bố sẵn sàng

`worker.main()` hiện chỉ kiểm tra script và thư mục model của ZeroTTS; đăng ký worker trước khi `ZeroTtsResidentHandler` gọi model lần đầu. `_MODEL` chỉ được nạp trong `_synthesize`. Vì vậy trạng thái READY chưa chứng minh model/voice/codec đã hoạt động. Nên thêm probe startup: kiểm tra toàn bộ asset, nạp model, tạo một câu ngắn với preset có thật, xác minh WAV PCM 16-bit 48 kHz không rỗng rồi mới công bố ready. Màn hình máy chính cần phân biệt đang cài, đang nạp, sẵn sàng và lỗi.

Nguồn: [worker main](D:/_coder/colin-tts-compute-service/src/colin_compute_service/worker.py:390), [lazy load](C:/Coder/tts-voice-cloning-OMNI/engines/zerotts_worker/synthesize.py:124).

## 6. Giữ một model, một job, đo trên CPU thật trước khi tăng tải

Worker hiện `max_concurrency=1`; giữ mặc định này cho pilot. Model threads mặc định 4; codec threads 0 được chuyển thành `None` cho SDK. Do đó không nên quảng bá cấu hình hiện tại là giới hạn toàn bộ tiến trình ở đúng bốn luồng hay một tỷ lệ CPU cố định. Đo thử model threads 2/4/8 phù hợp số lõi, thêm codec threads rõ ràng, ưu tiên để máy phụ vẫn dùng được. Giữ cấu hình khởi tạo ổn định: thay model path, threads hoặc warmup làm `_MODEL_KEY` đổi và nạp lại model. Ghi thời gian nạp lần đầu, thời gian tạo lần sau, RAM đỉnh và RTF = thời gian tạo / thời lượng audio; không hứa realtime từ benchmark máy khác. ONNX Runtime xác nhận cấu hình luồng và spinning có thể đánh đổi độ trễ với mức dùng CPU/điện.

Nguồn: [model settings](C:/Coder/tts-voice-cloning-OMNI/engines/zerotts_worker/synthesize.py:15), [capabilities](D:/_coder/colin-tts-compute-service/src/colin_compute_service/worker.py:357), [ONNX Runtime thread management](https://onnxruntime.ai/docs/performance/tune-performance/threading.html).

## 7. Dùng helper resident đã có cho chờ kết quả và log

ZeroTTS handler hiện đọc `stdout.readline()` trực tiếp và để `stderr=PIPE` mà không có luồng hút log thường xuyên. Một SDK lỗi/treo hoặc ghi log nhiều có thể làm việc chờ kết quả khó quản lý. Service đã có `ResidentJsonWorker` với timeout, hàng đợi phản hồi và log có giới hạn cho VieNeu. Nên tái sử dụng helper này cho ZeroTTS trong phần gia cố worker PC, giữ thao tác hủy chỉ đóng tiến trình do worker sở hữu.

Nguồn: [ZeroTtsResidentHandler](D:/_coder/colin-tts-compute-service/src/colin_compute_service/worker.py:137), [ResidentJsonWorker](D:/_coder/colin-tts-compute-service/src/colin_compute_service/resident.py:15).

## 8. Tiêu chí pilot có thể xác minh

Một máy phụ đã xác định OS/CPU/RAM; chọn đúng model Official ONNX và preset cố định. Từ máy chính gửi một câu, nhận WAV đúng sample rate/duration/hash, nghe kiểm tra nội dung; gửi câu thứ hai để xác nhận dùng lại model resident. Sau đó thử đoạn dài, hủy khi đang chạy, mất mạng/nối lại và restart worker; job/đầu ra đã được xác minh phải không mất hay bị gửi lại mù. Chỉ khi có số đo thật mới chốt trần luồng, thời hạn chờ và quy mô batch dài. Chưa có kết quả benchmark hay triển khai máy khác trong báo cáo này.

## Câu hỏi còn mở

- Máy phụ nào, hệ điều hành/kiến trúc, CPU/RAM và mạng LAN hay Internet?
- Người dùng muốn Official ONNX cho pilot hay giữ biến thể GGUF đang chọn ở Studio?
- Máy phụ dùng chung cho công việc khác hay dành riêng cho worker, để chốt mức dùng CPU?
