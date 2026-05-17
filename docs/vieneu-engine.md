# VieNeu TTS Engine — Tài liệu tích hợp & kiến trúc

> **Cập nhật lần cuối:** 2026-05-15
> **Phiên bản:** v1.2 (lora mode rewrite + 3-tier model status)
> **Liên quan:** `engines/vieneu_worker/`, `src/omni_tts_core/engines/vieneu_engine.py`, `config/models.yaml`
> **Quyết định kỹ thuật:** đọc `docs/engineering-decisions.md` trước khi sửa model/runtime, đặc biệt phần Ngọc Huyền LoRA.

---

## 1. Bối cảnh & lý do thiết kế

VieNeu TTS là engine TTS tiếng Việt chất lượng cao nhất trong dự án. Nó được chạy trong một **subprocess worker riêng** thay vì in-process, vì:

- Dependency conflicts: VieNeu cần `neucodec`, `llama-cpp-python`, và các phiên bản torch cụ thể có thể xung đột với OmniVoice/Qwen/Valtec.
- Cách ly lỗi: worker crash không kéo theo toàn bộ app.
- Linh hoạt: CUDA vs CPU, LoRA vs GGUF — chỉ cần cài đặt khác nhau trong `.venv` riêng.

**Giao tiếp giữa core và worker:** Core viết `request.json` → worker đọc → sinh `output.wav` → core đọc numpy array.

---

## 2. Kiến trúc worker (sau refactor v1.1)

```
engines/vieneu_worker/
├── synthesize.py           ← entry point + mode dispatcher (~72 dòng)
├── worker_utils.py         ← shared helpers: vieneu_kwargs, infer_kwargs, flatten_codes... (~53 dòng)
├── modes/
│   ├── __init__.py         ← re-export tất cả create/run functions
│   ├── standard.py         ← GGUF + neucodec + speech_token_gguf (~101 dòng)
│   ├── turbo.py            ← ONNX encoder/decoder turbo (~48 dòng)
│   ├── pytorch_mode.py     ← Full float PyTorch weights (~58 dòng)
│   └── lora_mode.py        ← LoRA adapter via voices.json (~87 dòng)
└── pyproject.toml          ← deps (cpu mặc định; optional: cuda, lora groups)
```

### Dispatcher pattern

`synthesize.py` dùng `_MODE_HANDLERS` dict để lookup mode → module → functions:

```python
_MODE_HANDLERS = {
    "standard": ("modes.standard", "create_standard_tts", "run_standard", "run_standard_batch"),
    "turbo":    ("modes.turbo",    "create_turbo_tts",    "run_turbo",    "run_turbo_batch"),
    "pytorch":  ("modes.pytorch_mode", "create_pytorch_tts", "run_pytorch", "run_pytorch_batch"),
    "lora":     ("modes.lora_mode",    "create_lora_tts",   "run_lora",    "run_lora_batch"),
}
```

**Thêm mode mới:** chỉ cần 1 dòng trong dict này + tạo file mode tương ứng.

---

## 3. Luồng dữ liệu đầy đủ

```
UI (Tkinter/Gradio)
  └─ TtsService.generate_audio(GenerateSpeechRequest)
       └─ VieneuSubprocessEngine.generate(TtsEngineRequest)
            └─ viết request.json vào temp dir
            └─ spawn: python synthesize.py --request <path>
                 └─ synthesize.py: load payload, detect mode
                 └─ create_<mode>_tts(Vieneu, payload) → tts object
                 └─ apply_runtime_overrides(tts, payload)
                 └─ run_<mode>(tts, payload) → audio array
                 └─ tts.save(audio, output.wav)
            └─ đọc output.wav → numpy float32
            └─ TtsEngineResult(audio, sample_rate)
```

---

## 4. Mode system — chi tiết từng mode

### 4.1 `standard` (GGUF + neucodec)

Dùng cho tất cả model dạng GGUF quantized. Backbone là llama-cpp-python, codec là ONNX neucodec.

**Runtime fields:**
| Field | Bắt buộc | Mô tả |
|---|---|---|
| `backbone_repo` | ✓ | HF repo chứa GGUF |
| `gguf_filename` | ✓ | Tên file .gguf |
| `codec_repo` | ✓ | HF repo codec ONNX |
| `codec_device` | — | `"cpu"` hoặc `"cuda"` |
| `backbone_device` | — | `"cpu"` hoặc `"cuda"` |
| `emotion` | — | `"natural"` hoặc `"storytelling"` |
| `legacy_chat_format` | — | `true` cho model cũ (q8-gguf legacy) |
| `disable_emotion_tag` | — | `true` để tắt emotion token |
| `temperature` | — | Sampling temperature (0.1–2.0) |
| `top_k` | — | Top-K sampling (1–200) |
| `prompt_format` | — | `"speech_token_gguf"` cho audiobook mode |

