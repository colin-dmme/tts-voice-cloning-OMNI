# Tối ưu Voice Profile cho app đa engine

Cập nhật: 2026-05-15

Tài liệu này là nơi thống nhất để đánh giá và phát triển hệ thống Profile giọng trong Colin TTS Local khi app hỗ trợ nhiều engine: OmniVoice, VieNeu, Qwen3-TTS và Valtec.

## Mục tiêu

Hiện tại app xem một Profile giọng như một cặp `audio + transcript`. Cách này đủ để chạy thử nhanh, nhưng chưa tối ưu cho app đa engine vì mỗi model có cách encode giọng mẫu, yêu cầu transcript, thời lượng mẫu và cache nội bộ khác nhau.

Mục tiêu dài hạn:

- Giữ UI đơn giản cho người dùng: chọn một Profile giọng là đủ.
- Bên dưới app tự chuẩn hóa audio và chọn cách dùng phù hợp theo từng engine.
- Tăng độ ổn định tone giữa các chunk.
- Giảm encode lại reference audio nhiều lần.
- Cho phép một profile có nhiều sample theo phong cách đọc khác nhau.
- Không phá profile cũ và không ảnh hưởng model/runtime đang chạy ổn.

## Hiện trạng codebase

### VoiceProfile hiện tại

Schema hiện tại nằm ở `src/omni_tts_shared/schemas.py`:

```python
class VoiceProfile(BaseModel):
    profile_id: str
    name: str
    audio_path: Path
    transcript: str = ""
    language: LanguageCode = "vi"
    project: str = ""
    notes: str = ""
    created_at: str = ""
    updated_at: str = ""
```

Profile chỉ chứa:

- 1 file audio mẫu.
- 1 transcript.
- 1 language.
- project/notes.

Lưu profile do `src/omni_tts_core/voice_profiles.py` xử lý. File audio được copy vào `voices/samples/`, metadata JSON lưu trong `voices/profiles/`.

### Cách profile đi vào pipeline

Trong `src/omni_tts_core/service.py`, `_apply_voice_profile()` làm việc rất trực tiếp:

```python
update = {
    "reference_audio_path": profile.audio_path,
    "reference_text": profile.transcript or request.reference_text,
    "speaker_id": None,
}
```

Sau đó mỗi chunk được tạo thành `TtsEngineRequest` với cùng `reference_audio_path` và `reference_text`.

Điểm mạnh:

- Đơn giản, dễ hiểu.
- Mọi engine có thể nhận cùng một khái niệm `ref_audio/ref_text`.
- Tương thích ngược tốt.

Điểm yếu:

- Không có phân tích chất lượng audio mẫu.
- Không có chuẩn hóa chung trước khi đưa vào engine.
- Không có khuyến nghị thời lượng theo model.
- Không có cache theo engine/profile/model.
- Không phân biệt engine nào cần transcript, engine nào không dùng transcript.
- Một profile không thể chứa nhiều sample cho nhiều style.

## Khác biệt giữa các engine

| Engine | Cách đang dùng trong app | Transcript | Thời lượng mẫu nên hướng tới | Điểm cần tối ưu |
|---|---|---:|---:|---|
| OmniVoice | `model.generate(ref_audio, ref_text)` trong `omnivoice_engine.py` | Nên có | 3-10 giây | Cache `voice_clone_prompt`; dùng prepared WAV ổn định |
| VieNeu Standard/GGUF | Profile được encode riêng thành `ref_codes.npy`, sau đó generate bằng `ref_codes + ref_text` | Có, nếu dùng clone giọng | 3-5 giây | Cache `ref_codes` theo profile/sample/model; không truyền trực tiếp `ref_audio` vào GGUF để tránh crash native trên Windows |
| VieNeu PyTorch | `tts.infer(ref_audio, ref_text)` trong worker nếu model hỗ trợ | Nên có khi clone | 3-5 giây | Encode `ref_codes` một lần cho batch/chunks |
| VieNeu Turbo | `tts.encode_reference(ref_audio)` rồi `tts.infer(voice=...)` | Không dùng trực tiếp | 3-5 giây | Đã encode một lần trong batch, cần chuẩn hóa audio |
| Qwen3-TTS | `generate_voice_clone(ref_audio, ref_text)` trong worker | Nên bắt buộc trong app | Khoảng 3-10 giây để test an toàn | Cache `voice_clone_prompt`; batch nhiều câu |
| Valtec | `ZeroShotTTS.clone_voice(reference_audio)` | Không dùng | 3-10 giây | Chuẩn hóa 24k mono; cache embedding nếu API cho phép |

