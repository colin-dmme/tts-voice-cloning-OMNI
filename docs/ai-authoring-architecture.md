# AI authoring architecture

## Mục tiêu

AI authoring không thuộc một GUI, một AI model hay một TTS provider cụ thể.
Luồng chuẩn:

```text
source text + AuthoringBrief + VoiceContext
  -> AI authoring provider
  -> provider-neutral PerformancePlan
  -> TTS authoring dialect adapter
  -> provider markup/request controls
  -> provider validator
```

Gemini là AI provider đầu tiên. Higgs Script là authoring dialect đầu tiên.
Hai registry độc lập:

- `authoring/provider_registry.py`: đăng ký model phân tích nội dung.
- `provider_registry.py`: provider TTS khai báo `authoring_dialect` và
  `authoring_features`.

GUI chỉ đọc `AuthoringPolicy`, thu thập form và gọi `AppController`.

## Thêm một TTS provider có điều khiển cách diễn

1. Tạo dialect adapter thực thi contract trong
   `authoring/dialects/base.py`.
2. Adapter nhận `source_text`, `PerformancePlan`, `AuthoringBrief`; trả văn bản
   hoặc request representation đã render cùng cảnh báo.
3. Đăng ký adapter trong `AuthoringService`.
4. Khai báo `authoring_dialect` và `authoring_features` trong
   `ProviderDescriptor`.
5. Thêm validator riêng của dialect.

Không thêm `if provider_id == ...` vào StudioPage hoặc dialog.

Provider dùng SSML có thể ánh xạ `pace`, `pitch`, `pause_after` sang
`<prosody>`/`<break>`. Provider dùng request parameter có thể ánh xạ cùng plan
sang JSON thay vì inline token.

## Thêm một AI provider

1. Viết client có `call_json()`, `test_connection()` và `list_models()`.
2. Tạo `AiProviderDescriptor` trong `authoring/provider_registry.py`.
3. Khai báo danh sách model mặc định và capability model.
4. Nếu provider có quy tắc retry đặc biệt, cung cấp rotating provider tương
   ứng sau interface của core.

Trang AI/API lấy provider/model từ controller nên không cần sửa logic form khi
registry có provider mới.

## Voice Context

Thứ tự ưu tiên:

```text
override lần chạy
  > mô tả đã nhớ theo profile/voice ID
  > metadata VoiceProfile
  > mặc định trung tính
```

Giới tính/chất giọng chỉ là ngữ cảnh cho đạo diễn. Dialect không được dùng
pitch để thay thế việc chọn đúng source voice.

## Persistence

Các file sau là runtime cục bộ và không commit:

- `config/authoring_ai.json`
- `config/authoring_ai_keys.json`
- `config/authoring_state.json`
- `config/authoring_sessions.json`

Candidate lưu snapshot của brief, voice context, AI provider/model, prompt
version, plan, kết quả render và validator messages. Regenerate không ghi đè
candidate cũ.

## Invariants

- Renderer không được sửa spoken text của nguồn.
- Chỉ dialect adapter sinh cú pháp provider.
- Chỉ core quyết định capability/visibility.
- API key value không xuất hiện trong log hoặc UI table.
- Một lỗi model/config không được làm inactive API key tốt.
- Provider không hỗ trợ authoring tiếp tục dùng pipeline cũ không đổi.
