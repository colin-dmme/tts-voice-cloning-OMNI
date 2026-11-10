# Pha 1. Hồ sơ năng lực nghỉ và bộ phân xử trong Core

Trạng thái: **đã làm phần lõi (10/11/2026)**. Code ở `src/omni_tts_core/rhythm/` (`layers.py`, `capabilities.py`, `resolver.py`); test `tests/test_rhythm_resolver.py` có 113 ca. `NarrativePacingOptions` đã có thêm `scope` và `model_switches`.

Khác so với thiết kế ban đầu:
- Hồ sơ nằm trong `rhythm/capabilities.py` (`PROFILES` theo provider_id, ghi đè theo model qua `ModelOverride`), không thêm trường vào `ProviderDescriptor`. Lý do: tránh import vòng và không đụng file registry dùng chung.
- Có thêm trạng thái `off` (TẮT) cho tầng người dùng tự tắt, ví dụ tầng chuyển mục hoặc nhạc. Trạng thái này khác KHÔNG ÁP DỤNG.
- Ở phạm vi `pacing_only`, các cơ chế `library_param` / `app_split` không được chọn vì mục Ngắt nghỉ cũ vẫn điều khiển. Switch Kokoro chỉ có tác dụng ở phạm vi `full`.

Ban đầu: chưa làm. Không phụ thuộc giao diện. Làm theo mẫu đã có: `chunk_join.py` (`resolve_chunk_join_policy` + `describe_chunk_join_policy`) và `ui_presenters/control_policy.py` (`ControlState`).

## File

- **Mới** `src/omni_tts_core/rhythm/pause_capabilities.py`: kiểu dữ liệu và hồ sơ năng lực.
- **Mới** `src/omni_tts_core/rhythm/resolver.py`: `resolve_rhythm_plan`, `describe_layer`, `diff_rhythm_plans`.
- **Sửa** `src/omni_tts_core/provider_registry.py`: thêm `pause_profile` vào `ProviderDescriptor` (mặc định `None` = toàn bộ `app_stretch`).
- **Mới** `tests/test_rhythm_resolver.py`.

## Kiểu dữ liệu

```python
Layer = Literal["comma", "clause", "ellipsis", "sentence_end", "question_end",
                "short_sentence", "connector", "paragraph", "question", "emphasis",
                "subtopic", "section", "music_theme", "music_short", "music_long"]
Mechanism = Literal["native_token", "library_param", "library_fixed",
                    "app_split", "app_stretch", "none"]

@dataclass(frozen=True)
class LayerCapability:
    mechanisms: tuple[Mechanism, ...]         # theo thứ tự ưu tiên của model này
    param: str | None = None                  # "sentence_pause", "silence_p"...
    semantics: Literal["total", "added"] | None = None
    fixed_ms: int | None = None               # library_fixed: mức model tự đặt
    limit: str | None = None                  # lý do GIỚI HẠN, viết cho người dùng
    limit_max_ms: int | None = None           # ví dụ OmniVoice ~1000
    requires: str | None = None               # "authored_tokens", "postprocess_off"...

@dataclass(frozen=True)
class RhythmSwitch:
    # Tùy chọn riêng của model, hiện trong mục Nhịp đọc chỉ khi model đó đang chọn.
    key: str                                  # "kokoro_pause_mode", "omnivoice_keep_long_silence"
    label: str
    choices: tuple[tuple[str, str], ...]      # (giá trị, nhãn); bool = (("on",..),("off",..))
    default: str
    help: str
    # Mỗi giá trị đổi hồ sơ tầng nào: {"app_split": {"comma": LayerCapability(...)}}
    effects: Mapping[str, Mapping[Layer, LayerCapability]] = {}

@dataclass(frozen=True)
class PauseProfile:
    layers: Mapping[Layer, LayerCapability]
    model_overrides: Mapping[str, Mapping[Layer, LayerCapability]] = {}
    # VieNeu v2/v3 và ZeroTTS official/GGUF dùng chung provider_id nên cần ghi đè theo model_id.
    switches: tuple[RhythmSwitch, ...] = ()
    locked_settings: tuple[str, ...] = ()     # setting "Tinh chỉnh riêng" trùng tầng, ví dụ segment_gap_seconds

@dataclass(frozen=True)
class LayerResolution:
    layer: Layer
    state: Literal["model", "app", "model_app_topup", "limited", "not_applicable"]
    mechanism: Mechanism
    value_ms: tuple[int, int]                 # (min, max) người dùng đặt, không đổi theo model
    effective_note: str                       # 1 dòng: làm bằng cách nào
    reason: str = ""                          # vì sao GIỚI HẠN / KHÔNG ÁP DỤNG

@dataclass(frozen=True)
class RhythmPlan:
    provider_label: str
    model_label: str
    layers: tuple[LayerResolution, ...]
    locked_controls: tuple[str, ...]          # khóa mục cũ, ví dụ "punctuation_pause_enabled"
    switches: tuple[tuple[RhythmSwitch, str], ...]  # tùy chọn riêng của model + giá trị đang dùng
    summary: str                              # "OmniVoice: 9 tầng APP, 3 GIỚI HẠN, 0 KHÔNG ÁP DỤNG"
```

## Bộ phân xử

`resolve_rhythm_plan(options, descriptor, spec, *, output_mode, source_kind, chunk_join, device_kind, text_has_tokens=False)`