Ghi chú:

- VieNeu docs khuyến nghị reference audio lý tưởng 3-5 giây.
- Với trạng thái app ngày 2026-05-16, VieNeu Standard/GGUF đã dùng luồng pre-encode: audio mẫu được encode trong process riêng bằng NeuCodec Standard/Distill, cache thành `ref_codes.npy`, rồi worker GGUF chỉ nhận `ref_codes`. Cách này tránh lỗi crash native từng gặp khi gọi trực tiếp `tts.infer(ref_audio=...)` trong cùng process GGUF trên Windows.
- Valtec local README ghi rõ zero-shot cloning tốt nhất với 3-10 giây, sạch, một người nói, cảm xúc trung tính.
- OmniVoice và Qwen đều có API tạo voice prompt/cache prompt, nhưng app hiện chưa dùng.

## Vấn đề thực tế cần giải quyết

### 1. Một sample không tối ưu cho mọi engine

Ví dụ cùng một file 10-12 giây:

- Có thể phù hợp OmniVoice hoặc Valtec.
- Có thể hơi dài cho VieNeu, đặc biệt khi muốn tone ổn định và ref_text khớp chặt.
- Với Qwen, transcript càng khớp càng quan trọng.

Do đó profile không nên chỉ là một file duy nhất. Profile nên là hồ sơ giọng, bên trong có nhiều sample.

### 2. Audio gốc chưa được chuẩn hóa

Hiện file người dùng chọn có thể là MP3/WAV/FLAC, sample rate 24k/44.1k, mono/stereo, volume khác nhau. Một số worker tự xử lý, ví dụ Valtec resample về 24k mono, nhưng các engine khác chưa có lớp chuẩn hóa chung.

Điều này dễ gây:

- Chất lượng clone không đều giữa engine.
- Lệch tone giữa các lần generate.
- Lỗi codec/encoder khó đoán.

### 3. Encode reference lặp lại

Khi text bị chia nhiều chunk, nhiều engine đang nhận lại cùng `ref_audio` cho từng chunk.

Hiện VieNeu Turbo đã tối ưu batch bằng cách `encode_reference()` một lần trong `engines/vieneu_worker/modes/turbo.py`.

VieNeu Standard/GGUF đã có luồng riêng: `engines/vieneu_worker/encode_reference.py` encode audio mẫu thành `ref_codes.npy` trong process tách biệt, `src/omni_tts_core/engines/vieneu_engine.py` cache file này theo profile/sample/model, rồi `engines/vieneu_worker/modes/standard.py` truyền `ref_codes` vào `tts.infer(...)`. Nếu người dùng chọn file audio mẫu thủ công thay vì profile đã lưu, app vẫn pre-encode vào thư mục tạm của job. Cách này giúp tone giữa chunk ổn định hơn và tránh lỗi native crash trên Windows.

VieNeu PyTorch Full vẫn có thể tiếp tục dùng `ref_audio/ref_text`; dài hạn nên dùng chung cache `ref_codes` nếu API ổn định trên tất cả biến thể.

OmniVoice và Qwen cũng có API tạo voice clone prompt, nhưng app chưa cache.

### 4. Metadata profile chưa đủ giàu

`VoiceProfile.language` hỗ trợ schema nhiều language, nhưng khi lưu trong `voice_profiles.py` hiện chỉ giữ `vi/en`. Điều này không khớp với Qwen3-TTS vì Qwen hỗ trợ nhiều ngôn ngữ hơn.

Profile cũng chưa có:

- duration.
- sample rate.
- channel count.
- prepared path.
- quality score.
- style/role của sample.
- transcript confidence hoặc trạng thái transcript.

## Kiến trúc đề xuất

### Tư duy mới

```text
Voice Profile = hồ sơ giọng gốc người dùng chọn
Voice Sample = một mẫu audio cụ thể trong profile
Prepared Sample = bản audio đã chuẩn hóa cho engine dùng
Engine Profile Asset = cache riêng theo engine/model/sample
Engine Policy = luật chọn sample, validate và cache cho từng engine
```

Người dùng vẫn chọn một profile trong UI. App tự quyết định sample/asset phù hợp nhất theo model đang chọn.

### VoiceProfile v2

Đề xuất schema tương lai:

