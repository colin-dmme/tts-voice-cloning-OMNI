# Hợp đồng chọn CPU máy khác cho nhiều provider

Ngày 09/11/2026. Báo cáo lập kế hoạch từ source hiện tại; không sửa implementation.

## Trạng thái đã xác minh

- `src/omni_tts_core/runtime_devices.py:24,189,197` và `src/omni_tts_shared/schemas.py:20` chỉ có `auto/cpu/cuda/remote`. `remote` đang có nhãn “Colab từ xa”; giá trị không nhận ra bị normalize thành `auto`.
- `src/omni_tts_core/ui_presenters/control_policy.py:164` ưu tiên remote-only provider: Higgs chỉ có **GPU từ xa (server quyết định)** với giá trị `auto`. Nhánh ZeroTTS Official, VieNeu v3 Turbo chèn Colab riêng; Piper/`cpu_only` chưa có remote. Nhãn CPU ONNX, GGUF và precision lấy từ model/runtime phải được giữ chính xác.
- `src/omni_tts_ui_qt/pages/settings_panel.py:712` dựng combo từ policy; khu worker chỉ hiện cho hai ID ZeroTTS Official/VieNeu v3. `current_settings:1356` chỉ chuyển item data sang chuỗi `runtime_target`.
- `GenerationSettings` tại `src/omni_tts_core/ui_presenters/settings_state.py:151,266,377,410` mang target vào request, preferences và history. Preferences lọc theo `DEFAULT_GENERATION_PREFERENCES`; field mới phải thêm cả default, dataclass và `to_request`. `src/omni_tts_core/user_state.py:26` có allowlist portable settings.
- `src/omni_tts_core/service.py:1069,1822` bỏ kiểm tra payload cài trên máy chính và cho remote chỉ với hai model ID cũ. Hai điểm tạo `TtsEngineRequest` (`679`, `1240`) phải truyền target/profile cùng nhau.
- `src/omni_tts_core/provider_registry.py:57,104` chỉ bọc VieNeu v3 và ZeroTTS bằng router; Piper gọi trực tiếp local engine. `PiperSubprocessEngine` đọc đường dẫn model/config ở máy chính; không thể thêm một nhãn UI rồi sử dụng nguyên engine đó cho máy khác.
- `src/colin_studio_tts_mcp/contracts.py:79` là Literal riêng, cùng `_PROTECTED_SETTINGS` và mapping sang GenerationSettings. Thêm lựa chọn mà chỉ sửa Qt sẽ không hoạt động từ MCP. `src/colin_colab_remote/client.py:36` còn intercept toàn bộ remote của hai model khi global Colab enabled.

## Đề xuất nhỏ, tương thích với request cũ

1. **Một lựa chọn chung `CPU máy khác`, giữ wire target cũ.** Giữ enum request `auto/cpu/cuda/remote`; thêm `remote_compute: RemoteComputeTarget | None = None` với `kind=existing_worker|managed_colab`, `worker_profile_id` và `backend=cpu|cuda`. Lựa chọn CPU máy khác luôn serialize thành `runtime_target=remote` cùng `kind=existing_worker, backend=cpu`; không cần thêm enum runtime hỗn hợp mới. `remote_compute=None` giữ cách diễn giải remote/Colab cũ cho request hiện hữu. Với `GenerationSettings`, có thể dùng ba field phẳng tương tự nhóm Higgs hiện có rồi dựng object typed tại `to_request`; thêm defaults để dữ liệu cũ tiếp tục nạp được. Credential không thuộc object này.

   Combo cần khóa UI riêng (ví dụ `external_worker_cpu`) khác lựa chọn Colab để hai hàng không cùng item data. Mapper ở presenter đổi khóa UI sang target wire + options và thực hiện chiều ngược khi restore; không đưa khóa UI vào schema/SDK hoặc `normalize_runtime_target` (hiện giá trị lạ thành Auto). Một helper `resolved_execution_target()` là nguồn diễn giải chung cho UI/MCP/service/daemon. Explicit external worker không được thừa hưởng Google-managed chỉ vì bật setting Colab toàn cục.

2. **Giữ chuẩn xử lý local.** Auto của provider cài được trên máy vẫn chỉ chọn CPU/CUDA của chính máy đó; không vì bật worker hay bật Colab mà gửi việc ra ngoài. Giữ nguyên nhãn CPU ONNX FP32/INT8, CPU GGUF và cơ chế auto GPU hiện hữu. Remote CPU chỉ thêm một nhánh thực thi; không tự đổi model/độ lượng tử. Các model VieNeu/ZeroTTS khác chỉ được bật khi có adapter cho đúng model ID, runtime và phiên bản; chưa có thì không quảng bá “cả provider đã chạy được”.

3. **Capability là điều kiện chạy; thiếu model ở máy chính không phải lỗi remote.** Policy dựa vào danh mục adapter hỗ trợ remote CPU để hiện lựa chọn; khi chọn thì hiện worker selector chung ngay dưới. Giữ lựa chọn nhìn thấy để thêm máy; khi chưa có máy tương thích, thông báo “Chưa có máy sẵn sàng cho model này” và khóa chạy. Selector lọc đúng model ID/revision, `execution_backend=cpu`, voice/clone và tùy chọn được hỗ trợ. Không dựa vào local CUDA hay `RuntimeStatus.installed` để bỏ lựa chọn remote. Backend vẫn xác minh capability lúc submit/lease, không tin mỗi UI.