**Voice selection hierarchy:**
1. `prompt_format == "speech_token_gguf"` → audiobook phoneme mode
2. `ref_audio` có → voice cloning qua neucodec
3. `voice_name` có → dùng preset voice từ model
4. Không có gì → synthesize với model default voice

### 4.2 `turbo` (ONNX encoder/decoder)

Nhanh hơn standard ~2-3x. Dùng ONNX encoder/decoder thay GGUF cho voice encoding. Không hỗ trợ emotion. Có thể clone voice không cần transcript.

**Runtime fields:**
| Field | Bắt buộc | Mô tả |
|---|---|---|
| `backbone_repo` | ✓ | HF repo chứa GGUF turbo |
| `backbone_filename` | ✓ | Tên file GGUF turbo |
| `decoder_repo` | ✓ | VieNeu-Codec repo |
| `decoder_filename` | ✓ | `vieneu_decoder.onnx` |
| `encoder_repo` | ✓ | VieNeu-Codec repo |
| `encoder_filename` | ✓ | `vieneu_encoder.onnx` |
| `device` | — | `"cpu"` hoặc `"cuda"` (unified cho cả backbone + codec) |

**Batch optimization:** Turbo mode encode reference audio 1 lần, dùng lại cho tất cả chunk — tăng tốc đáng kể cho text dài.

### 4.3 `pytorch` (Full float PyTorch)

Load `model.safetensors` trực tiếp qua Vieneu library thay vì GGUF. Chất lượng cao nhất nhưng nặng hơn (0.6B = 1.1GB, 0.3B = 488MB).

**Runtime fields:** Giống standard nhưng **không có `gguf_filename`** — đây là điểm khác biệt duy nhất. Vieneu tự phát hiện và load PyTorch weights.

**Khi nào dùng:** Khi cần chất lượng tối đa; máy có đủ RAM/VRAM; làm audiobook dài.

### 4.4 `lora` legacy/experimental

Đường chạy cũ để thử LoRA Ngọc Huyền bằng voice codes trong `voices.json`.
Đây không phải cách load PEFT LoRA adapter chuẩn.

**Cách hoạt động legacy (voices.json approach):**
1. Load base GGUF model (`backbone_repo` + `gguf_filename`) — standard factory
2. Đọc `voices.json` từ LoRA repo trong HF local cache (`local_files_only=True`)
3. Lấy voice dict `{codes, text}` → inject vào `tts.infer(voice=...)`
4. Synthesize với voice embedding từ LoRA repo (bypass preset voice của base model)

> **Ghi chú 2026-05-15:** Tài nguyên gốc HF của LoRA có `voices.json` với câu reference đầy đủ `Tác phẩm dự thi bảo đảm tính khoa học, tính đảng, tính chiến đấu, tính định hướng.` và 227 speech codes. Việc cắt tay codes/text chỉ là workaround giảm rò reference text, không phải hướng chạy ổn định. Production hiện ưu tiên model PyTorch đã merge riêng: `pnnbao-ump/VieNeu-TTS-0.3B-ngoc-huyen`. Bản GGUF Q4 hiện giữ Debug/Legacy vì đã rò reference text trong test thực tế.

**Runtime fields:**
| Field | Bắt buộc | Mô tả |
|---|---|---|
| `backbone_repo` | ✓ | Base GGUF model repo (phải là `VieNeu-TTS-0.3B-q4-gguf`, không phải PyTorch 0.3B) |
| `gguf_filename` | ✓ | Base GGUF filename |
| `lora_repo` | ✓ | HF repo của LoRA adapter (dùng voices.json từ đây) |
| `codec_repo` | ✓ | ONNX codec repo |

---

## 5. Catalog VieNeu (trạng thái 2026-05-15)

### CPU Models (mặc định, cài qua `install_vieneu_worker.bat`)

