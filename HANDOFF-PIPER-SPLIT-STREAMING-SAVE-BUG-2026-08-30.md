# HANDOFF — Piper split streaming-save bug

Ngày ghi nhận: 2026-08-30  
Repo: `C:\Coder\tts-voice-cloning-OMNI`  
Trạng thái: **Đã điều tra, chưa sửa code trong phiên này**

## 1. Bối cảnh phát hiện

Một job TTS dài được chạy qua MCP upstream `colin-studio-tts` với provider Piper ONNX, model/voice:

`piper_vbee_ngan_ke_chuyen_2`

Input:

`H:\My Drive\00.video content\00-git-vid-content\41-nghich-thien-tv\150h-la-bo-muu-luoc\FINAL\Tap-01__0001-0075\Tap-01__0001-0075-tach-cau.txt`

Input có **971 đoạn**, kỳ vọng output:

- 971 MP3 riêng, mỗi đoạn tương ứng 1 MP3;
- 1 MP3 gộp toàn tập;
- 1 SRT đồng bộ với MP3 gộp.

Job upstream:

`123c91b2186c484a922e06ede1d5ec08`

Job kết thúc với:

- `status = succeeded`
- `progress = 100`
- `segment_count = 3298` chunk nội bộ Piper
- `duration_seconds = 36078.52789115646`
- thông báo: `Đã tạo 971 file audio riêng và file tổng.`

## 2. Hiện tượng lỗi

QC trên disk cho thấy:

- đủ **971/971 MP3 riêng**;
- tên file liên tục `001 -> 971`;
- không có MP3 0 byte;
- SRT có đúng **971 cue**;
- MP3 gộp tồn tại, bitrate 192 kbps;
- source `.txt` không thay đổi, SHA256 vẫn đúng.

Tuy nhiên timeline bị lệch lớn:

| Artifact | Thời lượng |
|---|---:|
| MP3 gộp | `36078.552 s` = **10:01:18.552** |
| Cue cuối SRT | **09:31:59.921** |
| Chênh lệch | khoảng **29:18.631** |

Cue cuối SRT hiện tại:

```text
971
09:31:23,119 --> 09:31:59,921
...
```

Trong khi MP3 gộp được `ffprobe` xác nhận:

```text
36078.552000 seconds
bit_rate=192000
```

=> Đây không phải sai số encode thông thường. SRT bị ngắn đáng kể so với audio gộp.

## 3. Kết luận điều tra hiện tại

Khả năng cao đây là **bug trong cơ chế incremental / streaming save của split output**, không phải lỗi nội dung source và không phải lỗi MCP bridge.

Luồng đang xảy ra:

1. Một line/segment người dùng có thể bị chia tiếp thành nhiều chunk nội bộ cho Piper.
2. Piper worker ghi từng chunk ra file WAV tạm.
3. `report_ready_chunks(...)` dò các WAV tạm và gọi `chunk_callback` ngay khi đánh giá file là "ready".
4. `chunk_callback` dẫn tới `save_ready_jobs_from_chunk_paths()`.
5. Khi toàn bộ chunk của một split job được cho là ready, code đọc các WAV đó bằng `_read_tts_result(...)` và lập tức tạo MP3 riêng cho split job.
6. Duration của MP3 riêng được lưu vào `saved_durations`.
7. SRT được tạo từ `saved_durations`.
8. Sau khi toàn bộ Piper batch kết thúc, MP3 gộp lại được rebuild từ `batch_results` cuối cùng — tức từ dữ liệu audio hoàn chỉnh sau khi worker đã hoàn tất.

Kết quả có thể xảy ra:

- MP3 riêng được tạo từ WAV tạm chưa hoàn tất hoàn toàn;
- duration của MP3 riêng bị ngắn;
- SRT dựa vào duration đó nên cũng ngắn;
- MP3 gộp dùng `batch_results` cuối cùng nên dài đầy đủ hơn.

Điều này khớp chính xác với hiện tượng quan sát được.

## 4. Code liên quan đã xác định

### 4.1. Readiness check của WAV tạm

File:

`src\omni_tts_core\engines\batch_progress.py`

Hàm:

```python
def audio_file_ready(path: Path, minimum_age_seconds: float = 0.2) -> bool:
    if not path.exists():
        return False
    try:
        if time.time() - path.stat().st_mtime < minimum_age_seconds:
            return False
        return sf.info(str(path)).frames > 0
    except Exception:
        return False
```

Hiện tại điều kiện chỉ là:

- file tồn tại;
- mtime cũ hơn 0.2 giây;
- `sf.info(...).frames > 0`.

Điểm đáng nghi: kiểm tra này **không chứng minh writer đã đóng file** và cũng không chứng minh file đã ngừng tăng kích thước/frames một cách ổn định.

`report_ready_chunks(...)` sau đó đánh dấu chunk là reported vĩnh viễn:

```python
reported_chunks.add(index)
if chunk_callback is not None:
    chunk_callback(index, out)
```

Sau khi đã report, chunk đó không được đọc lại để cập nhật bản cuối.

### 4.2. Streaming save của split jobs

File:

`src\omni_tts_core\service.py`

Đoạn quanh `save_ready_jobs_from_chunk_paths()`:

```python
def save_ready_jobs_from_chunk_paths() -> None:
    for job_index, job in enumerate(split_jobs, start=1):
        if job_index in saved_audio_paths:
            continue
        ...
        else:
            job_results = [_read_tts_result(path) for path in paths]
            audio_path, audio_duration, segment_count = self._save_split_job_outputs(
                job,
                job_results,
                request,
            )
            remember_saved(job_index, audio_path, audio_duration, segment_count)
```

Một khi job đã được lưu sớm thì `saved_audio_paths` khiến vòng final save bỏ qua job đó:

```python
for job_index, job in enumerate(split_jobs, start=1):
    if job_index in saved_audio_paths:
        continue
```

=> Nếu bản lưu sớm đọc WAV chưa hoàn chỉnh thì bản final **không overwrite lại bằng `batch_results` hoàn chỉnh**.

### 4.3. SRT dùng saved duration của các MP3 riêng

File:

`src\omni_tts_core\service.py`

```python
srt_path = output_dir / f"{output_stem}.srt"
write_srt(
    srt_path,
    _split_timeline_segments(
        split_jobs, saved_durations, paragraph_pauses_ms
    ),
)
```

`_split_timeline_segments(...)` dùng trực tiếp:

```python
duration = durations.get(index, 0.0)
```

Do đó nếu `saved_durations` được lấy từ MP3 riêng bị lưu sớm thì SRT cũng sai theo.

### 4.4. MP3 gộp lại dùng batch_results hoàn chỉnh

File:

`src\omni_tts_core\service.py`

```python
joined_duration = self._join_split_jobs_from_results(
    split_jobs,
    batch_results,
    joined_audio_path,
    request,
    paragraph_pauses_ms,
)
```

Trong `_join_split_jobs_from_results(...)`:

```python
job_results = batch_results[start_index : start_index + job["count"]]
combined, current_rate, _segment_count = self._build_split_job_audio(
    job, job_results, request
)
```

=> MP3 gộp được build sau `engine.generate_batch(...)` hoàn tất, dùng `batch_results` cuối cùng.

Đây là lý do mạnh nhất giải thích tại sao MP3 gộp dài hơn SRT/segment outputs.

## 5. Bằng chứng thực nghiệm bổ sung

Ví dụ vài MP3 riêng:

```text
001 = 12.792 s
486 = 44.592 s
971 = 36.840 s
```

Cue đầu SRT:

```text
1
00:00:00,000 --> 00:00:12,764
```

Sự khác biệt vài chục ms ở từng file do encode MP3 là bình thường. Vấn đề quan trọng là **tổng timeline thiếu khoảng 29 phút**, cho thấy nhiều split item có thể đã bị lưu trước khi WAV tạm hoàn tất.

## 6. Phạm vi ảnh hưởng dự kiến

Có thể ảnh hưởng các trường hợp hội đủ điều kiện:

- provider/engine ghi WAV chunk theo thời gian trong background;
- bật split output;
- sử dụng `chunk_callback` để lưu từng split job sớm;
- một split job gồm nhiều chunk nội bộ;
- final pass bỏ qua các job đã có trong `saved_audio_paths`.

Không nên mặc định lỗi chỉ riêng Piper cho đến khi kiểm engine khác, vì `batch_progress.py` là helper dùng chung. Tuy nhiên bug được tái hiện rõ với Piper persistent worker trong case này.

## 7. Hướng sửa đề xuất

### Phương án A — ưu tiên an toàn, đơn giản nhất

**Không dùng dữ liệu streaming-save làm artifact production cuối cùng.**

Cho phép streaming save để preview/progress/checkpoint nếu cần, nhưng sau khi `engine.generate_batch(...)` trả về thành công:

- rebuild/overwrite toàn bộ split MP3 từ `batch_results` cuối cùng;
- tính lại `saved_durations` từ audio final;
- sau đó mới tạo SRT;
- sau đó mới tạo MP3 gộp.

Ưu điểm:

- loại bỏ phụ thuộc vào việc detect WAV đã đóng hay chưa;
- final artifacts đều lấy từ cùng một source `batch_results`;
- đảm bảo MP3 riêng, SRT và MP3 gộp nhất quán.

Nhược điểm:

- sẽ encode split MP3 thêm một lần nếu đã từng lưu streaming;
- tốn thêm I/O/CPU nhưng đổi lại độ tin cậy cao.

Đây là phương án được khuyến nghị nhất cho production.

### Phương án B — sửa readiness detection

Thay `audio_file_ready()` bằng kiểm tra ổn định nghiêm ngặt hơn, ví dụ:

- stat size + mtime + frame count;
- chờ một khoảng;
- stat lại;
- chỉ ready nếu size, mtime, frame count không đổi qua nhiều lần;
- hoặc worker tạo file `.tmp`, sau khi đóng hoàn toàn mới atomic rename sang `.wav` final;
- hoặc worker phát explicit completion event cho từng chunk thay vì phía host tự đoán bằng filesystem polling.

