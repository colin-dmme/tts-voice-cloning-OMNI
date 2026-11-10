# Pha 4. Adapter CPU dùng chung cho ZeroTTS, Piper ONNX và VieNeu

Trạng thái: thiết kế đã khảo sát; chưa triển khai. Hợp đồng trong tài liệu này được dùng ngay khi xây host worker ở pha 1. ZeroTTS là adapter đầu; bật Piper và VieNeu sau khi pilot ZeroTTS qua.

## Căn cứ và phạm vi

[Khảo sát adapter](C:/Coder/tts-voice-cloning-OMNI/plans/2026-11-09-zerotts-may-cpu-tu-xa/reports/cpu-provider-adapters.md) · [UI/target](C:/Coder/tts-voice-cloning-OMNI/plans/2026-11-09-zerotts-may-cpu-tu-xa/reports/cpu-target-ui-contract.md).

Phần dùng chung là ghép máy/quyền, HTTPS, job store, lease/retry, cache theo đoạn, progress, download/hash, pause/cancel, log và cập nhật worker. Phần riêng là cài/nạp SDK, model/voice, chuẩn hóa tham số và synthesize. Một host worker phục vụ các adapter, dùng một hàng đợi và một slot inference; không tạo endpoint mới cho mỗi provider.

## Hợp đồng chung

| Thao tác | Trách nhiệm |
|---|---|
| `describe` | Model/provider/adapter ID, revision, SDK, backend/precision, trạng thái đã cài/có thể nạp/ready, voice modes, native sample rate và option schema |
| `activate(model_ref, host_policy)` | Resolve file tại máy phụ, kiểm revision/assets/runtime CPU; đóng slot cũ khi rảnh, nạp/warm-up rồi xác nhận ready |
| `synthesize(unit, assets, cancel)` | Nhận payload typed đã lưu; chạy SDK riêng trong subprocess có timeout/hủy; không nhận shell, đường dẫn máy chính hoặc URL SDK tùy ý |
| `close` | Đóng subprocess/model thuộc adapter, xác nhận thu hồi slot trước đổi provider |
| Kết quả | WAV hoàn tất, mapping unit, native sample rate/channels/duration/size/SHA-256 và runtime thực tế |

Runtime từng engine ở venv riêng; Python host không import mọi SDK vào cùng môi trường. CPU policy và activation key gồm backend/precision/threads; inference options là nhóm khác, được validate theo adapter. Thêm provider CPU bằng đăng ký adapter/manifest và kiểm thử hợp đồng, không thêm logic provider vào vận chuyển/hàng đợi/UI chung.

Request có model/adapter/revision chính xác, text hoặc segments đã chốt, preset hoặc reference asset hợp lệ, options typed, target CPU và unit/idempotency key. Model path do máy phụ resolve từ registry. Bổ sung schema/capability tương ứng cho segments/batch/clone, giữ validator và giới hạn; không nhét payload chưa kiểm vào metadata để lách chốt model hiện tại. Phiên PC được cấp quyền theo allowlist nhiều model; phiên Colab cũ giữ tương thích.

## ZeroTTS Official

- Reuse engine và handler hiện có, gia cố bằng resident helper có timeout/log, probe trước READY.
- Giữ 48 kHz, preset `.npz`, preprocessing/sampling đã được Core xác thực; model/snapshot đúng manifest.
- Các bản GGUF là adapter khác; chưa tự nhận hỗ trợ chỉ vì cùng provider ZeroTTS.

## Piper ONNX

- Thêm adapter và routing remote; package `engines/piper_worker/{synthesize.py,pyproject.toml,uv.lock}` theo allowlist. Reuse engine/worker hiện có, không tạo bản fork logic tổng hợp.
- Registry model phải có ONNX + JSON đúng voice, numeric speaker nếu model nhiều speaker. Giữ speed → `length_scale=1/speed`, noise_scale/noise_w và seed, gồm giá trị 0 hợp lệ.
- Giữ `segments[{text,pause_after_ms}]` do Core chuẩn bị. Chốt khoảng nghỉ ngẫu nhiên một lần trong payload/checkpoint; retry không bốc lại. Không chèn cùng khoảng nghỉ ở cả máy chính và worker.
- Giữ semantics seed/session của worker, không hứa bit-exact giữa CPU/SDK khác nhau.
- Đọc native sample rate từ model/WAV: catalog đã có 22050 Hz và 16000 Hz. Không ép metadata toàn hệ thống thành 48 kHz; hậu xử lý/resample chỉ ở bước đã xác định.
- Không nhập pool local hai tiến trình/cache nhiều voice vào host slot một model. Đổi voice/model cần unload/close tương ứng.