| Model ID | Mode | HF Repo | File | Kích thước | Ghi chú |
|---|---|---|---|---|---|
| `vieneu_v2_standard` | standard | pnnbao-ump/VieNeu-TTS-v2 | VieNeu-TTS-v2-Q4-K-M.gguf | ~400MB | Model chính, 7 voices |
| `vieneu_v2_turbo` | turbo | pnnbao-ump/VieNeu-TTS-v2-Turbo-GGUF | vieneu-tts-v2-turbo.gguf | ~100MB | Nhanh nhất, 4 voices |
| `vieneu_v2_turbo_gguf` | turbo | pnnbao-ump/VieNeu-TTS-v2-Turbo-GGUF | (same) | ~100MB | Alias, không voice profile |
| `vieneu_legacy_q8_gguf` | standard | pnnbao-ump/VieNeu-TTS-q8-gguf | VieNeu-TTS-q8_0.gguf | ~720MB | Legacy prompt format |
| `vieneu_03b_q4_gguf` | standard | pnnbao-ump/VieNeu-TTS-0.3B-q4-gguf | VieNeu-TTS-0_3B-Q4_0.gguf | ~190MB | Nhẹ nhất |
| `vieneu_03b_q8_gguf` | standard | pnnbao-ump/VieNeu-TTS-0.3B-q8-gguf | VieNeu-TTS-0_3B-Q8_0.gguf | ~350MB | Chất lượng cao hơn q4 |
| `vieneu_audiobook_nguyen_brat_q4` | standard | nguyen-brat/nguyen-ngoc-ngan-vieneu-tts-fine-tune | vieneu_q4_k_m.gguf | — | Community finetune audiobook |
| `vieneu_v2_mradermacher_q5km` | standard | mradermacher/VieNeu-TTS-GGUF | VieNeu-TTS.Q5_K_M.gguf | ~484MB | Q5 > Q4 về chất lượng |
| `vieneu_v2_mradermacher_q6k` | standard | mradermacher/VieNeu-TTS-GGUF | VieNeu-TTS.Q6_K.gguf | ~570MB | Gần lossless |
| `vieneu_v2_mradermacher_q8` | standard | mradermacher/VieNeu-TTS-GGUF | VieNeu-TTS.Q8_0.gguf | ~595MB | Lossless quantization |
| `vieneu_06b_pytorch` | pytorch | pnnbao-ump/VieNeu-TTS | model.safetensors | ~1.1GB | Full float, chất lượng tối đa |
| `vieneu_03b_pytorch` | pytorch | pnnbao-ump/VieNeu-TTS-0.3B | model.safetensors | ~488MB | Full float 0.3B |
| `vieneu_ngoc_huyen_03b_pytorch` | pytorch | pnnbao-ump/VieNeu-TTS-0.3B-ngoc-huyen | model.safetensors | ~488MB | Ngọc Huyền full/merged, đường chính |
| `vieneu_ngoc_huyen_03b_q4_gguf` | standard | pnnbao-ump/VieNeu-TTS-0.3B-ngoc-huyen-gguf-Q4_0 | VieNeu-TTS-0.3B-ngoc-huyen-Q4_0.gguf | ~190MB | Debug/Legacy: rò reference text trong test 2026-05-15 |
| `vieneu_lora_ngoc_huyen` | lora | pnnbao-ump/VieNeu-TTS-0.3B-lora-ngoc-huyen | adapter_model.safetensors | ~13MB adapter | Legacy experimental, không khuyến nghị cho production |

### CUDA/GPU Legacy Shortcuts (cài qua `install_vieneu_worker_cuda.bat`)

| Model ID | Mode | Base | Device | Ghi chú |
|---|---|---|---|---|
| `vieneu_v2_standard_cuda` | standard | pnnbao-ump/VieNeu-TTS-v2 | cuda | Legacy shortcut, ưu tiên model thường + `Thiết bị xử lý = GPU CUDA` |
| `vieneu_v2_turbo_cuda` | turbo | pnnbao-ump/VieNeu-TTS-v2-Turbo-GGUF | cuda | Legacy shortcut, ưu tiên model thường + `Thiết bị xử lý = GPU CUDA` |
| `vieneu_03b_q4_cuda` | standard | pnnbao-ump/VieNeu-TTS-0.3B-q4-gguf | cuda | Legacy shortcut, ưu tiên model thường + `Thiết bị xử lý = GPU CUDA` |

---

## 6. Cách thêm model mới (không cần viết code)

Chỉ cần thêm entry vào `config/models.yaml` với đúng `provider: "vieneu"` và `runtime.vieneu_mode`:

