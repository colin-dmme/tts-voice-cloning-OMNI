# Adapter CPU từ xa dùng chung: Piper ONNX và VieNeu v3

Ngày kiểm tra: 09/11/2026. Chỉ nghiên cứu source; chưa chạy inference, cài đặt hay truy cập máy đích.

## Hiện trạng đã xác minh

| Provider / model | Local hiện có | Remote hiện có | Phần còn thiếu cho máy CPU thường |
| --- | --- | --- | --- |
| ZeroTTS Official ONNX | Worker riêng, model resident, preset `.npz`, 48 kHz | Handler nhận `zerotts_202m_official` | Host dispatcher, bộ cài/mã ghép máy PC, startup probe và gia cố resident. Xem [báo cáo ZeroTTS](C:/Coder/tts-voice-cloning-OMNI/plans/2026-11-09-zerotts-may-cpu-tu-xa/reports/zerotts-runtime.md). |
| Piper ONNX | Worker JSONL resident, model/config của từng giọng, tùy chỉnh tốc độ/nhiễu/seed/khoảng nghỉ | Chưa có handler hay routing remote | Adapter Piper + chuẩn hóa request + capability theo model + allowlist/package source Piper. |
| VieNeu v3 Turbo 3.6.4 | Worker riêng, CPU ONNX FP32, preset/clone, 48 kHz; GPU là cấu hình khác | Đã có `VieneuResidentHandler(device='cpu')`, warmup, clone theo asset SHA-256, preset/batch | Dùng lại handler qua host dispatcher, thay runtime policy hardcode bằng cấu hình máy đã kiểm chứng, tách đích PC khỏi vòng cấp Colab. |
| VieNeu v2 / GGUF / Ngọc Huyền 0.3B cũ | `engines/vieneu_worker` với mode riêng | Handler remote v3 từ chối các model này | Cần adapter riêng khi mở rộng; không gán nhầm tên v3 hay dùng chung manifest v3. |

Studio hiện chặn `runtime_target='remote'` cho mọi model ngoài `zerotts_202m_official` và `vieneu_v3_turbo`. Remote worker chọn provider bằng nhánh ZeroTTS/VieNeu, không tự chạy được Piper chỉ nhờ model đó có trong danh sách UI. Nên thay điều kiện này bằng registry adapter/capability nhưng vẫn từ chối model chưa có adapter đã cài.

Nguồn: [service validation](C:/Coder/tts-voice-cloning-OMNI/src/omni_tts_core/service.py:1821), [remote worker](D:/_coder/colin-tts-compute-service/src/colin_compute_service/worker.py:357), [V3 handler](D:/_coder/colin-tts-compute-service/src/colin_compute_service/vieneu.py:17).

## Piper: giữ nguyên ý nghĩa request

- Cài riêng runtime `engines/piper_worker` và lockfile; manifest khai báo `piper-tts>=1.6.0`, lock hiện khóa 1.6.0. Mỗi model cần cả ONNX và JSON tương ứng. Registry máy đích ánh xạ `model_id` sang file tại máy đó; không gửi đường dẫn ổ C/D của máy chính làm đường dẫn suy luận.
- Giữ `speaker_id` dạng số cho model nhiều speaker, `speed` chuyển `length_scale=1/speed`, `noise_scale`, `noise_w`, `seed`. Giá trị 0 hợp lệ của noise/seed phải được giữ. Local không nhận clone audio cho Piper.
- Khoảng nghỉ được Core tách thành `segments=[{text,pause_after_ms}]`, kèm fallback `sentence_pause_ms`. Gửi đúng cấu trúc này để worker chèn PCM silence ở sample rate thật. Các khoảng nghỉ ngẫu nhiên dùng nguồn random riêng, không đồng nhất với `piper_seed`; cần chốt và lưu segments một lần cùng job để retry không bốc lại khoảng nghỉ.
- Khi có seed, worker hiện tạo session ONNX mới để seed áp dụng lúc dựng session; không thay bằng cache model thông thường rồi tuyên bố seed còn tương đương. Độ tái lập bit-exact giữa CPU/phiên bản thư viện khác nhau chưa được kiểm chứng.
- Không hardcode 48 kHz cho Piper. Đã đọc JSON model local: `piper_ngoc_huyen` là **22050 Hz**, `piper_25hours_single_low` là **16000 Hz**. Adapter trả metadata từ WAV thực, giữ native rate đến bước hậu xử lý chung.
- Worker hiện dùng LRU tối đa ba voice; local engine còn có pool hai tiến trình. Host remote theo yêu cầu một active model phải dùng một resident slot riêng, đóng tiến trình khi đổi model/provider, không nhập và tái sử dụng pool local hai tiến trình.

Nguồn: [Piper worker](C:/Coder/tts-voice-cloning-OMNI/engines/piper_worker/synthesize.py:29), [chuẩn bị payload và pause](C:/Coder/tts-voice-cloning-OMNI/src/omni_tts_core/engines/piper_engine.py:197), [pause selection](C:/Coder/tts-voice-cloning-OMNI/src/omni_tts_core/text/punctuation_pauses.py:18), [Piper manifest](C:/Coder/tts-voice-cloning-OMNI/engines/piper_worker/pyproject.toml), [voice catalog](C:/Coder/tts-voice-cloning-OMNI/config/piper_voices.yaml).