## VieNeu v3 CPU

- Reuse `VieneuResidentHandler(device=cpu)` và `engines/vieneu_v3_worker`, SDK 3.6.4. CPU chạy ONNX FP32 mặc định; model/preset/codec đúng manifest v3.
- Handler đã có warm-up, resident, preset, clone và batch. Bỏ hardcode threads/max_batch bằng host policy đã validate; không dùng cấu hình CPU/GPU của máy chính để suy cấu hình máy phụ, không âm thầm nhận INT8 khi runtime chưa đáp ứng.
- Giữ temperature/top_k/repetition_window/denoise_reference và catalog 23 preset theo SDK. Clone truyền reference asset SHA-256 và nội dung được cấp quyền, không truyền đường dẫn Profile ổ C/D.
- Batch chỉ cùng model/voice/language/options, giữ thứ tự và đúng số file, mono 48 kHz.
- VieNeu v2, GGUF và Ngọc Huyền 0.3B cũ dùng runtime khác, chỉ thêm sau bằng adapter riêng và test đúng model; không gộp toàn bộ 19 model trong nhãn provider thành đã hỗ trợ.

## UI dùng chung và tương thích

Provider/model tiếp tục được chọn như hiện tại. Model đã có adapter CPU remote sẽ có lựa chọn **CPU máy khác** và selector **Máy chạy**. Local Auto/CPU/GPU, nhãn precision của VieNeu và Higgs endpoint giữ ý nghĩa đúng. Khi máy chưa có model, hiển thị thiếu model trên máy phụ và bước chuẩn bị; máy chính không phải tải engine/model đó.

Giữ public `runtime_target=remote`; thêm typed target options `kind`, `worker_profile_id`, `backend`, lưu vào job/prefs/history. Mapper của UI chuyển lựa chọn CPU máy khác thành `existing_worker/cpu` và restore ngược lại. Khóa UI không được lưu thành runtime_target lạ rồi bị normalize thành Auto. Backend luôn kiểm đúng model/revision/backend/capability tại submit/lease. Higgs Remote GPU là remote API riêng; yêu cầu CPU worker không được gửi nhầm sang endpoint GPU đó.

## Source dự kiến

- Service: `D:/_coder/colin-tts-compute-service/src/colin_compute_service/pc_worker/` cho registry/dispatcher và `adapters/` cho từng engine; sửa `worker.py`, `protocol.py`, `pairing.py`, `server.py`, `worker_package.py` theo hợp đồng tương thích.
- Studio: `C:/Coder/tts-voice-cloning-OMNI/src/omni_tts_core/provider_registry.py`, `service.py`, `runtime_devices.py`, `ui_presenters/{control_policy,settings_state}.py`, `user_state.py`, `engines/base.py` và router chung.
- Shared/MCP: `C:/Coder/tts-voice-cloning-OMNI/src/omni_tts_shared/schemas.py`, `src/colin_studio_tts_mcp/contracts.py` và mapping hai đường text/file.
- Remote core: `C:/Coder/tts-voice-cloning-OMNI/src/colin_remote_compute/`, di chuyển dần từ package Colab với alias cũ; giữ adapter Google tại `colin_colab_remote`.

## Tiêu chí nghiệm thu

- [ ] ZeroTTS/Piper/VieNeu v3 dùng cùng host ID/profile, transport và điều khiển; chỉ một model active.
- [ ] Piper trả đúng 22050/16000 Hz theo model, đúng pause và tham số gồm noise/seed 0; VieNeu preset/clone đúng 48 kHz.
- [ ] Đổi provider thu hồi slot/RAM, không sót model hoặc pool; cancel dừng đúng subprocess sở hữu.
- [ ] Worker/model thiếu, sai revision/backend/voice/quyền bị chặn rõ, không đổi sang local/GPU/Colab.
- [ ] Preferences/history/MCP round-trip target/profile; Auto local và request cũ giữ hành vi cũ; không gọi Google cho CPU PC.
- [ ] Remote vẫn chạy khi máy chính không cài model/engine; detector thiết bị local không quyết định remote readiness.
- [ ] Nghiệm thu WAV thật trên máy Windows qua Internet theo pha 3 cho từng adapter, trước khi công bố model đã hỗ trợ.