```yaml
# Ví dụ: thêm mradermacher Q3_K_M
vieneu_v2_mradermacher_q3km:
  display_name: "VieNeu TTS v2 Q3_K_M (mradermacher)"
  provider: "vieneu"
  model_type: "tts"
  local_path: "engines/vieneu_worker/.venv"
  hf_repo: "mradermacher/VieNeu-TTS-GGUF"
  language_priority: "vi-en"
  required: false
  capabilities:
    supported_languages: ["auto", "vi", "en"]
    supports_voice_profile: true
    supports_reference_text: true
    supports_voice_presets: true
    supports_speed: false
    supports_pitch_shift: false
    supports_emotion: true
    emotions: ["natural", "storytelling"]
  runtime:
    vieneu_mode: "standard"
    backbone_repo: "mradermacher/VieNeu-TTS-GGUF"
    gguf_filename: "VieNeu-TTS.Q3_K_M.gguf"   # ← đổi filename
    codec_repo: "neuphonic/neucodec-onnx-decoder-int8"
    codec_device: "cpu"
    backbone_device: "cpu"
  default_voice_preset: "Ly"
  voice_presets:
    # copy từ model cùng dòng
  notes: "..."
```

Restart UI → model tự xuất hiện trong dropdown. Không cần sửa code.

---

## 7. Cách thêm mode mới (khi Vieneu ra API mới)

**3 bước:**

**Bước 1:** Tạo `engines/vieneu_worker/modes/newmode.py`

```python
# Bắt buộc export 3 functions:
def create_newmode_tts(vieneu_factory, payload): ...
def run_newmode(tts, payload): ...
def run_newmode_batch(tts, chunks, base_payload): ...
```

**Bước 2:** Thêm 1 dòng vào `synthesize.py:_MODE_HANDLERS`:

```python
"newmode": ("modes.newmode", "create_newmode_tts", "run_newmode", "run_newmode_batch"),
```

**Bước 3:** Nếu cần runtime fields mới, thêm vào `allowed` set trong `src/omni_tts_core/engines/vieneu_engine.py:_runtime_payload()` (line ~171).

---

## 8. GPU Setup (GTX 1080 Ti / Pascal CUDA 6.1)

### Yêu cầu
- Driver NVIDIA hỗ trợ CUDA 11.x (Pascal tương thích tốt nhất với cu118)
- ~2–3GB VRAM trống khi chạy (model VieNeu nhỏ, không bị giới hạn VRAM)

### Cài đặt

```bat
install_vieneu_worker_cuda.bat
```

Script cài:
1. `torch+cu118` (tương thích Pascal tốt nhất)
2. `llama-cpp-python` với CUDA cuBLAS backend (hoặc build từ source nếu không có pre-built wheel)
3. `onnxruntime-gpu` (thay thế CPU onnxruntime cho codec)
4. `neucodec`, `huggingface_hub`

### Sử dụng
Chọn model VieNeu thường trong UI, sau đó vào tab `Nâng cao` và đặt `Thiết bị xử lý = GPU CUDA`. Không thêm model mới chỉ vì khác CPU/GPU. Các model `_cuda` cũ chỉ giữ để tương thích cấu hình cũ và debug.

### Kiểm tra GPU đang dùng

```python
# Trong worker subprocess, kiểm tra
import torch; print(torch.cuda.is_available())  # True nếu OK
```

---

## 9. Voice Presets — tổng hợp

### 7 voices của VieNeu-TTS v2 / 0.6B standard
| Preset ID | Tên | Vùng |
|---|---|---|
| `Binh` | Thanh Bình | Nam miền Bắc |
| `Tuyen` | Phạm Tuyên | Nam miền Bắc |
| `Vinh` | Xuân Vĩnh | Nam miền Nam |
| `Doan` | Thục Đoan | Nữ miền Nam |
| `Ly` | Trúc Ly | Nữ miền Bắc |
| `Sơn` | Thái Sơn | Nam miền Nam |
| `Ngoc` | Bích Ngọc | Nữ miền Bắc |

### 4 voices của VieNeu-TTS v2 Turbo
`Bích Ngọc (Nữ - Miền Bắc)`, `Phạm Tuyên (Nam - Miền Bắc)`, `Thục Đoan (Nữ - Miền Nam)`, `Xuân Vĩnh (Nam - Miền Nam)`

### LoRA Ngọc Huyền
Không dùng preset/profile. Với nhu cầu production, dùng `vieneu_ngoc_huyen_03b_pytorch`. Dòng `vieneu_ngoc_huyen_03b_q4_gguf` và `vieneu_lora_ngoc_huyen` chỉ còn là Debug/Legacy vì đã rò reference text trong test ngày 2026-05-15.

---

## 10. Files quan trọng cần biết

