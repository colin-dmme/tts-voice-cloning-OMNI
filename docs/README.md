# Tài liệu dự án — Colin TTS Local

## Index

| File | Nội dung | Cập nhật |
|---|---|---|
| [engine-architecture.md](engine-architecture.md) | Sơ đồ kiến trúc toàn bộ engine system, provider mapping, YAML model registry, capabilities system | 2026-05-15 |
| [vieneu-engine.md](vieneu-engine.md) | Chi tiết VieNeu integration: 4 modes, 16 models, GPU setup, cách thêm model/mode, known issues, roadmap | 2026-05-15 |
| [voice-profile-optimization.md](voice-profile-optimization.md) | Hiện trạng và kế hoạch dài hạn tối ưu Profile giọng cho app đa engine | 2026-05-15 |
| [runtime-device-policy.md](runtime-device-policy.md) | Quy ước Auto/CPU/GPU CUDA cho app đa engine, detector/policy/runtime target | 2026-05-16 |
| [engineering-decisions.md](engineering-decisions.md) | Source of truth cho các quyết định kỹ thuật cần giữ nhất quán khi dùng Codex/Cursor/Claude/tự code | 2026-05-15 |
| [license_obfuscation_release_notes.md](license_obfuscation_release_notes.md) | License & obfuscation release notes | — |
| [portable_distribution_notes.md](portable_distribution_notes.md) | Portable distribution notes | — |

## Quick reference

**Thêm model VieNeu mới** → chỉ sửa `config/models.yaml`, không cần code
**Thêm model OmniVoice fine-tune/test** → thêm row `provider: omnivoice`, điền `catalog_info.origin/base_model/risk`, giữ `required: false` nếu chưa production
**Tối ưu Profile giọng / clone voice** → xem `voice-profile-optimization.md` trước khi sửa schema, UI hoặc engine cache
**Thêm mode worker mới** → tạo `engines/vieneu_worker/modes/newmode.py` + 1 dòng dispatcher
**Bật GPU** → trong Quản lý model chọn model rồi bấm `Cài tăng tốc GPU cho model đang chọn`, sau đó chọn `Thiết bị xử lý = GPU CUDA`
**Hiểu data flow** → xem `engine-architecture.md` section 4
**Xem tất cả VieNeu models** → xem `vieneu-engine.md` section 5
**Xem quyết định cần giữ nhất quán** → đọc `engineering-decisions.md` trước khi sửa model/runtime