```yaml
profile_id: ngoc-huyen
schema_version: 2
name: Ngọc Huyền
default_sample_id: neutral_5s
language: vi
project: audiobook
notes: ""
samples:
  - sample_id: neutral_5s
    role: neutral
    source_path: voices/samples/ngoc-huyen-neutral.wav
    prepared_path: voices/prepared/ngoc-huyen/neutral_5s/reference_24k_mono.wav
    transcript: "..."
    language: vi
    duration_seconds: 5.2
    sample_rate: 24000
    channels: 1
    quality_score: 92
    warnings: []
  - sample_id: storytelling_8s
    role: storytelling
    source_path: voices/samples/ngoc-huyen-storytelling.wav
    prepared_path: voices/prepared/ngoc-huyen/storytelling_8s/reference_24k_mono.wav
    transcript: "..."
    language: vi
    duration_seconds: 8.1
    quality_score: 86
```

Tương thích ngược:

- Profile cũ vẫn đọc được.
- Nếu profile không có `samples`, app tự tạo một sample ảo từ `audio_path/transcript`.
- Không bắt buộc migrate ngay toàn bộ JSON cũ.

### EngineProfileAsset

Cache theo engine/model/profile/sample:

```text
voices/cache/
  <profile_id>/
    <sample_id>/
      omnivoice/
        <model_id>/
          voice_clone_prompt.pkl
          meta.json
      qwen/
        <model_id>/
          voice_clone_prompt.pkl
          meta.json
      vieneu/
        <model_id>/
          ref_codes.npz
          meta.json
      valtec/
        <model_id>/
          speaker_embedding.npz
          style_embedding.npz
          meta.json
```

Cache key nên gồm:

- `profile_id`
- `sample_id`
- `model_id`
- hash của prepared WAV
- hash của transcript
- engine version nếu lấy được

Nếu audio/transcript đổi thì cache tự invalid.

### Engine Policy Layer

Thêm lớp mới, ví dụ:

```text
src/omni_tts_core/voice_profile_policy.py
```

Vai trò:

- Biết model nào cần sample dài bao nhiêu.
- Biết model nào cần transcript.
- Biết model nào dùng prepared WAV nào.
- Chọn sample phù hợp nhất nếu profile có nhiều sample.
- Trả cảnh báo UI theo model đang chọn.
- Trả engine asset nếu có cache.

Ví dụ policy:

```yaml
omnivoice:
  recommended_duration: [3, 10]
  transcript: recommended
  prepared_audio: 24000_mono_wav
  cache_asset: voice_clone_prompt

vieneu_standard:
  recommended_duration: [3, 5]
  transcript: recommended_required_for_quality
  prepared_audio: 24000_mono_wav
  cache_asset: ref_codes

qwen:
  recommended_duration: [3, 10]
  transcript: required_by_app
  prepared_audio: model_default_or_24000_mono_wav
  cache_asset: voice_clone_prompt

valtec:
  recommended_duration: [3, 10]
  transcript: unused
  prepared_audio: 24000_mono_wav
  cache_asset: speaker_style_embedding
```

## Đề xuất UX

### Khi lưu profile

UI nên phân tích và hiển thị:

```text
Duration: 9.3s
Sample rate: 44100 Hz
Channels: mono
Transcript: 171 ký tự

Đánh giá:
- OmniVoice: tốt
- VieNeu: hơi dài, nên tạo sample 3-5s
- Qwen3-TTS: tốt nếu transcript khớp audio
- Valtec: tốt
```

Không nên chặn người dùng quá sớm. Chỉ chặn nếu:

- file không đọc được.
- duration quá ngắn, ví dụ dưới 2 giây.
- không có audio speech rõ ràng.

### Khi chọn model

Dưới combobox profile nên có dòng:

```text
Profile này hợp với OmniVoice. Với VieNeu nên dùng sample 3-5s để ổn định tone.
```

Nếu model là Qwen mà profile không có transcript:

```text
Qwen3-TTS cần transcript khớp audio mẫu để clone ổn định.
```

### Khi profile có nhiều sample

Mặc định app tự chọn sample tốt nhất, nhưng cho advanced user override:

```text
Sample: Tự chọn tốt nhất / Neutral 5s / Storytelling 8s / News 6s
```

## Roadmap dài hạn

### Phase 1 - Analyzer và prepared WAV

Phạm vi:

- Thêm `VoiceSampleAnalysis`.
- Khi lưu profile, đọc duration/sample rate/channel.
- Tạo prepared WAV 24k mono trong `voices/prepared/`.
- Lưu analysis vào profile JSON nhưng vẫn giữ schema cũ đọc được.
- UI hiển thị cảnh báo theo engine.

