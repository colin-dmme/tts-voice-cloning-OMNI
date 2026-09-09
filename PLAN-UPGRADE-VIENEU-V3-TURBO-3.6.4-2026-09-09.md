# PLAN — Nâng VieNeu v3 Turbo từ SDK 3.3.0 lên 3.6.4

Ngày lập: 2026-09-09  
Dự án: `C:\Coder\tts-voice-cloning-OMNI`  
Máy mục tiêu hiện tại: COLINPC  
Mục đích: bàn giao cho Codex triển khai nâng cấp VieNeu v3 Turbo theo hướng an toàn, ít phá hành vi hiện có, ưu tiên giữ ổn định pipeline TTS đang dùng.

---

## 1. Mục tiêu

Nâng integration `VieNeu v3 Turbo` trong Colin TTS Local từ `vieneu==3.3.0` lên `vieneu==3.6.4`, đồng bộ dependency, voice catalog, runtime policy, test và thông tin UI với SDK mới.

Ưu tiên giai đoạn đầu là **nâng version mà không làm thay đổi workflow người dùng ngoài những thay đổi bắt buộc của upstream**.

Không nên gộp thêm nhiều feature mới như v3 Nano hoặc streaming UI vào cùng một thay đổi lớn. Sau khi baseline 3.6.4 chạy ổn định mới làm Phase 2 riêng.

---

## 2. Trạng thái source hiện tại đã kiểm chứng

### 2.1 Worker VieNeu v3 đang tách riêng đúng kiến trúc

Worker:

`engines/vieneu_v3_worker`

VieNeu v2/GGUF cũ vẫn dùng:

`engines/vieneu_worker`

Đây là cấu trúc nên giữ nguyên. Không merge hai worker lại.

### 2.2 Package đang khóa cứng ở VieNeu 3.3.0

File:

`engines/vieneu_v3_worker/pyproject.toml`

Hiện tại:

```toml
vieneu==3.3.0
sea-g2p>=0.9.0,<1.0.0
```

Mô tả package cũng ghi:

```text
Independent VieNeu v3 Turbo 3.3 runtime
```

File `uv.lock` cũng khóa:

```text
vieneu 3.3.0
```

Đã chạy trực tiếp Python trong worker `.venv` và xác nhận runtime thực tế:

```text
vieneu 3.3.0
sea-g2p 0.9.0
```

### 2.3 Worker hiện tại đã dùng API tương thích cơ bản với SDK mới

File:

`engines/vieneu_v3_worker/synthesize.py`

Luồng hiện tại:

- `Vieneu(mode="v3turbo", ...)`
- single: `tts.infer(...)`
- batch: `tts.infer_batch(...)`
- voice preset: `voice=`
- clone: `ref_audio=`
- denoise reference
- temperature
- top_k
- repetition_window
- persistent worker qua stdin/stdout

Các API chính này vẫn tồn tại trong 3.6.4 nên không cần viết lại worker từ đầu.

### 2.4 Config hiện tại đang đóng băng snapshot SDK 3.3

File:

`config/models.yaml`

Model:

```yaml
vieneu_v3_turbo:
  display_name: "VieNeu v3 Turbo 3.3 · 48 kHz"
```

Hiện tại:

- 20 preset voice
- default voice: `Adam`
- `precision: "int8"`
- CPU được ưu tiên
- download pattern bao gồm `onnx_int8/*`
- description/UI nói rõ SDK 3.3.0
- clone Profile 3–8 giây

Voice catalog hiện có 20 giọng:

1. Minh Đức
2. Phạm Tuyên
3. Thái Sơn
4. Xuân Vĩnh
5. Thanh Bình
6. Trúc Ly
7. Ngọc Linh
8. Đoan Trang
9. Mai Anh
10. Thục Đoan
11. Minh Triết
12. Thùy Dung
13. Quang Sơn
14. Ngọc Trân
15. Mỹ Duyên
16. Quỳnh Anh
17. Đức Trí
18. Kim Thanh
19. Ngọc Huyền
20. Adam

### 2.5 Tests hiện tại cố tình khóa behavior của 3.3.0

File:

`tests/test_vieneu_v3_integration.py`

Có test tên:

```python
test_vieneu_v3_catalog_matches_sdk_330_snapshot
```

Các assertion hiện tại yêu cầu:

- display name chứa `3.3`
- đúng 20 giọng
- default `Adam`
- runtime status chứa `SDK 3.3.0`
- runtime status chứa `CPU ONNX INT8`

Sau khi nâng dependency, nếu không sửa tests thì tests cũ vẫn ép project quay lại behavior 3.3.

### 2.6 Installer hiện tại

CPU:

`install_vieneu_v3_worker.bat`

Hiện log:

```text
Installing independent VieNeu v3 Turbo 3.3 CPU/ONNX worker...
```

GPU:

`install_vieneu_v3_worker_cuda.bat`

Hiện logic:

- đa số GPU: Torch 2.7.1 + CUDA 11.8
- RTX 50: Torch 2.8.0 + CUDA 12.8
- Transformers 4.57.6

Không được đổi GPU installer sang CUDA 12.8 cho mọi GPU một cách máy móc.

COLINPC đang dùng GTX 1080 Ti (Pascal). Với Pascal phải đặc biệt tránh một thay đổi CUDA/PyTorch làm mất support card cũ.

---

## 3. Upstream VieNeu 3.6.4 đã kiểm chứng

Đã tải wheel chính thức `vieneu-3.6.4` từ PyPI để inspect, chưa cài đè môi trường project.

### 3.1 Dependency

3.6.4 yêu cầu tối thiểu:

```text
sea-g2p>=0.9.1
onnxruntime>=1.20.0
kaldi-native-fbank>=1.20
```

Project hiện tại đang dùng `sea-g2p 0.9.0`, vì vậy dependency này chắc chắn phải được nâng.

### 3.2 Constructor của v3 Turbo 3.6.4

Các tham số chính vẫn tương thích với worker hiện tại:

```text
backbone_repo
model_subfolder
moss_tokenizer
device
backend
precision
onnx_subfolder
threads
max_batch_size
```

3.6.4 bổ sung/đáng chú ý thêm:

```text
dtype
onnx_repo
onnx_dir
babble_retries
```

### 3.3 CPU precision default đã đổi

3.6.4:

```text
precision="fp32"
```

FP32 là default upstream cho chất lượng tối đa.

INT8 vẫn có, nhưng upstream ghi rõ INT8 cần CPU hỗ trợ VNNI để tránh méo tiếng.

COLINPC dùng Intel i9-10900. Máy này không nên bị mặc định ép theo chiến lược INT8 như config hiện tại nếu chưa benchmark/validate chất lượng.

Khuyến nghị cho upgrade này:

**CPU default của VieNeu v3 Turbo nên chuyển về FP32 theo upstream.**

INT8 chỉ giữ như option nâng cao nếu runtime/hardware policy xác nhận phù hợp.

### 3.4 Voice catalog 3.6.4

3.6.4 có 23 preset voice.

Ba giọng mới so với snapshot 3.3:

- Mạnh Dũng
- Minh Quân
- Anh Khôi

Default voice mới:

```text
Minh Quân
```

Không còn `Adam` là default upstream.

### 3.5 Inference API mới/cải thiện

3.6.4 vẫn hỗ trợ:

```python
infer(...)
infer_batch(...)
```

Đồng thời có:

```python
infer_stream(...)
```

Các sampling option mới/được expose đầy đủ hơn gồm:

```text
top_p
max_new_frames
repetition_penalty
repetition_window
max_chars
silence_p
crossfade_p
apply_watermark
batch_size
```

Có thêm `babble_retries` ở engine/constructor để hạn chế tình trạng model nói thêm/babble ở chunk ngắn.

Không cần expose toàn bộ các setting mới lên UI ngay trong upgrade này.

---

## 4. Chiến lược nâng cấp được đề xuất

### Nguyên tắc

1. Nâng dependency trước.
2. Giữ architecture hiện có.
3. Giữ `vieneu_v3_worker` độc lập.
4. Không đụng VieNeu v2.
5. Không làm v3 Nano trong cùng PR/change set.
6. Không làm streaming UI trong cùng change set, trừ khi cần để sửa regression.
7. Không thay đổi nhiều setting người dùng cùng lúc.
8. CPU FP32 trở thành default theo upstream.
9. Giữ INT8 dưới dạng optional capability, không ép COLINPC dùng INT8.
10. GPU path phải giữ tương thích GTX 1080 Ti; không copy nguyên hướng dẫn CUDA mới của upstream mà bỏ kiểm tra architecture.