## VieNeu v3 CPU: tái sử dụng đúng handler

- Runtime độc lập `engines/vieneu_v3_worker`, `vieneu==3.6.4`, Python `>=3.10,<3.13`; thống nhất host pilot Python 3.12 vẫn phù hợp. CPU phải xác nhận `backend='onnx',device='cpu',precision='fp32'`. Không lấy lựa chọn Colab/GPU làm thiết lập CPU.
- Handler remote hiện đã ép đúng CPU ONNX khi `device='cpu'`, warmup trước ready và dùng `ResidentJsonWorker` có hủy/timeout/log. Tuy nhiên `_runtime()` hardcode `threads=8`, `max_batch_size=4`, FP32 và repo/subfolder. Nên resolve một host runtime policy được kiểm tra, đưa policy vào model activation key và hiển thị lại cấu hình thực tế. Không âm thầm nhận `int8` từ UI vì handler hiện chưa đưa lựa chọn đó vào runtime.
- Giữ catalog 23 preset từ SDK `--describe`; chọn fixed voice thì gửi `speaker_id/voice_name`, chọn clone thì gửi asset SHA-256 qua broker. Worker tải/xác minh mẫu và cache embedding/codes tối đa 16 giọng theo hash + denoise; không chuyển đường dẫn Profile trên máy chính sang máy khác.
- Giữ `temperature`, `top_k`, `repetition_window`, `denoise_reference` và kiểm tra miền giá trị. Những setting constructor khác không thuộc allowlist request hiện tại; không trộn constructor policy và inference options rồi truyền tùy ý.
- Batch chỉ gom các unit cùng model/voice hoặc mẫu clone/language/options. Worker đòi đúng số WAV, mono 48 kHz; bảo toàn thứ tự, hash và ánh xạ unit. V3 có sample rate/codec/preset khác với model VieNeu cũ dù trùng nhãn Ngọc Huyền.

Nguồn: [V3 manifest](C:/Coder/tts-voice-cloning-OMNI/engines/vieneu_v3_worker/pyproject.toml), [V3 resident SDK](C:/Coder/tts-voice-cloning-OMNI/engines/vieneu_v3_worker/synthesize.py:42), [V3 remote handler](D:/_coder/colin-tts-compute-service/src/colin_compute_service/vieneu.py:34), [remote batch preparation](C:/Coder/tts-voice-cloning-OMNI/src/colin_colab_remote/inference.py:26).

## Hợp đồng adapter tối thiểu đề xuất

Một host worker nhận lease, xác thực model/capability và điều phối đúng một resident subprocess. Từng provider giữ `.venv` riêng. Host không import SDK nặng vào Python broker và không điều khiển máy chính qua đường dẫn request.

| Thao tác | Dữ liệu / kết quả cần có |
| --- | --- |
| `describe` | Adapter/model ID, phiên bản SDK, revision/hash asset, backend/precision, preset/clone/segment/batch flags, sample rate thực, giới hạn tải. |
| `activate(model_ref, host_policy)` | Kiểm tra file/hash và dependency; đóng active slot cũ khi an toàn; nạp/warmup; chỉ trả ready sau probe. Key gồm adapter/model/revision/backend/precision/threads. |
| `synthesize(unit, assets, cancel)` | Unit ID/idempotency đã lưu; text hoặc segments đã chốt; voice cố định hoặc reference asset; option typed theo adapter; scratch/output tại máy đích. |
| `close` | Dừng đúng subprocess đang sở hữu, thu hồi RAM/cache; báo xác nhận trước khi đổi provider hoặc model. |
| Kết quả | File WAV hoàn tất, sample rate/channels/duration/size/SHA-256, mapping unit, phiên bản runtime và thời gian xử lý. |

Protocol hiện chỉ cho `reference_audio_id` và `batch_texts` đối với V3. Với Piper, chọn một unit/lượt ở pilot; nếu mở rộng batch/segments chung, phải thêm schema/version/capability tương ứng ở cả Studio lẫn broker/worker, không lách bằng `batch_texts` dành riêng cho V3 hoặc metadata không được xác thực. Piper single-speaker là mỗi voice một model; V3 là một model với nhiều preset. Registry phải thể hiện được cả hai.

## Kiểm chứng cần thực hiện khi triển khai

1. So payload local/remote đã chuẩn hóa bằng cùng adapter: Piper pauses cố định/ngẫu nhiên đã chốt, noise 0, seed 0; V3 preset và clone có/không denoise.
2. Piper thật trả 22050 Hz và 16000 Hz theo hai model trên; V3 trả mono 48 kHz. WAV/hash đúng và kết quả không bị hiểu nhầm là 48 kHz toàn hệ thống.
3. Đổi Piper → ZeroTTS → V3 CPU: tại mỗi thời điểm chỉ một model active; không sót pool local, RAM được thu hồi; hủy chỉ dừng SDK sở hữu.
4. Dependency thiếu, model chưa tải, model sai revision, preset không tồn tại và CPU policy không hỗ trợ phải báo lỗi cụ thể; không tự đổi model/giọng/backend.
5. Pilot thực trên máy đã xác định OS/CPU/RAM; đo cold/warm time và RAM. Chưa có bằng chứng chạy các adapter mới qua máy khác trong báo cáo này.