4. **Đóng băng máy đích khi tạo job.** `worker_profile_id` là tham chiếu không chứa credential; nếu rỗng có thể resolve profile mặc định đúng một lần rồi lưu target snapshot vào job/checkpoint. Đổi worker ưu tiên ở UI không làm job đang chạy tự đổi máy. Giữ `selected_only` mặc định; failover là chính sách riêng, chỉ sang worker được phép và đúng model/CPU. Worker offline, thiếu model hoặc hết quyền phải chờ/lỗi có giải thích, không âm thầm chạy local hoặc GPU.

5. **Một dispatcher dùng chung và adapter theo engine.** Dùng helper/resolver chung xác định local / external CPU worker / managed Colab / remote API provider trước local validation. `kind=existing_worker` không được gọi Google OAuth, tier check, create/delete runtime ngay cả khi Colab auto đang bật. Thêm routing cho Piper; reuse router VieNeu/ZeroTTS nhưng gọi cùng bộ gửi job, download/hash và context chung. Không đưa device label của UI xuống SDK; SDK trên máy phụ nhận backend CPU đã xác thực. Model/config path của Piper được resolve trên worker, không gửi đường dẫn Windows máy chính. Coordinator hiện kiểm model/clone/batch, cần thêm điều kiện backend CPU/revision trước submit; không chỉ dựa vào worker ID.

6. **Higgs giữ nguyên hợp đồng endpoint.** Remote-only provider vẫn có `auto` với nhãn server quyết định; không hiện `CPU máy khác` hoặc worker broker selector cho Higgs. `remote_endpoint`/`higgs_*` tiếp tục phục vụ `HiggsRemoteEngine` và custom voice endpoint ID; không tái sử dụng chúng làm cấu hình CPU worker. Local Auto của provider thường và Auto của remote-only Higgs là hai resolver khác nhau có chủ đích.

7. **Serialization và frontend.** Bổ sung target options đồng bộ ở schema shared, defaults/dataclass/settings mapping, `TtsEngineRequest`, hai đường generate text/file, MCP options/protected settings và history. Đưa field target vào protected settings để không bị `advanced` ghi đè. `runtime_devices`/control policy nhận bộ lựa chọn UI và mapper nhưng enum wire vẫn giữ nguyên. Khi profile cũ không còn tồn tại, giữ lựa chọn và yêu cầu chọn lại, không dùng `default_device()` để âm thầm đổi thành local. Tkinter/Gradio đang dùng danh sách target toàn cục, cần dùng policy/mapper theo model hoặc không đưa lựa chọn UI mới vào frontend đó trước khi có selector; backend vẫn từ chối target options chưa hỗ trợ.

## Kiểm tra hợp đồng cần có khi triển khai

- `tests/test_control_policy.py`: Piper/ZeroTTS/VieNeu có CPU máy khác theo adapter mà không cần local CUDA/model; model không có adapter không được chấp nhận; các nhãn backend/precision local và Auto giữ nguyên; Higgs giữ lựa chọn endpoint cũ. Mapper không để khóa UI lạ thành Auto local.
- `tests/test_ui_presenters.py`, `tests/test_user_state.py`, `tests/test_history_restore.py`: round-trip `remote` + target existing_worker/CPU/profile qua preferences, snapshot/history và file/text request; khôi phục đúng hàng CPU máy khác; dữ liệu cũ thiếu options giữ hành vi cũ.
- `tests/test_colin_studio_tts_mcp.py`: MCP nhận cùng target/profile rõ ràng, field được bảo vệ khỏi override qua `advanced`; output/status phản ánh worker thực tế.
- Router/service: remote CPU Piper/ZeroTTS/VieNeu chạy khi payload local chưa cài; không truy cập đường dẫn model local; sai model/CPU/revision bị chặn; mixed local/remote batch bị từ chối. Giữ các bài `test_zerotts_routing_engine.py`, `test_vieneu_routing_engine.py`, `test_piper_tuning.py` và thêm remote Piper.
- Regression Google: chọn existing_worker/CPU khi managed Colab enabled không tạo bất kỳ Google provider/runtime nào; hủy job không gọi delete runtime. Test Auto không tự gửi broker. `tests/test_higgs_remote.py` giữ endpoint/options/custom voices và device policy.
- UI thực: chọn model → CPU máy khác → máy đích → tạo thử; đổi model không làm mất target âm thầm, trạng thái chưa có máy/sai capability có hành động xử lý rõ. Status remote hiển thị tên máy/backend thực tế từ worker, không dùng số GPU/RAM local.

## Phạm vi

Đây là đề xuất hợp đồng; chưa bổ sung enum/field, chưa tạo UI hoặc thực thi provider. Root có thể chọn cấu trúc target nội bộ khác, nhưng cần giữ các invariant: lựa chọn remote CPU rõ, Auto local cho provider thường, worker snapshot, Higgs riêng và Google không nhận job PC.
