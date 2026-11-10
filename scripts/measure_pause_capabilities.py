"""Measure the silence each TTS model really leaves after every punctuation mark.

Phase 0 of plans/2026-11-10-nhip-doc-theo-nang-luc-model. Every case reads the
same paragraph with the app's own pause tools switched off (no punctuation
split, no pacing), then marks are aligned to the detected silences with the
pacing aligner. Output: one CSV row per mark plus a Markdown summary.

    .venv/Scripts/python.exe scripts/measure_pause_capabilities.py [--only zerotts,piper] [--analyze-only]
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import statistics
import sys
import time
from pathlib import Path

import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from omni_tts_core.narrative_pacing.audio_analysis import SilenceMap
from omni_tts_core.narrative_pacing.sentence_pause_aligner import (
    _align,
    _short_sentence_marks,
)

TEXT_VI = (
    "Con người ấy là ai? Chính là bản thân chúng ta. Khi đọc một cuốn sách hay, ta "
    "thường dừng lại, suy nghĩ, rồi đọc tiếp; nhưng có lúc ta vội vàng: lướt qua từng "
    "trang mà không hiểu gì cả. Đó là điều đáng tiếc… Vì vậy, hãy đọc chậm lại! Mỗi câu "
    "chữ, mỗi dấu câu, đều có ý nghĩa riêng của nó. Bạn đã bao giờ tự hỏi vì sao người "
    "xưa đọc sách to thành tiếng không? Bởi vì họ muốn nghe được nhịp của từng câu văn."
)
TEXT_EN = (
    "Who is that person? It is ourselves. When we read a good book, we often stop, "
    "think, then read on; but sometimes we rush: skimming page after page without "
    "understanding anything. That is a pity… So, slow down! Every word, every mark, "
    "has a meaning of its own. Have you ever wondered why people once read books "
    "aloud? Because they wanted to hear the rhythm of every sentence."
)
VI_PROFILE = "hoàng-quân-5f269f9b"
EN_PROFILE = "johnny-discovery-7d1dc975"

CASES: list[dict] = [
    {"id": "piper_ngoc_huyen", "model_id": "piper_vbee_ngoc_huyen_1"},
    {"id": "piper_mai_phuong", "model_id": "piper_mai_phuong"},
    {"id": "piper_nguyet_nga", "model_id": "piper_vbee_nguyet_nga_podcast"},
    {"id": "supertonic_f1", "model_id": "supertonic_3_official_onnx", "voice": "F1"},
    {"id": "kokoro_af_heart_en", "model_id": "kokoro_82m_v1_timestamped_onnx", "voice": "af_heart",
     "language": "en"},
    {"id": "zerotts_official_huuduc", "model_id": "zerotts_202m_official", "voice": "huuduc"},
    {"id": "zerotts_q8_huuduc", "model_id": "zerotts_202m_gguf_q8_0", "voice": "huuduc"},
    {"id": "vieneu_v3_pham_tuyen", "model_id": "vieneu_v3_turbo", "voice": "Phạm Tuyên"},
    {"id": "vieneu_v2_turbo_pham_tuyen", "model_id": "vieneu_v2_turbo",
     "voice": "Phạm Tuyên (Nam - Miền Bắc)"},
    {"id": "omnivoice_hoang_quan", "model_id": "omnivoice_vietnamese", "profile": VI_PROFILE},
    {"id": "f5_hoang_quan", "model_id": "f5tts_v1_base_swivid", "profile": VI_PROFILE},
    {"id": "qwen06_hoang_quan", "model_id": "qwen3_tts_06b_base", "profile": VI_PROFILE},
    {"id": "chatterbox_johnny_en", "model_id": "chatterbox_turbo_resembleai", "profile": EN_PROFILE,
     "language": "en"},
]
# WAVs made outside the app (library parameters the app does not pass yet);
# only analysed. Kokoro: kokoro_onnx.create(sentence_pause=s, clause_pause=c).
CASES += [
    {"id": f"kokoro_param_s{s}_c{c}", "language": "en", "external": True}
    for s, c in [(0, 0), (250, 100), (600, 300), (1000, 500)]
]
# Nhịp đọc defaults (total ms) per mark, as (min, max).
_TARGETS = {",": (200, 200), ";": (380, 380), ":": (380, 380), "…": (550, 550),
            ".": (520, 520), "!": (520, 520), "?": (620, 620)}
MARKS = re.compile(r"[,.?!:;…](?=\s|$)")
RUN_MIN_SECONDS = 0.05  # shorter dips are breaths inside words, not pauses
OUT = ROOT / "outputs" / "rhythm_measure"


def generate(case: dict, runtime) -> Path:
    from colin_studio_tts_mcp.contracts import TextGenerationInput

    language = case.get("language", "vi")
    voice = ({"mode": "profile", "voice_id": case["profile"]} if case.get("profile")
             else {"mode": "fixed", "voice_id": case.get("voice")})
    request = TextGenerationInput.model_validate({
        "idempotency_key": f"rhythm-measure-{case['id']}-{int(time.time())}",
        "text": TEXT_EN if language == "en" else TEXT_VI,
        "model_id": case["model_id"],
        "voice": voice,
        "output": {"directory": str(OUT), "stem": case["id"], "mode": "merged",
                   "audio_format": "wav", "create_srt": False,
                   "append_voice_duration_suffix": False},
        "generation": {
            "language": language, "speed": 1.0, "max_chunk_chars": 400,
            "provider_options": case.get("provider_options", {}),
            # Baseline: app pause tools off. Nhịp đọc cases: Nhịp đọc owns everything.
            "advanced": ({} if case.get("rhythm") else {"punctuation_pause_enabled": False})
            | case.get("advanced", {}),
            **({"pacing": {"enabled": True, "scope": "full", **case.get("rhythm_options", {})}}
               if case.get("rhythm") else {}),
        },
    })
    job_id = runtime.jobs.start_text(request)["job_id"]
    while True:
        job = runtime.jobs.get(job_id)
        if job["status"] in {"succeeded", "failed", "cancelled", "interrupted"}:
            break
        time.sleep(2)
    if job["status"] != "succeeded":
        raise RuntimeError(f"{job['status']}: {job.get('error') or job.get('message')}")
    found = _outputs(case["id"])
    if not found:
        raise RuntimeError("job succeeded but no WAV found")
    return found[-1]


def _outputs(case_id: str) -> list[Path]:
    """WAVs of exactly this case (stem or stem_N), oldest first."""
    pattern = re.compile(rf"^{re.escape(case_id)}(_\d+)?\.wav$")
    return sorted((p for p in OUT.glob("*.wav") if pattern.match(p.name)), key=lambda p: p.stat().st_mtime)


def analyze(wav: Path, text: str) -> tuple[list[dict], list[int]]:
    audio, rate = sf.read(str(wav), dtype="float32", always_2d=True)
    audio = audio.mean(axis=1)
    silence = SilenceMap(audio, rate)
    loud = np.flatnonzero(silence.frame_db > -40.0)
    step = silence.hop / rate
    start, end = loud[0] * step, (loud[-1] + 1) * step
    marks = [(m.start(), m.group(0)) for m in MARKS.finditer(text) if m.start() < len(text) - 1]
    runs = silence.quiet_runs(start + 0.15, end - 0.15, min_seconds=RUN_MIN_SECONDS)
    # Align on a speech-only clock: characters map to spoken time, so long
    # pauses earlier in the text do not push later marks out of place.
    speech_total = (end - start) - sum(b - a for a, b in runs)
    expected = [speech_total * pos / len(text) for pos, _ in marks]
    centers, before = [], 0.0
    for a, b in runs:
        centers.append(a - start - before)
        before += b - a
    matched = dict(_align(expected, centers)) if runs else {}
    rows = []
    for index, (pos, mark) in enumerate(marks):
        run = runs[matched[index]] if index in matched else None
        rows.append({
            "mark": mark, "position": pos,
            "context": text[max(0, pos - 12): pos + 1],
            "silence_ms": round((run[1] - run[0]) * 1000) if run else 0,
            "glued": run is None,
        })
    return rows, sorted((round((b - a) * 1000) for a, b in runs), reverse=True)


def order_score(text: str, runs_ms: list[int]) -> tuple[int, int]:
    """Alignment-free check: the N longest pauses vs the N targets, both sorted.

    Per-mark alignment misfires when a voice has many pauses; comparing the
    sorted lists only asks whether the pause lengths come out as intended.
    """
    marks = [(m.start(), m.group(0)) for m in MARKS.finditer(text) if m.start() < len(text) - 1]
    short = _short_sentence_marks(text, marks)
    targets = sorted((max(_TARGETS[mark][0], 700 if i in short else 0)
                      for i, (_, mark) in enumerate(marks)), reverse=True)
    heard = (runs_ms + [0] * len(targets))[: len(targets)]
    hits = sum(t - 60 <= h <= t + 150 for t, h in zip(targets, heard, strict=True))
    return hits, len(targets)


def summarize(rows_by_case: dict[str, list[dict]], errors: dict[str, str],
              runs_by_case: dict[str, list[int]]) -> str:
    groups = {"phẩy ,": ",", "; :": ";:", "…": "…", ". !": ".!", "?": "?"}
    lines = [
        "# Đo khoảng lặng thật sau dấu câu (pha 0)", "",
        (f"Ngày {time.strftime('%d/%m/%Y')}. Mỗi model đọc cùng một đoạn, tắt Ngắt nghỉ theo dấu câu "
         "và Nhịp đọc. Ô = trung vị ms (p10–p90), `đọc liền` = tỉ lệ dấu không có lặng ≥50ms."), "",
        ("Dòng `_nhip`: bật Nhịp đọc (toàn bộ, mặc định). Cột cuối: xếp N khoảng lặng dài nhất "
         "và N mục tiêu (quanh câu ngắn 700ms) theo độ dài, đếm cặp nằm trong [mục tiêu − 60, "
         "mục tiêu + 150] ms. Cách này không cần dóng từng dấu, nên không bị lệch khi giọng có "
         "nhiều chỗ ngắt."), "",
        "| Model | " + " | ".join(groups) + " | Đạt mục tiêu |",
        "|---|" + "---|" * (len(groups) + 1),
    ]
    for case_id, rows in rows_by_case.items():
        cells = []
        for chars in groups.values():
            picked = [r for r in rows if r["mark"] in chars]
            if not picked:
                cells.append("—")
                continue
            values = [r["silence_ms"] for r in picked if not r["glued"]]
            glued = sum(r["glued"] for r in picked) / len(picked)
            if values:
                q = np.percentile(values, [10, 90]).round().astype(int) if len(values) > 1 else [values[0]] * 2
                cell = f"{round(statistics.median(values))} ({q[0]}–{q[1]})"
            else:
                cell = "0"
            if glued:
                cell += f", đọc liền {glued:.0%}"
            cells.append(cell)
        if case_id.endswith("_nhip") and case_id in runs_by_case:
            text = TEXT_EN if "_en" in case_id or "kokoro" in case_id or "chatterbox" in case_id else TEXT_VI
            hits, total = order_score(text, runs_by_case[case_id])
            cells.append(f"{hits}/{total}")
        else:
            cells.append("")
        lines.append(f"| {case_id} | " + " | ".join(cells) + " |")
    if errors:
        lines += ["", "## Chưa đo được", ""]
        lines += [f"- `{case_id}`: {message}" for case_id, message in errors.items()]
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", default="", help="comma-separated substrings of case ids")
    parser.add_argument("--analyze-only", action="store_true")
    parser.add_argument("--rhythm", action="store_true",
                        help="also run each selected case with Nhịp đọc (scope full), id suffix _nhip")
    parser.add_argument("--report", default=str(
        ROOT / "plans" / "2026-11-10-nhip-doc-theo-nang-luc-model" / "reports" / "pause-capability-measurements.md"))
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    wanted = [w for w in args.only.split(",") if w]
    cases = [c for c in CASES if not wanted or any(w in c["id"] for w in wanted)]
    if args.rhythm:
        cases = [{**c, "id": c["id"] + "_nhip", "rhythm": True} for c in cases if not c.get("external")]
    runtime = None
    if not args.analyze_only:
        from colin_studio_tts_mcp.runtime import McpRuntime
        runtime = McpRuntime()
    results_path = OUT / "results.json"
    stored = json.loads(results_path.read_text(encoding="utf-8")) if results_path.exists() else {}
    rows_by_case, errors = dict(stored.get("rows", {})), dict(stored.get("errors", {}))
    runs_by_case = dict(stored.get("runs", {}))
    for case in cases:
        text = TEXT_EN if case.get("language") == "en" else TEXT_VI
        try:
            if args.analyze_only or case.get("external"):
                found = _outputs(case["id"])
                if not found:
                    continue
                wav = found[-1]
            else:
                print(f"[{case['id']}] generating…", flush=True)
                wav = generate(case, runtime)
            rows_by_case[case["id"]], runs_by_case[case["id"]] = analyze(wav, text)
            errors.pop(case["id"], None)
            print(f"[{case['id']}] ok {wav.name}", flush=True)
        except Exception as exc:  # noqa: BLE001 - one broken model must not stop the others
            errors[case["id"]] = f"{type(exc).__name__}: {exc}"[:300]
            print(f"[{case['id']}] FAILED {errors[case['id']]}", flush=True)
        results_path.write_text(json.dumps({"rows": rows_by_case, "runs": runs_by_case, "errors": errors},
                                           ensure_ascii=False, indent=1), encoding="utf-8")
    with (OUT / "marks.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(["case", "mark", "context", "silence_ms", "glued"])
        for case_id, rows in rows_by_case.items():
            for r in rows:
                writer.writerow([case_id, r["mark"], r["context"], r["silence_ms"], r["glued"]])
    report = Path(args.report)
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(summarize(rows_by_case, errors, runs_by_case), encoding="utf-8")
    print(f"report: {report}", flush=True)


if __name__ == "__main__":
    main()