1. Nhịp đọc tắt: trả `RhythmPlan` rỗng, `locked_controls=()`. Mọi thứ như cũ.
2. Ngữ cảnh loại tầng:
   - `output_mode == "split"`: các tầng giữa đoạn và nhạc là `not_applicable` (lý do: "Xuất tách từng đoạn, không có chỗ nối giữa đoạn").
   - `source_kind == "epub"`: `section`, `music_*` là `not_applicable` (lý do: "Chương, cảnh và nhạc chương do mục EPUB quản lý"). Các tầng trong câu, cuối câu, `connector`…`subtopic` áp cho đoạn văn trong chương.
3. Áp `options.model_switches` (giá trị người dùng chọn, thiếu thì `default`) để thay `LayerCapability` theo `effects`.
4. Với mỗi tầng còn lại, đi theo `mechanisms` của model, chọn cách đầu tiên dùng được:
   - `native_token` cần `text_has_tokens` (Higgs có văn bản đã soạn).
   - `library_param` cần worker hỗ trợ thiết bị hiện tại. Remote chưa nhận tham số thì bỏ qua.
   - `app_split` cần `"punctuation_pauses" in descriptor.controls`.
   - `app_stretch` luôn dùng được với job ghép.
5. Gắn trạng thái:
   - `library_fixed` đi trước → `model_app_topup`. Lưu `fixed_ms` để giải thích.
   - Có `limit`, và giá trị Max người dùng vượt `limit_max_ms` hoặc limit luôn đúng → `limited`.
   - `chunk_join` là crossfade/nối thẳng → tầng trong câu `limited` (lý do: điểm nối không có lặng).
6. `locked_controls`: mục cũ trùng tầng (`punctuation_pause_*`, `paragraph_pause_*`) cộng `profile.locked_settings`. Không viết cứng theo provider_id.

## Tùy chọn riêng theo model (đã chốt)

| Model | `RhythmSwitch` | Giá trị | Mặc định | Ảnh hưởng |
|---|---|---|---|---|
| Kokoro | `kokoro_pause_mode` "Cách ngắt nghỉ của Kokoro" | `library` (Tham số model) / `app_split` (App cắt câu) | `library` | `library`: tầng trong câu/cuối câu `library_param`, nhãn MODEL, một giá trị = điểm giữa Min–Max (ghi rõ "không dao động"). `app_split`: nhãn APP, có dao động |
| OmniVoice | `omnivoice_keep_long_silence` "Giữ khoảng lặng dài" | bật / tắt | bật | bật: `postprocess_output=False`, tầng trong câu/cuối câu `app_stretch` không limit; app cắt lặng >2s. tắt: thư viện rút lặng, gắn limit 1000ms → GIỚI HẠN |

`diff_rhythm_plans(old, new) -> list[str]`: các dòng "Dấu phẩy, cuối câu: MODEL → GIỚI HẠN (lý do)". Dùng cho thông báo khi đổi model.

## Hồ sơ mẫu (sửa theo số đo pha 0)

| Model | Trong câu | Cuối câu | Giữa đoạn / nhạc | Setting provider bị khóa |
|---|---|---|---|---|
| Kokoro | `library_param` clause_pause (total) hoặc `app_split`, theo `kokoro_pause_mode` | `library_param` sentence_pause (total) hoặc `app_split` | `app_stretch` | — |
| Piper | `app_split` | `app_split` | `app_stretch` | — |
| Supertonic | `app_split` | `app_split` | `app_stretch` | (silence_duration giữ 0, không lộ ra) |
| ZeroTTS | `library_fixed` + `app_stretch`; `;` có limit "thư viện đổi `;` thành `,`" | `library_fixed` + `app_stretch` | `app_stretch` | `segment_gap_seconds` |
| VieNeu v3 | `app_stretch` (đo: không có mức cố định trong câu) | `library_fixed` 500 + stretch | `app_stretch` | — |
| VieNeu v2 | `app_stretch` | `app_stretch` | `app_stretch` | `silence_p` nếu lộ ra |
| OmniVoice | `app_stretch`; limit 1000 chỉ khi tắt `omnivoice_keep_long_silence` | như trong câu | `app_stretch` | — |
| F5, Qwen, Valtec | `app_stretch` | `app_stretch` | `app_stretch` | — |
| Chatterbox | `app_stretch`; `…` `:` limit "thư viện đổi thành dấu phẩy" | `app_stretch` | `app_stretch` | — |
| Higgs | `app_stretch` | `native_token` (`pause`) khi có token, không thì `app_stretch` | `native_token` (`long_pause`) cho đoạn, không thì `app_stretch` | — |

## Tiêu chí

- [ ] Test tham số hóa: mọi provider trong registry × {merged, split, epub} × {Nhịp đọc bật/tắt} × mọi giá trị switch. Không tầng nào có hai bên đảm nhận.
- [ ] Switch của model khác không ảnh hưởng: giá trị `kokoro_pause_mode` còn lưu khi đang chọn ZeroTTS, không hiện và không tác động.
- [ ] Provider mới không khai báo `pause_profile` vẫn chạy: mọi tầng là `app_stretch`, nhãn APP.
- [ ] Không có nhánh `if provider_id == ...` trong resolver; mọi khác biệt nằm trong hồ sơ.
- [ ] `describe_layer` trả câu tiếng Việt, đã duyệt chữ, giống `describe_chunk_join_policy`.