Trong các lựa chọn trên, **atomic rename hoặc explicit completion event** đáng tin hơn polling theo tuổi file.

Chỉ tăng `minimum_age_seconds` từ 0.2 lên 1–2 giây không phải fix chắc chắn, vì chunk dài có thể vẫn đang được ghi sau khoảng đó.

### Phương án C — kết hợp

- worker đảm bảo publish chunk atomically;
- streaming save chỉ dùng các chunk đã publish;
- final reconciliation vẫn rebuild hoặc ít nhất validate lại mọi split job từ `batch_results`.

Đây là phương án robust nhất nếu cần vừa có progressive output vừa có artifact final chính xác.

## 8. Đề xuất thay đổi logic cụ thể

Một hướng sửa ít rủi ro trong `service.py`:

1. Giữ `save_ready_jobs_from_chunk_paths()` để tạo preview/checkpoint nếu muốn.
2. Sau `batch_results = engine.generate_batch(...)` thành công, **không `continue` đối với `saved_audio_paths`** trong final loop.
3. Luôn chạy lại `_save_split_job_outputs(job, final_job_results, request)` bằng `batch_results` final.
4. Overwrite đúng file split đã tạo trước đó.
5. Reset/rebuild `saved_durations` và `saved_segment_counts` từ final outputs.
6. Chỉ sau đó mới `write_srt(...)`.
7. Build joined audio từ cùng final `batch_results`.

Nếu overwrite semantics hiện tại không cho phép, có thể dùng temp output + atomic replace.

## 9. Test regression cần bổ sung

Nên có unit/integration test mô phỏng worker ghi WAV dần theo thời gian.

Ít nhất phải test:

1. WAV tồn tại và đã có frames nhưng vẫn tiếp tục tăng -> `audio_file_ready()` không được report sớm.
2. Nếu streaming-save tạo artifact sớm, final reconciliation phải overwrite bằng audio final.
3. `sum(duration(split files)) + paragraph pauses` phải xấp xỉ `joined duration`.
4. End timestamp cue cuối SRT phải xấp xỉ joined duration.
5. Split file count phải đúng input unit count.
6. Test với một input line dài bị chia thành nhiều chunk nội bộ.
7. Test Piper persistent worker vì đây là case đã tái hiện thực tế.

Tolerance đề xuất cho MP3 duration:

- mỗi file: có thể lệch vài chục ms do encoder/container;
- toàn bộ tập: chênh lệch SRT end vs joined duration không nên vượt khoảng 0.1–1.0 giây tùy cách encode/pause;
- tuyệt đối không chấp nhận chênh lệch hàng phút.

## 10. Tiêu chí nghiệm thu fix

Fix chỉ nên coi là PASS khi chạy lại một case đủ dài và đạt tất cả:

- job `succeeded`;
- 971/971 MP3 riêng tồn tại;
- không file 0 byte;
- sequence liên tục;
- SRT 971 cue;
- MP3 gộp tồn tại;
- tổng duration các split outputs + configured inter-item pause gần bằng joined duration;
- SRT cue cuối gần bằng joined duration;
- nội dung split source không đổi;
- không phát sinh duplicate hoặc `_1`, `_2` ngoài ý muốn;
- rerun deterministic không làm giảm duration hoặc cắt cuối file.

## 11. Trạng thái artifact hiện tại của Tập 1

Thư mục:

`H:\My Drive\00.video content\00-git-vid-content\41-nghich-thien-tv\150h-la-bo-muu-luoc\FINAL\Tap-01__0001-0075`

Hiện có:

- source `Tap-01__0001-0075-tach-cau.txt`;
- MP3 gộp `Tap-01__0001-0075-tach-cau.mp3` — hiện được đánh giá là bản audio đầy đủ;
- SRT `Tap-01__0001-0075-tach-cau.srt` — **không dùng production vì timeline ngắn**;
- thư mục `Tap-01__0001-0075-tach-cau\` chứa 971 MP3 riêng — **không nên tin production trước khi fix/reconcile**.

Không xóa các artifact này trước khi người sửa thu thập thêm bằng chứng nếu cần.

## 12. Lưu ý cho người tiếp nhận

- MCP upstream không phải nguyên nhân chính đã thấy. Job upstream chạy tới `succeeded` và trả đúng result object.
- Không cần sửa project văn bản `nghich-thien` để giải quyết lỗi này.
- Không nên rerun toàn bộ Tập 1 trước khi fix, vì có thể tái tạo đúng lỗi và mất thêm khoảng 1 giờ xử lý.
- Ưu tiên tạo test nhỏ có nhiều chunk trên mỗi split item để tái hiện nhanh trước.
- Sau khi fix test nhỏ PASS, mới rerun Tập 1 vào staging mới, QC duration, rồi mới thay output cũ.

## 13. Tóm tắt một câu

**Split MP3/SRT có khả năng bị chốt từ WAV tạm chưa đóng trong streaming callback, trong khi joined MP3 dùng `batch_results` hoàn chỉnh; cần final reconciliation từ `batch_results` hoặc cơ chế publish chunk atomic/explicit-complete để mọi artifact dùng cùng audio final.**