| File | Vai trò |
|---|---|
| `config/models.yaml` | **Source of truth** cho tất cả model — thêm/sửa/xóa model tại đây |
| `engines/vieneu_worker/synthesize.py` | Entry point worker + mode dispatcher |
| `engines/vieneu_worker/modes/standard.py` | Standard GGUF mode logic |
| `engines/vieneu_worker/modes/turbo.py` | Turbo ONNX mode + batch optimization |
| `engines/vieneu_worker/modes/pytorch_mode.py` | Full PyTorch weights mode |
| `engines/vieneu_worker/modes/lora_mode.py` | LoRA adapter mode (voices.json approach) |
| `engines/vieneu_worker/worker_utils.py` | Shared helpers dùng trong tất cả modes |
| `src/omni_tts_core/engines/vieneu_engine.py` | Core engine: build subprocess, whitelist runtime fields |
| `install_vieneu_worker.bat` | Cài CPU worker |
| `install_vieneu_worker_cuda.bat` | Cài GPU/CUDA worker |

---

## 11. Known issues & limitations

| Vấn đề | Mức độ | Trạng thái |
|---|---|---|
| Dòng legacy `vieneu_lora_ngoc_huyen` dùng `voices.json` thay vì PEFT LoRA thật, có thể rò reference text hoặc lệch tone | Trung | Giữ để debug; production chuyển sang `vieneu_ngoc_huyen_03b_pytorch` |
| `vieneu_ngoc_huyen_03b_q4_gguf` bị rò reference text trong test thực tế ngày 2026-05-15, audio dài bất thường so với PyTorch Full | Trung | Giữ Debug/Legacy; chỉ production nếu có bản quantize mới vượt smoke test |
| PEFT LoRA full integration vẫn cần smoke test riêng với `load_lora_adapter()` trước khi đưa ra UI ổn định | Thấp | Chưa bật mặc định |
| llama-cpp-python CUDA build có thể phức tạp trên Windows | Trung | Script có fallback sang build từ source |
| mradermacher GGUF: filenames xác nhận qua HF API (tháng 5/2026) | Thấp | Có thể thay đổi nếu repo được update |
| Turbo mode không hỗ trợ emotion | N/A | By design của VieNeu library |

---

## 12. HuggingFace repos tham chiếu

| Repo | Mô tả |
|---|---|
| `pnnbao-ump/VieNeu-TTS-v2` | Model chính v2 (GGUF Q4-K-M) |
| `pnnbao-ump/VieNeu-TTS-v2-Turbo-GGUF` | Turbo backbone + VieNeu-Codec |
| `pnnbao-ump/VieNeu-Codec` | ONNX encoder/decoder cho Turbo |
| `pnnbao-ump/VieNeu-TTS-0.3B-q4-gguf` | 0.3B Q4 GGUF |
| `pnnbao-ump/VieNeu-TTS-0.3B-q8-gguf` | 0.3B Q8 GGUF |
| `pnnbao-ump/VieNeu-TTS-q8-gguf` | 0.6B Q8 legacy (prompt cũ) |
| `pnnbao-ump/VieNeu-TTS` | 0.6B full float (model.safetensors 1.1GB) |
| `pnnbao-ump/VieNeu-TTS-0.3B` | 0.3B full float (model.safetensors 488MB) |
| `pnnbao-ump/VieNeu-TTS-0.3B-ngoc-huyen` | Ngọc Huyền full/merged PyTorch |
| `pnnbao-ump/VieNeu-TTS-0.3B-ngoc-huyen-gguf-Q4_0` | Ngọc Huyền GGUF Q4 CPU |
| `pnnbao-ump/VieNeu-TTS-0.3B-lora-ngoc-huyen` | LoRA adapter Ngọc Huyền (12.8MB) |
| `mradermacher/VieNeu-TTS-GGUF` | Community quants: Q2→Q8, F16 |
| `nguyen-brat/nguyen-ngoc-ngan-vieneu-tts-fine-tune` | Community fine-tune audiobook |
| `neuphonic/neucodec-onnx-decoder-int8` | ONNX codec decoder (standard mode) |
| `neuphonic/distill-neucodec` | Legacy distill codec (voice cloning fallback) |

---

## 13. Roadmap tính năng liên quan

- [ ] **PEFT LoRA full integration** — Áp dụng adapter_model.safetensors vào backbone khi Vieneu library hỗ trợ, hoặc implement PEFT bypass. File cần sửa: `modes/lora_mode.py`.
- [x] **Runtime target selector** — Model thường có thể chọn `Auto`, `CPU`, hoặc `GPU CUDA` từ UI.
- [ ] **Model download progress** — Hiển thị tiến trình tải model HuggingFace trong UI.
- [ ] **Persistent TTS instance** — Hiện tại mỗi request spawn 1 subprocess mới; có thể giữ worker alive để tăng tốc (cần refactor sang long-running subprocess với stdin/stdout protocol).
- [ ] **F16 GGUF support** — `VieNeu-TTS.f16.gguf` (1.1GB) từ mradermacher — chỉ cần thêm YAML entry.
