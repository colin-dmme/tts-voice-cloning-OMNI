# Valtec Worker

Worker rieng cho Valtec Vietnamese TTS. App chinh goi worker qua subprocess de dependency cua Valtec khong anh huong OmniVoice, VieNeu hoac Qwen.

## Cai dat

Tu thu muc goc du an, chay:

```bat
install_valtec_worker.bat
```

## Cach app chinh goi worker

Core ghi mot file JSON request tam, goi `synthesize.py`, worker tao WAV tam, sau do core doc WAV lai de dung chung pipeline xuat file, tach file va SRT.

Neu request co `ref_audio`, worker dung zero-shot voice cloning. Neu khong co `ref_audio`, worker dung giong mac dinh cua Valtec.
