# Pha 0. Đo năng lực nghỉ thật của từng model

Trạng thái: **đã đo các model CPU (10/11/2026); còn các model GPU**. Mục đích: hồ sơ năng lực ở pha 1 phải dựa trên số đo, không dựa vào đọc source thư viện.

## Kết quả lần 1 (10/11/2026)

Script: `scripts/measure_pause_capabilities.py`. Bảng số đo: [reports/pause-capability-measurements.md](reports/pause-capability-measurements.md). Audio và số đo từng dấu nằm ở `outputs/rhythm_measure/` (`marks.csv`). Cách dóng dấu câu dùng **đồng hồ chỉ tính lúc có tiếng**; nếu tính theo thời gian tuyệt đối, khoảng nghỉ dài làm trôi vị trí và đo sai.

| Kết luận | Bằng chứng | Đã áp vào hồ sơ |
|---|---|---|
| Kokoro `sentence_pause` / `clause_pause` là **tổng lặng**, chính xác tới ±10ms | Đặt 0,6 / 1,0s → đo 605 / 1005ms; clause 0,3 / 0,5s → 305 / 505ms | Giữ `library_param`, semantics total |
| Kokoro tự nhiên nghỉ ngắn: phẩy ~70ms, cuối câu ~290ms | Bản tham số 0 | — |
| VieNeu v3 chỉ có mức cố định ở **cuối câu** (~465ms, đúng mức 0,5s của thư viện); dấu phẩy để tự nhiên ~155ms, 17% đọc liền | vieneu_v3_pham_tuyen | **Sửa:** bỏ mức cố định 0,3s ở trong câu, chuyển sang `app_stretch` |
| ZeroTTS: `;` `:` chỉ còn ~55–62ms (thư viện đổi `;` thành `,`), cuối câu chỉ 150–270ms, phẩy đọc liền 17% | zerotts official + q8 | Giữ GIỚI HẠN cho `; :`; cuối câu `library_fixed` + app bù |
| Piper: phẩy ~230–260ms, cuối câu 280–520ms tùy giọng; `…` đọc liền ở 2/3 giọng | 3 giọng | Giữ `app_split` |
| Supertonic: cuối câu chỉ ~150ms, `?` ~260ms | supertonic_f1 | Giữ `app_split` |

Mỗi loại dấu chỉ có 1–6 mẫu trong đoạn thử, nên số đo dùng để chỉ ra hướng, không dùng làm hằng số.

**Đo bổ sung khi GPU nguội (cùng ngày):**
- VieNeu v2 tự nghỉ khá dài: phẩy ~0,34s, `; :` ~0,47s, cuối câu ~0,66s.
- OmniVoice mặc định: phẩy ~0,15s, cuối câu ~0,28s.
- Chatterbox (tiếng Anh): "…" bị đọc liền, khớp với GIỚI HẠN "thư viện đổi … thành dấu phẩy".
- F5 v1 Base và Qwen3 0.6B Base không hỗ trợ tiếng Việt nên không đo; hồ sơ giữ mặc định `app_stretch`.

**Lần đo đầu (trước khi GPU nguội) chưa đo được**: VieNeu v2, OmniVoice (bật/tắt rút lặng), F5, Qwen, Chatterbox. Khi chạy, GPU đang ở 83–84°C và bộ mã hóa video NVENC bận khoảng 28% (có thể do ứng dụng điều khiển từ xa hoặc quay màn hình), nên chế độ bảo vệ GPU giữ các job chờ. Chạy lại khi GPU nguội:

```
.venv/Scripts/python.exe scripts/measure_pause_capabilities.py --only vieneu_v2,omnivoice,f5,qwen,chatterbox
```

Nhánh OmniVoice tắt `postprocess_output` cần pha 3 (engine chưa nhận tùy chọn này).

## Căn cứ

- Khảo sát source ngày 10/11/2026 (xem `plan.md`).
- Bộ dò lặng có sẵn: `src/omni_tts_core/narrative_pacing/audio_analysis.py` (`SilenceMap.quiet_runs`) và bộ dóng dấu câu `sentence_pause_aligner._align`.
- Số đo cũ: ZeroTTS huuduc sau khi giãn đạt mục tiêu ở `.` 96%, `?` 97%, `:;` khoảng 94%, `,` 84%.

## Việc cần làm

1. Script `scripts/measure_pause_capabilities.py`:
   - Dùng một đoạn văn cố định, có đủ `, ; : … . ? !`, câu ngắn và 3 đoạn.
   - Với mỗi provider/model đang cài, gọi `TtsService` ở chế độ ghép, tắt Nhịp đọc và tắt ngắt nghỉ theo dấu câu.
   - Dóng dấu câu với khoảng lặng, rồi ghi `mark → lặng đo được (ms)` và tỉ lệ dấu không có lặng (đọc liền).
2. Chạy thêm các biến thể theo tham số thư viện:
   - Kokoro: `sentence_pause` / `clause_pause` = 0,3 / 0,6 / 1,0. Kiểm tra lặng đo được có bằng **tổng** đặt vào không (top-up) hay bị cộng thêm.
   - Supertonic: `silence_duration` khi văn bản dài hơn `max_chunk_length`.
   - VieNeu v2: `silence_p`. VieNeu v3: xác nhận mức 0,3/0,5/0,7 và việc `silence_p` bị bỏ qua.
   - OmniVoice: `postprocess_output` bật/tắt. Đo mức rút lặng và tìm lặng bất thường (>2s) khi tắt.
   - Higgs (nếu có remote): có/không token `pause`, `long_pause`.
   - Chatterbox: `…` và `:` có còn lặng sau khi thư viện đổi dấu không.
3. Đo thêm trên worker remote CPU (ZeroTTS, Piper) để biết kết quả có khớp chạy local không.

## Đầu ra

- `plans/2026-11-10-nhip-doc-theo-nang-luc-model/reports/pause-capability-measurements.md`: bảng model × dấu câu (lặng trung vị, p10–p90, tỉ lệ đọc liền) và bảng tham số × kết quả.
- Mỗi ô trong ma trận mẫu ở pha 1 được xác nhận hoặc sửa theo số đo.

## Tiêu chí

- [ ] Có số đo cho mọi model đang cài: Kokoro, Piper (3 giọng), Supertonic, ZeroTTS official/GGUF, VieNeu v2/v3, OmniVoice, F5, Qwen, Valtec, Chatterbox.
- [ ] Xác định ngữ nghĩa từng tham số thư viện: tổng hay cộng thêm.
- [ ] Có ngưỡng "GIỚI HẠN" cho mỗi model, ví dụ dấu phẩy đọc liền >10%.
- [ ] Model chưa cài hoặc không chạy được ghi rõ "chưa đo"; hồ sơ của model đó để mặc định an toàn `app_stretch`.
