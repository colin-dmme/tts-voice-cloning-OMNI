# Qwen Worker

Thu muc nay chua moi truong rieng cho Qwen3-TTS. App chinh goi worker qua subprocess de tranh xung dot dependency voi OmniVoice va VieNeu.

## Cai dat

Tu thu muc goc du an, chay:

```bat
install_qwen_worker.bat
```

## Cach app chinh goi worker

Core ghi mot file JSON request tam, goi `synthesize.py`, worker tao WAV tam, sau do core doc WAV lai de dung chung pipeline xuat file, tach file va SRT.

Qwen3-TTS Base uu tien che do clone voice bang profile giong hien co: `ref_audio` va `ref_text`.
