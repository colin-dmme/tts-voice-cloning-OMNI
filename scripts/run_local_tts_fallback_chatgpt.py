from __future__ import annotations
import json, time
from pathlib import Path
from colin_studio_tts_mcp.runtime import McpRuntime
from colin_studio_tts_mcp.contracts import FileGenerationInput

SOURCE = r"H:\My Drive\Colin TTS\ban-chat-giao-tiep-xa-hoi-phan-1-huu-duc\BAN_CHAT_GIAO_TIEP_XA_HOI_PHAN_1_TTS.txt"
OUTDIR = r"H:\My Drive\Colin TTS\ban-chat-giao-tiep-xa-hoi-phan-1-huu-duc"
STEM = "BAN_CHAT_GIAO_TIEP_XA_HOI_PHAN_1_ZERO_TTS_HUU_DUC_Q8"

runtime = McpRuntime()

recent = runtime.jobs.list(limit=100)["jobs"]
matching = []
for job in recent:
    rs = job.get("request_summary") or {}
    out = rs.get("output") or {}
    srcs = rs.get("source_files") or []
    if SOURCE in srcs and out.get("stem") == STEM:
        matching.append(job)

for job in matching:
    if job.get("status") in {"queued","running","cancelling"}:
        print(json.dumps({"event":"resume_existing","job":job}, ensure_ascii=False), flush=True)
        job_id = job["job_id"]
        break
else:
    succeeded = next((j for j in matching if j.get("status") == "succeeded"), None)
    if succeeded:
        print(json.dumps({"event":"reuse_succeeded","job":succeeded}, ensure_ascii=False), flush=True)
        raise SystemExit(0)
    req = FileGenerationInput.model_validate({
        "source_files":[SOURCE],
        "model_id":"zerotts_202m_gguf_q8_0",
        "voice":{"mode":"fixed","voice_id":"huuduc"},
        "output":{
            "directory":OUTDIR,
            "stem":STEM,
            "mode":"merged",
            "audio_format":"mp3",
            "mp3_bitrate_kbps":192,
            "create_srt":False,
            "join_split_audio":True,
            "append_voice_duration_suffix":False
        },
        "generation":{
            "language":"vi",
            "runtime_target":"cpu",
            "speed":1.0,
            "emotion":"natural",
            "max_chunk_chars":220,
            "provider_options":{
                "normalize_vi_text":True,
                "normalize_punctuation":True,
                "clean_segment_punctuation":True,
                "max_chunk_sec":15,
                "segment_gap_seconds":0.08,
                "streaming_decoder":True
            }
        }
    })
    started = runtime.jobs.start_files(req)
    job_id = started["job_id"]
    print(json.dumps({"event":"started","job":started}, ensure_ascii=False), flush=True)

last = None
while True:
    job = runtime.jobs.get(job_id)
    key = (job.get("status"), job.get("progress"), job.get("message"))
    if key != last:
        print(json.dumps({"event":"status","job":job}, ensure_ascii=False), flush=True)
        last = key
    if job.get("status") in {"succeeded","failed","cancelled","interrupted"}:
        print(json.dumps({"event":"terminal","job":job}, ensure_ascii=False), flush=True)
        break
    time.sleep(3)
