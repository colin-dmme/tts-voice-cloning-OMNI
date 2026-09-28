import json, time
from colin_studio_tts_mcp.contracts import FileGenerationInput
from colin_studio_tts_mcp.server import start_file_generation, get_job

payload = {
    "source_files": [r"H:\My Drive\Colin TTS\zhihu-tu-nhan-tinh-tinh-khong-tot\zhihu-tu-nhan-tinh-tinh-khong-tot.txt"],
    "model_id": "piper_vbee_ngoc_huyen_1",
    "voice": {"mode": "fixed", "voice_id": None},
    "output": {
        "directory": r"H:\My Drive\Colin TTS\zhihu-tu-nhan-tinh-tinh-khong-tot",
        "stem": "zhihu-tu-nhan-tinh-tinh-khong-tot-ngoc-huyen-vbee",
        "mode": "merged",
        "audio_format": "mp3",
        "mp3_bitrate_kbps": 192,
        "create_srt": False,
        "join_split_audio": True,
        "append_voice_duration_suffix": False,
    },
    "generation": {
        "language": "vi",
        "runtime_target": "auto",
        "speed": 1.0,
        "pitch_shift": 0,
        "emotion": "natural",
        "max_chunk_chars": 220,
        "provider_options": {},
        "advanced": {"pronunciation_enabled": False},
    },
}
req = FileGenerationInput.model_validate(payload)
r = start_file_generation(req)
job_id = r["job_id"] if isinstance(r, dict) else r.job_id
print(json.dumps({"event":"started","job_id":job_id}, ensure_ascii=False), flush=True)
while True:
    j = get_job(job_id)
    status = j.get("status") if isinstance(j, dict) else j.status
    progress = j.get("progress") if isinstance(j, dict) else j.progress
    print(json.dumps({"event":"progress","job_id":job_id,"status":status,"progress":progress}, ensure_ascii=False), flush=True)
    if status in {"succeeded","failed","cancelled"}:
        data = j if isinstance(j, dict) else j.model_dump()
        print(json.dumps({"event":"final","job":data}, ensure_ascii=False, default=str), flush=True)
        break
    time.sleep(1)
