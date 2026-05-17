# Engineering Decisions

> Source of truth cho các quyết định kỹ thuật cần giữ nhất quán khi dùng Codex, Cursor, Claude hoặc tự sửa code.

## 2026-05-15 — VieNeu Ngọc Huyền LoRA

### Quyết định

Không dùng `pnnbao-ump/VieNeu-TTS-0.3B-lora-ngoc-huyen` + `voices.json` injection làm đường production cho giọng Ngọc Huyền.

Đường production nên ưu tiên:

| Model ID trong app | Hugging Face repo | Runtime | Mục đích |
|---|---|---|---|
| `vieneu_ngoc_huyen_03b_pytorch` | `pnnbao-ump/VieNeu-TTS-0.3B-ngoc-huyen` | `pytorch` | Chất lượng chính cho Ngọc Huyền |

Hai dòng sau chỉ giữ làm legacy/debug và đưa vào catalog category `experimental`:

| Model ID trong app | Lý do không dùng production |
|---|---|
| `vieneu_ngoc_huyen_03b_q4_gguf` | Test ngày 2026-05-15 bị rò reference text, audio dài bất thường so với PyTorch Full |
| `vieneu_lora_ngoc_huyen` | Không load PEFT adapter thật, dùng `voices.json` + base GGUF nên dễ rò reference text và lỗi chunk sau |

### Lý do

Repo `pnnbao-ump/VieNeu-TTS-0.3B-lora-ngoc-huyen` là PEFT LoRA adapter. Cách dùng đúng về mặt kiến trúc là load adapter lên base model bằng PEFT/VieNeu `load_lora_adapter()`, không phải lấy `voices.json` như một preset giọng thường.

`voices.json` gốc trên Hugging Face có reference:

```text
Tác phẩm dự thi bảo đảm tính khoa học, tính đảng, tính chiến đấu, tính định hướng.
```

với 227 speech codes. Trước đây repo từng có workaround cắt local còn:

```text
Tác phẩm dự thi bảo đảm tính khoa học, tính đảng
```

Workaround này chỉ giảm triệu chứng rò reference text, nhưng có thể làm lệch cặp `codes + ref_text`, khiến tone/voice không ổn định.

### Quy tắc khi sửa tiếp

- Không tự động override `max_chunk_chars`, `temperature`, `top_k`, hoặc pause cho Ngọc Huyền. Đây là tham số người dùng tự chỉnh trong UI.
- Không quảng bá `vieneu_lora_ngoc_huyen` là model ổn định hoặc production.
- Không quảng bá `vieneu_ngoc_huyen_03b_q4_gguf` là model ổn định cho tới khi có bản quantize mới vượt smoke test.
- Nếu muốn hỗ trợ LoRA adapter thật, tạo nhánh/PR riêng và smoke test PEFT `load_lora_adapter()` trước khi đưa vào UI.
- Khi thêm model Ngọc Huyền mới, khai báo trong `config/models.yaml` trước; tránh hardcode trong worker/UI.
- Khi chỉnh docs VieNeu, cập nhật cả `docs/vieneu-engine.md` nếu quyết định ảnh hưởng tới mode/model list.

### File liên quan

- `config/models.yaml`
- `engines/vieneu_worker/modes/lora_mode.py`
- `src/omni_tts_core/model_catalog.py`
- `docs/vieneu-engine.md`

## 2026-05-15 — Model Picker Labels

### Quyết định

Danh sách chọn model trong Tkinter UI phải hiển thị nguồn/nhóm của model ngay trong label, để người dùng biết nhanh model nào là official, community, debug/legacy hoặc multilingual.

Format hiện tại:

```text
<Display name> [<Group badge>]
```

Ví dụ:

```text
OmniVoice Base (k2-fsa) [Official] [Multilingual]
OmniVoice Vietnamese (splendor1811) [Community] [VN Fine-tune]
OmniVoice Vietnamese (Hacht) [Community] [VN Test] [Test]
OmniVoice Vietnamese (hieuducle ckpt-4000) [Community] [Checkpoint]
VieNeu TTS v2 Standard [Official]
VieNeu TTS v2 Standard (CUDA) [Official] [Legacy CUDA] [Debug]
VieNeu Ngọc Huyền 0.3B PyTorch (Full) [Community]
VieNeu Ngọc Huyền 0.3B Q4 GGUF Legacy [Debug/Legacy]
```

Bên dưới combobox, UI hiển thị thêm dòng tóm tắt từ `catalog_info`: nguồn, nhóm, biến thể, base model, mức rủi ro, highlight, và `recommend_for`.

### Quy ước source/category

`catalog_info.origin` dùng để phân biệt nguồn model:

- `official`: repo chính chủ hoặc base chính thức.
- `community`: fine-tune, quantize, duplicate, hoặc checkpoint cộng đồng.
- `custom`: model người dùng tự thêm.

`catalog_info.category` dùng để phân nhóm vận hành/UI filter:

- `official-cpu`, `official-gpu`: tên category cũ, hiện chỉ hiển thị là `Official`; không dùng để quyết định CPU/GPU nữa.
- `community`: model cộng đồng có thể dùng thử hoặc dùng chính nếu đã ổn định.
- `experimental`: debug, legacy, checkpoint thô, hoặc model chưa đủ bằng chứng production.
- `support`: tokenizer/ASR/phụ trợ.

Thiết bị chạy phải đi qua `runtime_target` trong request/UI: `auto`, `cpu`, hoặc `cuda`. Không thêm model mới chỉ vì khác CPU/GPU; các dòng `_cuda` cũ chỉ giữ để tương thích và phải gắn `Legacy CUDA`/`Debug`.

Nếu model là community fine-tune dựa trên official base, không ghi là official; điền `origin: "community"` và `base_model` để người dùng thấy quan hệ nguồn.

### Quy tắc khi sửa tiếp

- Badge ưu tiên lấy từ `catalog_info.origin`; nếu không có `origin`, fallback về `catalog_info.category`.
- Không hardcode riêng từng model trong UI, trừ khi đó là fallback không có `catalog_info`.
- Model `experimental` phải hiện là `Debug/Legacy`, không gọi là production.
- Khi thêm model mới, luôn điền `catalog_info.category`, `origin`, `highlight`, `recommend_for`, và nếu là fine-tune/quantize thì điền thêm `base_model`/`source_repo`.
- Model test phải đặt `required: false`, dùng `risk: "test"` hoặc `risk: "checkpoint"`, và không đổi `generation.default_model_id`.
