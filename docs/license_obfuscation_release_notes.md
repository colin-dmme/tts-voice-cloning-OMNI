# License, Obfuscation, and Release Layout Notes

Ngày ghi chú: 2026-05-14

Tài liệu này giải thích vì sao source code được sắp xếp như hiện tại, phần nào dùng cho bản quyền, phần nào cần obfuscate, và phần nào tuyệt đối không gửi cho khách. Mục tiêu là để sau này quay lại dự án vẫn hiểu được quyết định ban đầu mà không phải lần mò lại toàn bộ lịch sử.

## Mục tiêu hiện tại

Dự án đang ở giai đoạn bán thử rất sớm, nên chưa cần license server hoặc Firebase ngay. Hướng hiện tại là:

- phát hành bản Windows portable;
- không gửi source Python gốc cho khách;
- dùng license local dạng `license.json` có chữ ký;
- giữ model và engine nặng bên ngoài app để cập nhật nhẹ hơn;
- dùng PyArmor Free/Trial trước nếu còn phù hợp;
- để ngỏ đường nâng cấp sang Firebase sau này.

## Ranh giới source code

Source chính được chia như sau:

```text
src/
  omni_tts_core/          # Logic TTS, model, job, audio, SRT
  omni_tts_license/       # Logic bản quyền độc lập
  omni_tts_ui_tkinter/    # Giao diện desktop
  omni_tts_ui_gradio/     # Giao diện web/dev
engines/
  vieneu_worker/          # Worker riêng cho VieNeu
  qwen_worker/            # Worker riêng cho Qwen
tools/
  license_admin/          # Tool riêng để chủ phần mềm cấp license
secrets/                  # Khóa riêng tư, không gửi khách, không commit
config/                   # Cấu hình public/runtime
models/                   # Model nặng
voices/                   # Profile giọng và mẫu giọng
outputs/                  # Kết quả sinh audio
```

Lý do chia như vậy:

- `omni_tts_license` đứng riêng để sau này có thể thay `LocalSignedLicenseProvider` bằng `FirebaseLicenseProvider` mà không phải sửa core TTS.
- UI bản quyền nằm ở `src/omni_tts_ui_tkinter/panels/license_panel.py` để `app.py` không phình to và để PyArmor Free ít gặp giới hạn big script hơn.
- `tools/license_admin` là công cụ nội bộ. Không được đưa vào bản gửi khách vì nó dùng private key để cấp license.
- `secrets` là vùng cấm gửi khách. Private key mất là mất khả năng kiểm soát việc cấp license.

## Thiết kế bản quyền hiện tại

Luồng hiện tại:

1. Khách mở tab `Bản quyền`.
2. Khách sao chép `Mã máy`.
3. Chủ phần mềm dùng tool trong `tools/license_admin` để tạo `license.json`.
4. Khách nhập `license.json` vào app.
5. App kiểm tra chữ ký bằng public key trong `config/license_public_key.pem`.

App chỉ chứa public key, không chứa private key. Vì vậy khách sửa `expires_at`, `email`, `plan`, `device_id`, hoặc `features` thì chữ ký sẽ sai và app từ chối license.

License được lưu ở máy khách, dự kiến:

```text
%LOCALAPPDATA%\OmniTTS\license.json
```

Nếu khách xóa file này thì app không được kích hoạt nữa. App vẫn mở giao diện, nhưng chặn thao tác sinh audio.

## Vì sao chưa dùng Firebase ngay

Firebase/Auth/Firestore phù hợp khi có nhiều khách hơn, cần quản lý từ xa, khóa/mở license online, hoặc gia hạn tự động. Ở giai đoạn hiện tại, doanh thu chưa đủ để bù công xây hệ thống online. Vì vậy local signed license là lựa chọn tạm thời hợp lý:

- không cần server;
- không cần Google login;
- không tốn chi phí vận hành;
- đủ ngăn sửa ngày hết hạn kiểu thủ công;
- có thể thay bằng Firebase sau này thông qua cùng interface provider.

## Quy tắc obfuscate

Chỉ obfuscate code do mình viết:

```text
src/omni_tts_core/
src/omni_tts_license/
src/omni_tts_ui_tkinter/
src/omni_tts_ui_gradio/      # nếu bản phát hành còn dùng Gradio
engines/vieneu_worker/synthesize.py
engines/qwen_worker/synthesize.py
```

Không obfuscate:

```text
.venv/
engines/*/.venv/
models/
.hf_cache/
outputs/
voices/
config/*.yaml
config/license_public_key.pem
third-party packages
```

Lý do:

- Obfuscate `.venv` hoặc Torch/Numpy/Gradio là không cần thiết, chậm, dễ lỗi và không bảo vệ thêm logic riêng.
- Model là asset nặng, để ngoài để khách không phải tải lại mỗi lần app cập nhật.
- Config YAML nên để ngoài để sửa cấu hình phát hành mà không build lại app.
- Public key được phép gửi khách; private key thì không.

## PyArmor Free hiện tại

Đã thử PyArmor trial/free trên source ngày 2026-05-14:

- toàn bộ `src` obfuscate thành công;
- `engines/vieneu_worker/synthesize.py` obfuscate thành công;
- `engines/qwen_worker/synthesize.py` obfuscate thành công;
- file lớn nhất hiện tại là `src/omni_tts_ui_tkinter/app.py`, khoảng 25 KB / 540 dòng, vẫn qua được trial/free.

Để tiếp tục dùng PyArmor Free lâu hơn:

- không để `app.py` phình quá lớn;
- tách các tab UI thành panel riêng;
- không nhét dữ liệu dài, prompt dài hoặc template dài vào code;
- giữ mỗi worker nhỏ và độc lập;
- chạy obfuscate từng worker riêng nếu cần, vì các worker đều có file tên `synthesize.py`.

## Layout bản gửi khách đề xuất

Khi đóng gói portable, bản gửi khách nên có dạng:

```text
OmniTTS/
  app/
    OmniTTS.exe
    pyarmor_runtime_000000/
    config/
      app.yaml
      models.yaml
      license_public_key.pem
  engines/
    vieneu_worker/
      synthesize.py        # bản obfuscated hoặc worker đã build
    qwen_worker/
      synthesize.py        # bản obfuscated hoặc worker đã build
  models/
  voices/
  outputs/
  Run OmniTTS.bat
```

Không gửi:

```text
src/
tools/license_admin/
secrets/
.venv/
uv.lock nếu không cần cài lại môi trường
pyproject.toml nếu không cần dev
```

## Quy tắc update

- Sửa UI/core/license: build lại `app/`.
- Sửa worker engine: gửi lại worker tương ứng trong `engines/`.
- Sửa model: gửi riêng `models/`.
- Sửa cấu hình nhỏ: gửi lại file trong `config/`.

Mục tiêu là tránh bắt khách tải lại model nhiều GB khi chỉ thay đổi một nút hoặc một đoạn logic.

## Đường nâng cấp sau này

Khi có đủ khách để cần quản lý online:

1. Thêm `src/omni_tts_license/firebase_provider.py`.
2. Giữ nguyên các hàm public như `get_status`, `install_license`, `current_device_id`, `is_feature_enabled`.
3. UI chỉ gọi controller nên không cần viết lại tab bản quyền.
4. Có thể giữ local signed license làm fallback offline hoặc xóa hẳn nếu không cần.

Điểm quan trọng: mọi thay đổi license nên đi qua provider, không gọi Firebase trực tiếp từ core TTS hoặc UI tạo audio.
