# Portable Distribution Notes

Ngày ghi chú: 2026-05-14

Tên bản phát hành cho khách: `colinttslocal`.

## Mục tiêu

Bản portable cho Windows cần đáp ứng:

- người dùng không cần cài Python;
- người dùng chỉ bấm `colinttslocal.bat`;
- source Python gốc không được gửi khách;
- code trong `app/src` và worker đã được PyArmor obfuscate;
- license vẫn dùng local signed license;
- model và engine nặng có thể copy riêng khi cần.

## Lệnh build

Build skeleton để test app, license, UI:

```powershell
powershell -ExecutionPolicy Bypass -File packaging\build_portable.ps1
```

Build bản đầy đủ hơn để gửi khách, nếu ổ đĩa còn đủ dung lượng:

```powershell
powershell -ExecutionPolicy Bypass -File packaging\build_portable.ps1 -IncludeModels -IncludeVoices -IncludeEngineEnvs
```

Vị trí output mặc định:

```text
dist_portable/colinttslocal/
```

File khách bấm chạy:

```text
dist_portable/colinttslocal/colinttslocal.bat
```

## Layout portable

```text
colinttslocal/
  colinttslocal.bat
  README_FIRST.txt
  app/
    src/                         # source đã obfuscate
    pyarmor_runtime_000000/
  config/
    app.yaml
    models.yaml
    license_public_key.pem
  runtime/
    python/                      # Python runtime + site-packages
  engines/
    vieneu_worker/
      synthesize.py              # obfuscated
      pyarmor_runtime_000000/
      site-packages/             # chỉ có khi build -IncludeEngineEnvs
    qwen_worker/
      synthesize.py              # obfuscated
      pyarmor_runtime_000000/
      site-packages/             # chỉ có khi build -IncludeEngineEnvs
  models/                        # chỉ đầy đủ khi build -IncludeModels
  voices/                        # chỉ đầy đủ khi build -IncludeVoices
  outputs/
  .hf_cache/
```

## Không gửi khách

Không đưa các thư mục/file này vào bản gửi khách:

```text
src/
tools/license_admin/
secrets/
.venv/
build/
config/license_private_key.pem
```

## Lưu ý dung lượng

Bản skeleton hiện đã khoảng 5 GB vì chứa Python runtime và thư viện chính. Bản đầy đủ có thể rất lớn vì:

- `models/` khoảng 13 GB;
- worker env trong `engines/` khoảng 5-6 GB;
- runtime chính khoảng 5 GB.

Nếu ổ C không đủ, build ra ổ khác:

```powershell
powershell -ExecutionPolicy Bypass -File packaging\build_portable.ps1 -OutputRoot "D:\portable-build" -IncludeModels -IncludeVoices -IncludeEngineEnvs
```

## License

Portable chỉ có public key:

```text
config/license_public_key.pem
```

Private key vẫn nằm ngoài bản gửi khách:

```text
secrets/license_private_key.pem
```

Khách mở tab `Bản quyền`, sao chép mã máy, gửi lại cho chủ phần mềm. Chủ phần mềm tạo `license.json` bằng tool nội bộ rồi gửi khách nhập trong app.
