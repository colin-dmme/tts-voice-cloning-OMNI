# Engine Architecture — Tổng quan kiến trúc TTS engine

> **Cập nhật lần cuối:** 2026-05-15

---

## 1. Sơ đồ tổng quan

```
┌─────────────────────────────────────────────────────────┐
│                         UI Layer                         │
│   omni_tts_ui_tkinter  │  omni_tts_ui_gradio            │
│   (Tkinter desktop)    │  (Gradio web)                  │
└──────────────┬──────────────────────────┬───────────────┘
               │  GenerateSpeechRequest   │
               ▼                          ▼
┌─────────────────────────────────────────────────────────┐
│                      TtsService                          │
│  omni_tts_core/service.py                               │
│  - model discovery (from ModelRegistry)                  │
│  - request validation (capabilities gates)               │
│  - voice profile resolution                              │
│  - text splitting (max 220 chars/chunk)                  │
│  - audio concat + SRT generation                         │
└──────────────────────────┬──────────────────────────────┘
                           │  TtsEngineRequest (per chunk)
           ┌───────────────┼───────────────┬──────────────┐
           ▼               ▼               ▼              ▼
   ┌───────────┐  ┌──────────────┐ ┌─────────────┐ ┌──────────┐
   │OmniVoice  │  │VieneuSubproc │ │QwenSubproc  │ │ValtecSub │
   │Engine     │  │Engine        │ │Engine       │ │procEngine│
   │(in-process│  │(subprocess)  │ │(subprocess) │ │(subproc) │
   └───────────┘  └──────┬───────┘ └──────┬──────┘ └────┬─────┘
                         │                │              │
                    JSON file        JSON file      JSON file
                         ▼                ▼              ▼
                  ┌─────────────┐  ┌──────────┐  ┌──────────┐
                  │vieneu_worker│  │qwen_worker│  │valtec_wkr│
                  │.venv (riêng)│  │.venv(riêng│  │.venv(riêng│
                  └─────────────┘  └──────────┘  └──────────┘
```

---

## 2. Provider → Engine mapping

| Provider | Engine class | Kiểu | Venv |
|---|---|---|---|
| `omnivoice` | `OmniVoiceEngine` | In-process | Main project `.venv` |
| `vieneu` | `VieneuSubprocessEngine` | Subprocess | `engines/vieneu_worker/.venv` |
| `qwen` | `QwenSubprocessEngine` | Subprocess | `engines/qwen_worker/.venv` |
| `valtec` | `ValtecSubprocessEngine` | Subprocess | `engines/valtec_worker/.venv` |

**Tại sao subprocess?** Mỗi engine có dependency conflicts với nhau (torch version, llama-cpp, etc.). Subprocess với `.venv` riêng cách ly hoàn toàn.

---

## 3. Model Registry — YAML-driven

**Single source of truth:** `config/models.yaml`

```yaml
tts_models:
  <model_id>:
    display_name: str          # Hiển thị trong UI dropdown
    provider: str              # omnivoice | vieneu | qwen | valtec
    model_type: "tts"
    local_path: str            # Đường dẫn local model
    hf_repo: str               # HuggingFace repo ID
    language_priority: str     # "vi" | "vi-en" | "multilingual"
    required: bool             # Tải khi khởi động nếu true
    capabilities:              # Feature flags — UI và service đọc để enable/disable controls
      supported_languages: []
      supports_voice_profile: bool
      supports_voice_presets: bool
      supports_emotion: bool
      emotions: []
      supports_speed: bool
      supports_pitch_shift: bool
    runtime: {}                # Provider-specific config — không validate tại parse time
    voice_presets: {}          # {preset_id: label} — tự động xuất hiện trong UI
    default_voice_preset: str
```

**Thêm model mới = thêm YAML entry.** Không cần sửa code — UI tự discover qua `TtsService.list_tts_models()`.

---

## 4. Request → Engine data flow

```
GenerateSpeechRequest (Pydantic)
  text, language, model_id, voice_profile_id,
  reference_audio_path, speaker_id, speed, emotion,
  temperature, top_k, codec_repo, ...

  ↓ TtsService._apply_voice_profile()
    → resolve profile_id → reference_audio_path + reference_text
    → clear speaker_id (profile và preset mutually exclusive)

  ↓ TtsService._validate_request_for_model()
    → check capabilities gates
    → validate emotion trong whitelist
    → validate speaker_id trong voice_presets

  ↓ TtsService.split_text()
    → chia thành chunks <= max_chunk_chars (default 220)

  ↓ per chunk: engine.generate(TtsEngineRequest)
    → TtsEngineRequest(text, language, reference_audio_path,
                       reference_text, speaker_id, speed,
                       emotion, runtime_target, temperature, top_k, ...)

  ↓ concatenate_segments() + save_wav() + write_srt()
  ↓ GenerateSpeechResult
```

---

## 5. Capabilities system

`ModelCapabilities` (trong `schemas.py`) vừa là **feature discovery** cho UI, vừa là **validation gate** trong service:

| Capability | UI effect | Service validation |
|---|---|---|
| `supports_speed` | Enable/disable speed slider | Reject nếu speed ≠ 1.0 |
| `supports_emotion` | Show/hide emotion dropdown | Reject nếu emotion không trong whitelist |
| `supports_voice_presets` | Show/populate speaker dropdown | Require preset hoặc profile |
| `supports_voice_profile` | Enable/disable profile selector | Reject nếu profile không cho phép |
| `requires_voice_profile` | Force profile selection | Require profile (Qwen) |
| `supported_languages` | Filter language options | Reject nếu language không hỗ trợ |

---

## 6. Install scripts

| Script | Cài đặt |
|---|---|
| `install_tts_deps.bat` | Main project (OmniVoice, CPU torch) |
| `install_tts_deps_cuda126.bat` | Main project CUDA 12.6 |
| `install_tts_deps_cuda128.bat` | Main project CUDA 12.8 |
| `install_vieneu_worker.bat` | VieNeu CPU worker |
| `install_vieneu_worker_cuda.bat` | VieNeu GPU/CUDA worker |
| `install_qwen_worker.bat` | Qwen worker |
| `install_valtec_worker.bat` | Valtec worker |

---

## 7. Output modes

| Mode | Kết quả |
|---|---|
| `merged` | 1 file WAV + 1 file SRT (nếu bật) |
| `split` | Mỗi SRT cue → 1 file WAV riêng (`output_001.wav`, ...) |

Controlled qua `GenerateSpeechRequest.output_mode`.