Không đổi:

- Không đổi đường generate chính.
- Không đổi default model.
- Không bắt người dùng tạo nhiều sample.

Kết quả mong muốn:

- Người dùng biết profile nào tốt/xấu cho từng engine.
- Engine dùng audio sạch hơn nếu bật prepared path.

### Phase 2 - Engine policy

Phạm vi:

- Thêm `voice_profile_policy.py`.
- Thêm bảng policy theo provider/mode.
- `_apply_voice_profile()` không lấy thẳng `profile.audio_path` nữa mà hỏi policy.
- Policy trả về:
  - prepared audio path.
  - reference text.
  - warnings.
  - selected sample id.

Kết quả mong muốn:

- Một profile có thể dùng đúng cách hơn trên OmniVoice/VieNeu/Qwen/Valtec.
- UI có thông tin rõ khi profile không hợp model đang chọn.

### Phase 3 - Cache cho consistency giữa chunks

Ưu tiên:

1. VieNeu Standard/GGUF: đã encode reference thành `ref_codes.npy` bằng process riêng và truyền vào `tts.infer(ref_codes=..., ref_text=...)`.
2. VieNeu PyTorch: cân nhắc dùng cùng cache `ref_codes` nếu API ổn định và chất lượng không giảm.
3. OmniVoice: dùng `create_voice_clone_prompt()` rồi generate nhiều chunk bằng `voice_clone_prompt`.
4. Qwen: dùng `create_voice_clone_prompt()` rồi generate nhiều chunk.
5. Valtec: cache speaker/style embedding nếu API/vendor cho phép; nếu không thì dùng prepared WAV là đủ ở giai đoạn đầu.

Kết quả mong muốn:

- Tone giữa chunk ổn định hơn.
- Tốc độ tốt hơn khi text dài.
- Ít phụ thuộc vào encode ngẫu nhiên từng chunk.

### Phase 4 - Multi-sample profile

Phạm vi:

- Cho phép một profile chứa nhiều sample.
- Mỗi sample có `role`: neutral, storytelling, news, emotional, fast, slow.
- UI vẫn giữ chế độ đơn giản: sample mặc định.
- Advanced UI cho phép chọn sample cụ thể.

Kết quả mong muốn:

- Cùng một giọng nhưng có nhiều phong cách đọc phù hợp từng nội dung.
- Không phải tạo nhiều profile rời rạc cho cùng một người nói.

### Phase 5 - A/B Test Studio

Phạm vi:

- Một màn test cùng text/profile qua nhiều model.
- Xuất audio theo model.
- Lưu log:
  - profile id.
  - sample id.
  - prepared audio.
  - model id.
  - duration.
  - warnings.
  - cache hit/miss.

Kết quả mong muốn:

- Có bằng chứng thực tế model nào hợp profile nào.
- Giảm quyết định cảm tính khi chọn model production.

## Thứ tự ưu tiên đề xuất

1. Profile Analyzer + prepared WAV.
2. Engine policy và cảnh báo trong UI.
3. VieNeu ref-code cache cho Standard/PyTorch.
4. OmniVoice/Qwen voice prompt cache.
5. Multi-sample profile.
6. A/B Test Studio.

## Quy tắc triển khai an toàn

- Không phá profile cũ.
- Không đổi model mặc định khi chưa test.
- Không tự động ép người dùng đổi temperature/top-k/max chunk.
- Không hardcode riêng từng profile trong engine.
- Policy nằm ở core, UI chỉ hiển thị kết quả policy.
- Cache phải invalid theo hash audio/transcript/model.
- Nếu engine không hỗ trợ cache ổn định, fallback về `ref_audio/ref_text` hiện tại.

## Nguồn tham khảo

- OmniVoice official: https://github.com/k2-fsa/OmniVoice
- OmniVoice Hugging Face: https://huggingface.co/k2-fsa/OmniVoice
- VieNeu Voice Cloning docs: https://docs.vieneu.io/docs/sdk/voice-cloning/
- Qwen3-TTS 0.6B Base: https://huggingface.co/Qwen/Qwen3-TTS-12Hz-0.6B-Base
- Qwen3-TTS 1.7B Base: https://huggingface.co/Qwen/Qwen3-TTS-12Hz-1.7B-Base
- Valtec local README: `engines/valtec_worker/vendor/valtec-tts/README.md`