---

## 5. Phạm vi file dự kiến phải thay đổi

Tối thiểu kiểm tra và có khả năng sửa:

```text
engines/vieneu_v3_worker/pyproject.toml
engines/vieneu_v3_worker/uv.lock
engines/vieneu_v3_worker/README.md
engines/vieneu_v3_worker/synthesize.py
config/models.yaml
install_vieneu_v3_worker.bat
install_vieneu_v3_worker_cuda.bat
tests/test_vieneu_v3_integration.py
README.md
```

Ngoài ra search toàn repo các chuỗi:

```text
3.3.0
VieNeu v3 Turbo 3.3
20 giọng
CPU ONNX INT8
SDK 3.3.0
Adam
onnx_int8
```

Các file source/runtime status/UI presenter có hardcode text cũ phải được cập nhật.

Không sửa thủ công các bản copy trong `dist_portable` trước khi source chính chạy và test ổn định. Nếu portable cần cập nhật thì regenerate theo pipeline build của project sau cùng.

---

## 6. Kế hoạch triển khai chi tiết cho Codex

### Phase 0 — Bảo vệ worktree

Trước khi sửa:

```bash
git status
```

Trạng thái tại lúc lập plan:

```text
main...origin/main [ahead 2]
```

Repo đang có nhiều file untracked từ các công việc khác.

**Không chạy:**

```bash
git clean
git reset --hard
```

Không xóa các file temp/untracked không liên quan.

Chỉ sửa đúng file VieNeu cần thiết.

Nếu muốn branch riêng thì tạo branch mà không reset source hiện tại.

---

### Phase 1 — Update dependency và lock

Sửa:

`engines/vieneu_v3_worker/pyproject.toml`

Mục tiêu:

```toml
vieneu==3.6.4
sea-g2p>=0.9.1,<1.0.0
```

Sau đó chạy uv update/sync chỉ trong worker này để regenerate:

`engines/vieneu_v3_worker/uv.lock`

Không cài package VieNeu vào Python chính của app.

Worker phải tiếp tục có `.venv` riêng.

Sau sync, xác minh:

```text
vieneu 3.6.4
sea-g2p >= 0.9.1
```

---

### Phase 2 — Làm worker 3.6.4-compatible nhưng giữ behavior đơn giản

File:

`engines/vieneu_v3_worker/synthesize.py`

Giữ nguyên architecture persistent worker.

Kiểm tra constructor args hiện tại với 3.6.4.

Đề xuất:

- giữ `backbone_repo`
- giữ `model_subfolder`
- giữ `moss_tokenizer`
- giữ `device`
- giữ `backend`
- giữ `precision`
- giữ `onnx_subfolder`
- giữ `threads`
- giữ `max_batch_size`

Có thể thêm support optional cho:

```text
babble_retries
```

Nhưng chỉ expose trong payload/config nếu có lý do rõ ràng.

Không cần đưa tất cả `top_p`, `max_new_frames`, `watermark`, `crossfade` vào UI trong phase này.

Worker `_describe()` phải phản ánh **runtime thực**, không hardcode sai:

- SDK version từ package
- precision default theo config/runtime
- voice preset đọc từ `voices_v3_turbo.json`
- preset count thực
- default voice thực

Nếu `precision` không được cấu hình thì upstream 3.6.4 sẽ là FP32.

---

### Phase 3 — Đồng bộ model catalog

File:

`config/models.yaml`

Cập nhật display name:

```text
VieNeu v3 Turbo 3.6.4 · 48 kHz
```

Cập nhật voice catalog từ 20 → 23.

Thêm:

```text
Mạnh Dũng
Minh Quân
Anh Khôi
```

Đổi:

```yaml
default_voice_preset: "Minh Quân"
```

Không hardcode description voice nếu có thể đọc chính xác từ asset upstream hoặc snapshot đúng 3.6.4.

Cập nhật tooltip từ `20 giọng` thành `23 giọng`.

Cập nhật notes SDK 3.6.4.

### CPU policy

Đổi default:

```yaml
precision: "fp32"
```

Không còn mô tả `CPU ONNX INT8 mặc định`.

Mô tả phù hợp hơn:

```text
CPU ONNX FP32 mặc định; INT8 là tùy chọn tăng tốc cho CPU hỗ trợ VNNI; GPU PyTorch phù hợp batch dài.
```

### Download pattern

Không giữ `onnx_int8/*` như payload duy nhất nếu FP32 là default.

Inspect layout model 3.6.4/Hugging Face và cập nhật allow patterns sao cho CPU FP32 tải đủ backbone ONNX cần thiết.

Không đoán tên folder. Xác minh trực tiếp package/source/model repo trước khi sửa.

Nếu muốn hỗ trợ cả FP32 và INT8, downloader phải biết tải đúng payload theo precision thay vì tải thừa toàn bộ.

---

### Phase 4 — Runtime status/UI text

Search source các string cũ:

```text
SDK 3.3.0
CPU ONNX INT8
20 giọng
Adam
```

Runtime status nên hiển thị từ kết quả `synthesize.py --describe` hoặc model spec thực tế, tránh hardcode version mới lần nữa.

Mục tiêu dài hạn:

```text
SDK {actual_sdk_version}
CPU ONNX FP32
23 preset
```

Nếu chọn INT8 thì status phải hiện INT8 thật.

Nếu sau này worker được nâng tiếp 3.6.5 thì UI không nên vẫn ghi 3.6.4 sai thực tế.

Ưu tiên dynamic runtime status hơn hardcode khi có thể làm gọn.

---

### Phase 5 — Installer CPU

File:

`install_vieneu_v3_worker.bat`

Đổi text từ 3.3 sang 3.6.4 hoặc bỏ version hardcode nếu không cần.

Sau `uv sync`, bắt buộc chạy:

```text
synthesize.py --describe
```

Installer chỉ PASS khi describe trả đúng:

```text
sdk_version = 3.6.4
preset_count = 23
default_voice = Minh Quân
```

CPU ONNX cần smoke generation thật, không chỉ import package.

---

### Phase 6 — GPU installer: bảo toàn GTX 1080 Ti

Không được chuyển toàn bộ GPU sang:

```text
Torch 2.8 + cu128
```

một cách không kiểm chứng.

COLINPC dùng GTX 1080 Ti/Pascal.

Yêu cầu Codex:

1. Inspect yêu cầu thực của VieNeu 3.6.4 GPU backend.
2. Giữ logic phân nhánh GPU architecture.
3. Xác minh path hiện tại Torch 2.7.1 + cu118 có chạy VieNeu 3.6.4 không.
4. Nếu phải nâng Torch, chọn wheel còn support Pascal.
5. Sau cài phải chạy:

```python
import torch
print(torch.__version__)
print(torch.version.cuda)
print(torch.cuda.is_available())
print(torch.cuda.get_device_name(0))
print(torch.cuda.get_arch_list())
```

6. Với GTX 1080 Ti phải thấy architecture phù hợp `sm_61` trước khi coi GPU install là PASS.
7. Chạy ít nhất một generation GPU thật.

CPU path phải vẫn dùng được ngay cả khi GPU install fail.

---

### Phase 7 — Tests

Update:

`tests/test_vieneu_v3_integration.py`

Không chỉ đổi `330` → `364` trong tên test rồi giữ logic hardcode cũ.

Các test cần cover:

#### Catalog

- display name mới
- worker vẫn là `vieneu_v3_worker`
- default `Minh Quân`
- 23 presets
- ba voice mới tồn tại

#### Runtime

- package actual là 3.6.4
- CPU backend ONNX
- FP32 là default
- runtime status không nói INT8 khi đang chạy FP32

#### Worker

- `--describe` parse được
- preset count từ SDK asset
- fixed voice generation
- clone Profile generation
- batch generation
- output vẫn là WAV 48 kHz

#### Regression

- VieNeu v2 vẫn dùng worker cũ
- không thay đổi behavior của provider khác
- persistent worker vẫn tái sử dụng model thay vì reload mỗi chunk

---

## 7. Smoke test bắt buộc sau upgrade

### Test A — Describe

Chạy:

```text
engines/vieneu_v3_worker/.venv/Scripts/python.exe synthesize.py --describe
```

PASS khi:

```text
sdk_version = 3.6.4
preset_count = 23
default_voice = Minh Quân
backend CPU/ONNX hoạt động
```

### Test B — Fixed preset

Sinh một câu ngắn bằng `Minh Quân`.

