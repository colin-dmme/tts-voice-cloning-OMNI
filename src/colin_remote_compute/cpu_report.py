"""Per-job CPU contributions from verified synthesis results."""
from __future__ import annotations

from .local_cpu import LOCAL_CPU_ID, LOCAL_CPU_LABEL


def cpu_contributions(store, job_id, target):
    profiles = target["profiles"] if target["kind"] == "cpu_pool" else [target["profile"]]
    labels = {item["worker_id"]: item["label"] for item in profiles}
    labels[LOCAL_CPU_ID] = LOCAL_CPU_LABEL
    return [row | {"name": labels.get(row["worker_id"]) or row["worker_id"] or "Đoạn cũ chưa ghi tên máy"}
            for row in store.cpu_contributions(job_id)]


def add_cpu_summary(result, contributions):
    if not contributions:
        return ""
    result["cpu_contributions"] = contributions
    if "files" in result:
        audio_files = [item["result"] for item in result["files"] if item.get("result")]
    else:
        audio_files = [result]
    outputs = {str(path) for item in audio_files for path in [item["audio_path"], *item.get("item_audio_paths", [])]
               if path}
    subtitles = {str(path) for item in audio_files for path in [item.get("srt_path"), *item.get("item_srt_paths", [])]
                 if path}
    details = " · ".join(f"{row['name']} {row['segments']} đoạn" for row in contributions)
    return f"Tổng kết CPU · {details} · {len(outputs)} audio, {len(subtitles)} SRT."
