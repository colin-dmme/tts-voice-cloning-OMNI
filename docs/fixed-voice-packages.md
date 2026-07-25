# Giọng cố định và package model

## Mục tiêu

OMNI tách rõ hai nguồn giọng:

- **Giọng cố định**: model/voice đã huấn luyện sẵn, không đọc Profile giọng và không dùng audio mẫu.
- **Clone từ Profile**: dùng audio mẫu đã lưu; preset giọng cố định bị bỏ qua.

Quy tắc này nằm trong `voice_input` của `config/models.yaml` hoặc
`config/piper_voices.yaml` và được Core biến thành
`GenerationFormDescriptor`. Tkinter và PySide6 cùng đọc `AppController` và
`model_groups`, không GUI nào tự đoán provider hoặc hardcode tên giọng.

## Model đã thêm

### Piper ONNX

Catalog hiện có **33 model Piper**:

- **25 model NGHI-TTS:** Adam 1, Ban Mai, Nữ trầm tĩnh 3688, Chiếu Thành,
  Nam trầm 3909, Duy Oryx 3175, Lạc Phi, Mai Phương, Mạnh Dũng, Minh Khang,
  Minh Quang, Minh Thu, Mỹ Tâm v1/2794, Ngọc Huyền v1/NEW, Ngọc Ngạn 3701,
  Phương Trang, Tài An 2/4, Thanh Phương 2, Thiện Tâm, Trấn Thành 3870,
  Việt Thảo 3886 và Yan NEW.
- **3 model Piper official:** VAIS1000 medium, 25hours single low và VIVOS x-low.
- **5 model độc lập:** Pretrained VI nữ, Mai Linh 250626 và ba giọng nam miền Nam
  từ `jimmyvu/viPiper`.

Nguồn gồm `sannht/vi_voice`, `doof-ferb/nghitts-copy`,
`beyoru/MaiLinh-TTS-CoreML`, `jimmyvu/viPiper`,
`datasetsANDmodels/vietnamese-tts` và ba repository Piper official của
`speaches-ai`. Mỗi package chỉ tải đúng model và config cần dùng (đa số khoảng
64 MB; VIVOS x-low khoảng 28 MB), lưu tại:

```text
models/piper/<source>/<voice-package>/
```

Piper worker chạy độc lập tại `engines/piper_worker/.venv`. Tất cả giọng dùng chung
một process worker để tránh mở một process cho mỗi model. Worker giữ tối đa ba giọng
được dùng gần nhất, vì vậy A/B qua lại nhanh mà RAM không tăng vô hạn.

VIVOS x-low là model multi-speaker. Catalog ánh xạ đủ 65 `speaker_id`; khi chọn
VIVOS, cả Tkinter và PySide6 hiển thị danh sách speaker cố định thay vì dùng nhầm
một speaker mặc định.

### Hai bản Ngọc Huyền

- `piper_ngoc_huyen`: bản `ngochuyen.onnx` v1 từ `sannht/vi_voice`.
- `piper_ngoc_huyen_new`: bản `ngochuyennew.onnx` v2 từ
  `doof-ferb/nghitts-copy`.

Hai file có SHA-256 khác nhau, do đó đây là hai weights thật sự khác nhau chứ
không phải hai tên trỏ tới cùng model. Chất lượng được để ở trạng thái **Test**;
không tự gán bản nào “tốt hơn” trước khi nghe cùng văn bản, cùng tốc độ.

### Adam 1

`piper_adam_1` là file `adam1.onnx` tiếng Việt trong bộ NGHI-TTS. File từ
Google Drive chính thức, `doof-ferb/nghitts-copy`, `raikiri1498/nghitts` và
`phongluong197/ttsmodels` đều có cùng kích thước 63.531.379 byte và SHA-256
`90e73d171447825fa8442fea8bf39c54bcfb206958f05170361e0fa3ba5c48eb`.
Vì vậy các link này là mirror của cùng một voice, không được đưa vào catalog
thành nhiều “phiên bản Adam” giả.

Tên “Adam viral” cũng được nhiều dịch vụ dùng cho giọng ElevenLabs Adam. Entry
này chỉ khẳng định artifact Piper/NGHI-TTS có tên Adam; không khẳng định đó là
weights gốc của ElevenLabs. Model vẫn ở nhãn **Test** để người dùng nghe A/B
trước khi chọn cho nội dung dài.

### VieNeu v3 Turbo

`vieneu_v3_turbo` cung cấp 14 preset 48 kHz và chế độ clone Profile riêng biệt.
App chỉ tải các artifact cần cho PyTorch GPU và ONNX INT8 CPU, cộng MOSS tokenizer,
thay vì tải mọi biến thể của repo.

Trên máy GTX 1080 Ti đã đo, `Auto` ưu tiên ONNX INT8 CPU vì nhanh hơn PyTorch GPU
cho model v3. Người dùng vẫn có thể chọn CUDA thủ công để A/B.

## Thêm một giọng Piper mới

Không sửa từng GUI. Chỉ thêm một entry mới vào `tts_models` trong
`config/piper_voices.yaml`:

```yaml
piper_example:
  display_name: "Piper Example"
  provider: "piper"
  model_type: "tts"
  local_path: "models/piper/source/example"
  hf_repo: "owner/repository"
  language_priority: "vi"
  voice_input:
    modes: ["fixed"]
    default_mode: "fixed"
  capabilities:
    supported_languages: ["vi"]
    supports_voice_profile: false
    supports_reference_text: false
    supports_speed: true
  runtime:
    model_file: "path/example.onnx"
    config_file: "path/example.onnx.json"
    download_allow_patterns:
      - "path/example.onnx"
      - "path/example.onnx.json"
```

Sau khi khởi động lại, model tự xuất hiện trong danh sách model và Quản lý model.

## Tải, mở và gỡ

- **Tải model đang chọn**: tải đúng artifact đã khai báo.
- **Mở nơi lưu**: mở folder package hoặc HF cache tương ứng.
- **Piper:** tải bằng HF cache tạm, sau đó chỉ giữ package tự chứa trong
  `models/piper`. Khi người dùng xác nhận gỡ, package bị xóa thật để giải phóng
  dung lượng và có thể tải lại bình thường.
- **Provider khác:** vẫn dùng chính sách `.trash`/HF cache an toàn hiện có.
- Worker dùng chung không bị gỡ cùng một voice package.