Xác minh:

- file được tạo
- sample rate = 48000
- không silent
- không crash

### Test C — Voice cũ

Sinh một câu bằng `Ngọc Huyền` để xác minh upgrade không phá preset người dùng đang dùng.

### Test D — Voice clone

Dùng một Profile audio sạch 3–8 giây.

Xác minh:

- worker clone được
- không yêu cầu reference transcript
- denoise reference hoạt động
- output 48 kHz

### Test E — Batch

Sinh ít nhất 5 chunk bằng `infer_batch`.

Xác minh:

- đủ số output
- thứ tự output đúng
- persistent worker không reload model mỗi request

### Test F — CPU performance sanity

Benchmark ít nhất một đoạn khoảng 300–500 ký tự.

Ghi:

```text
elapsed time
audio duration
RTF
```

Không cần tối ưu ngay, chỉ đảm bảo không regression bất thường.

### Test G — GPU nếu cài GPU worker

Chỉ PASS GPU nếu generation thật chạy trên GTX 1080 Ti.

Không coi `torch.cuda.is_available() == True` là đủ.

---

## 8. Streaming — đề xuất Phase 2, không gộp upgrade baseline

VieNeu 3.6.4 đã có:

```python
infer_stream(...)
```

Đây là feature đáng tích hợp sau khi 3.6.4 baseline ổn định.

Project hiện tại core gọi subprocess và đợi WAV hoàn chỉnh. Để tận dụng `infer_stream`, cần thiết kế contract streaming xuyên qua:

```text
VieNeu worker
→ engine subprocess adapter
→ core
→ UI/MCP preview
```

Không nên chỉ gọi `infer_stream()` trong worker rồi vẫn đợi ghép xong WAV, vì như vậy không có lợi ích UX thật.

Tạo issue/plan riêng sau upgrade.

---

## 9. VieNeu v3 Nano — đề xuất để sau

Không tích hợp `v3nano` trong change set 3.6.4 này.

Lý do:

- mục tiêu hiện tại là ổn định v3 Turbo
- Nano có profile chất lượng/tốc độ khác
- cần model catalog riêng
- cần benchmark riêng
- cần quyết định xem là model mới trong UI hay mode runtime của cùng provider

Sau khi Turbo ổn định, có thể làm:

```text
vieneu_v3_nano
```

như một model/catalog entry riêng để người dùng hiểu rõ trade-off.

---

## 10. Những việc KHÔNG nên làm trong lần nâng này

Không:

- merge VieNeu v2 và v3 worker
- rewrite toàn bộ TTS engine
- thay UI lớn
- tích hợp Nano cùng lúc
- tích hợp streaming UI cùng lúc
- đổi CUDA toàn repo
- nâng PyTorch của các provider khác
- reset/clean worktree
- sửa các temp file không liên quan
- sửa dist portable bằng tay trước khi source ổn
- bỏ các preset cũ đang dùng
- ép INT8 trên COLINPC

---

## 11. Acceptance criteria

Upgrade chỉ coi là hoàn tất khi đạt tất cả:

- [ ] `vieneu==3.6.4`
- [ ] `sea-g2p>=0.9.1`
- [ ] `uv.lock` cập nhật đúng
- [ ] worker `.venv` describe báo 3.6.4
- [ ] 23 preset voice
- [ ] default preset = Minh Quân
- [ ] ba voice mới xuất hiện
- [ ] preset Ngọc Huyền vẫn hoạt động
- [ ] CPU ONNX FP32 là default
- [ ] INT8 không còn bị mô tả là default bắt buộc
- [ ] fixed voice generation PASS
- [ ] voice cloning PASS
- [ ] batch PASS
- [ ] WAV output 48 kHz
- [ ] runtime status/UI không còn string 3.3.0 sai
- [ ] tests VieNeu v3 PASS
- [ ] tests VieNeu v2 regression PASS
- [ ] không phá provider khác
- [ ] không xóa/thay đổi file không liên quan
- [ ] nếu chỉnh GPU installer: GTX 1080 Ti generation thật PASS

---

## 12. Deliverable Codex cần trả lại

Sau khi thực hiện, Codex phải báo cáo ngắn gọn:

1. File đã sửa.
2. Dependency trước/sau.
3. Voice catalog trước/sau.
4. CPU default trước/sau.
5. GPU installer có thay đổi hay không và lý do.
6. Tests đã chạy + kết quả.
7. Smoke audio đã chạy bằng voice nào.
8. Benchmark CPU nếu có.
9. Những phần cố tình để lại Phase 2.
10. Git diff/status cuối cùng.

Nếu gặp API incompatibility upstream, không workaround bằng hardcode bừa. Hãy dừng, ghi rõ lỗi thực tế, trace và đề xuất thay đổi nhỏ nhất.

---

## 13. Thứ tự thực hiện đề xuất

```text
1. Git status / bảo vệ worktree
2. Update pyproject → vieneu 3.6.4 + sea-g2p >=0.9.1
3. Regenerate uv.lock
4. Sync worker .venv
5. Chạy --describe trực tiếp
6. Điều chỉnh synthesize.py nếu API thay đổi
7. Smoke fixed voice bằng Minh Quân
8. Smoke preset cũ Ngọc Huyền
9. Smoke clone Profile
10. Smoke batch
11. Update models.yaml catalog/runtime policy
12. Update runtime/UI text
13. Update installer text và logic cần thiết
14. Update tests
15. Run full VieNeu regression tests
16. Kiểm tra VieNeu v2 không bị ảnh hưởng
17. Nếu cần GPU: test riêng GTX 1080 Ti
18. Git diff/status và báo cáo
```

---

## 14. Quyết định kỹ thuật khuyến nghị

Đối với tình trạng project hiện tại, hướng phù hợp nhất là:

> **Nâng VieNeu v3 Turbo 3.3.0 → 3.6.4 theo kiểu compatibility upgrade trước, giữ nguyên kiến trúc worker/core/UI hiện tại, chuyển CPU default từ INT8 sang FP32 theo upstream, đồng bộ 23 voices và default Minh Quân, rồi mới làm streaming/Nano thành phase riêng.**

Cách này giảm rủi ro hơn nhiều so với tranh thủ refactor hoặc tích hợp toàn bộ feature mới cùng lúc.

---

## 15. Hiệu chỉnh sau khi audit source và wheel 3.6.4

Các điều chỉnh dưới đây là một phần bắt buộc của kế hoạch triển khai:

1. `FP32` và `Minh Quân` là thay đổi policy/behavior, không chỉ là thay dependency.
   Phải lưu baseline 3.3.0 và chạy so sánh trước/sau bằng cùng văn bản.
2. Dựng môi trường canary 3.6.4 riêng. Không thay trực tiếp worker `.venv`
   đang hoạt động trước khi các smoke test cơ bản đạt yêu cầu.
3. `synthesize.py --describe` phải tách rõ SDK default và effective precision.
   Runtime status của app phải lấy effective precision từ model spec, không hardcode.
4. Source hiện chưa có setting cho người dùng chọn FP32/INT8 theo request. Bản
   0.5.1 dùng FP32 mặc định; selector precision được để lại cho phase riêng.
5. Cache cũ có thể chỉ chứa `onnx_int8`. ModelStorage phải precache/kiểm tra đúng
   `onnx_update/*` ngay cả khi repo đã có một snapshot cũ.
6. Đồng bộ toàn bộ metadata voice từ asset 3.6.4. Đặc biệt sửa vùng của `Xuân Vĩnh`
   theo asset upstream, không chỉ thêm ba voice mới.
7. Saved state đã chọn `Adam` vẫn được giữ vì `Adam` còn hợp lệ. `Minh Quân` chỉ
   trở thành default cho lựa chọn mới hoặc trạng thái chưa có preset hợp lệ.
8. MCP tiếp tục dùng shared core. Bổ sung test contract 23 voice và lọc mục voice
   rỗng `Không dùng preset` khỏi kết quả dành cho agent.
9. Không nâng MCP SDK trong cùng change set. Bản đang cài phải vượt protocol test;
   việc nâng MCP package là một thay đổi bảo trì độc lập.
10. Nâng version Colin TTS Local và MCP package từ `0.5.0` lên `0.5.1`, cập nhật
    README và CHANGELOG sau khi mọi smoke test đạt yêu cầu.
11. Rollback dùng worker/lock cũ đã giữ lại hoặc revert commit nâng cấp. Không dùng
    `git reset --hard` hay `git clean` vì repo có dữ liệu untracked của người dùng.
