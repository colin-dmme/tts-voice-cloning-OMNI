"""One Vietnamese help catalogue shared by every GUI.

Both giao diện (Tkinter và PySide6) hiển thị cùng một bộ thiết lập, nên lời giải
thích phải nằm ở một chỗ duy nhất. Nếu mỗi GUI tự viết tooltip thì hai bên sẽ mô
tả cùng một nút theo hai kiểu khác nhau — đó chính là thứ làm người dùng bối rối.

GUI chỉ gọi ``tooltip("<key>")``; nội dung, đơn vị và mức khuyến nghị nằm ở đây.
"""

from __future__ import annotations

# Keys are grouped by the section a GUI draws them in, not by provider, so a new
# GUI can walk one section at a time.
TOOLTIPS: dict[str, str] = {
    # --- Cơ bản ---------------------------------------------------------------
    "provider": (
        "Lọc danh sách model theo nhà cung cấp để chọn nhanh hơn.\n"
        "Mỗi nhà cung cấp có bộ tinh chỉnh riêng, hiện ở mục "
        "'Tinh chỉnh riêng' bên dưới sau khi chọn model."
    ),
    "model": (
        "Model quyết định toàn bộ thiết lập còn lại: ngôn ngữ, thiết bị chạy được, "
        "có clone giọng hay không và có những tham số tinh chỉnh nào.\n"
        "Thiết lập nào model không hỗ trợ sẽ bị ẩn hoặc khoá, không gửi giá trị rác."
    ),
    "language": (
        "Chỉ liệt kê ngôn ngữ model này được huấn luyện. Chọn sai ngôn ngữ làm phát âm "
        "sai hoặc đọc lơ lớ, kể cả khi model vẫn chạy."
    ),
    "device": (
        "Chỉ hiện thiết bị model này chạy được. Auto để app tự chọn GPU khi có CUDA và "
        "tự lùi về CPU khi không có.\n"
        "Model không có CUDA sẽ không còn mục GPU — chọn vào chỉ để báo lỗi lúc chạy."
    ),
    "speed": (
        "Tốc độ đọc so với mặc định của model. 1.00 là giữ nguyên.\n"
        "Model không hỗ trợ đổi tốc độ sẽ ẩn dòng này và luôn chạy ở 1.00."
    ),
    "pitch": (
        "Dịch cao độ giọng theo nửa cung. 0 là giữ nguyên.\n"
        "Chỉ hiện với model khai báo hỗ trợ pitch."
    ),
    "sentence_pause": (
        "Khoảng lặng sau dấu kết thúc câu: dấu chấm, chấm hỏi hoặc chấm than.\n"
        "Piper sinh riêng các nhịp này; giá trị 0 giữ nhịp tự nhiên của model."
    ),
    "comma_pause": (
        "Khoảng lặng sau dấu phẩy. Mặc định ngắn để không làm câu bị vụn.\n"
        "Tăng quá cao có thể làm ngữ điệu Piper nghe như nhiều câu rời."
    ),
    "clause_pause": (
        "Khoảng lặng sau dấu chấm phẩy hoặc dấu hai chấm. Nên dài hơn dấu phẩy "
        "nhưng ngắn hơn cuối câu."
    ),
    "ellipsis_pause": (
        "Khoảng lặng sau dấu ba chấm (…) hoặc ba dấu chấm (...), thường dùng cho "
        "nhịp do dự hoặc chuyển ý."
    ),
    "punctuation_section": (
        "Chỉ hiện khi provider có implementation đã kiểm thử. Piper ONNX hỗ trợ bằng "
        "cách sinh từng vế rồi chèn khoảng lặng đã chọn. Mỗi loại dấu có thể dùng "
        "một giá trị cố định hoặc lấy ngẫu nhiên riêng trong khoảng Min–Max; tắt "
        "ACTIVE để giữ nguyên nhịp mặc định của model."
    ),
    "punctuation_reset": (
        "Đặt lại toàn bộ khoảng nghỉ tiêu chuẩn: cuối câu 0.32 giây, dấu phẩy "
        "0.09 giây, chấm phẩy/hai chấm 0.18 giây, dấu ba chấm 0.45 giây, "
        "chunk kỹ thuật 0.12 giây, đoạn gốc 0.60 giây, tắt các khoảng ngẫu nhiên "
        "và bật ACTIVE."
    ),
    "chunk_pause": (
        "Khoảng lặng kỹ thuật khi app buộc phải chia một câu quá dài thành nhiều chunk.\n"
        "Đây không phải nghỉ theo dấu câu. Với Piper, nếu chunk kết thúc bằng dấu câu "
        "thì app ưu tiên đúng mức của dấu đó."
    ),
    "paragraph_pause": (
        "Khoảng lặng giữa các đoạn gốc (cách nhau bằng dòng trống) khi ghép file tổng "
        "hoặc dựng timeline SRT."
    ),
    "max_chunk": (
        "App tự chia văn bản trước khi đưa vào model — đây KHÔNG phải model tự cắt.\n"
        "Thứ tự cắt: ưu tiên hết câu (. ! ?); câu nào dài hơn giới hạn mới cắt tiếp ở "
        "dấu phẩy/chấm phẩy; cuối cùng mới cắt theo từ — không bao giờ cắt giữa từ.\n"
        "Đặt quá nhỏ: câu dài bị chia vụn, dễ sai ngữ điệu. Đặt lớn: mỗi lượt model "
        "xử lý nặng hơn và tốn VRAM hơn."
    ),
    # --- Nguồn giọng ----------------------------------------------------------
    "voice_mode_fixed": (
        "Dùng giọng/model đã huấn luyện sẵn. Profile giọng và audio mẫu không được dùng."
    ),
    "voice_mode_profile": (
        "Dùng audio mẫu trong Profile để clone giọng. Giọng cố định không được dùng."
    ),
    "voice_profile": (
        "Profile chứa audio mẫu và transcript để clone giọng; không áp dụng cho giọng cố định."
    ),
    "voice_fixed": (
        "Giọng đã huấn luyện sẵn đi cùng model; không cần và không dùng Profile giọng."
    ),
    # --- Tinh chỉnh riêng (khung chung) --------------------------------------
    "tuning_activation": (
        "Bật: dùng các giá trị bên dưới khi chạy.\n"
        "Tắt: giữ nguyên giá trị đang nhập nhưng gửi mặc định của model."
    ),
    # --- VieNeu ---------------------------------------------------------------
    "vieneu_codec": (
        "Bộ mã hoá âm thanh của VieNeu. Bản ONNX chạy nhanh trên CPU; bản PyTorch cần GPU.\n"
        "Chỉ hiện với model VieNeu có khai báo codec."
    ),
    "vieneu_temperature": (
        "Độ ngẫu nhiên khi sinh giọng. Thấp = đọc đều và an toàn hơn; "
        "cao = biểu cảm hơn nhưng dễ sai từ. Mặc định theo model."
    ),
    "vieneu_top_k": (
        "Số lựa chọn token được cân nhắc mỗi bước. Nhỏ thì ổn định, lớn thì đa dạng hơn."
    ),
    "vieneu_emotion": (
        "Preset cảm xúc do model cung cấp. Model không khai báo cảm xúc sẽ ẩn dòng này."
    ),
    # --- F5-TTS ---------------------------------------------------------------
    "f5_nfe": (
        "Số bước suy luận của F5-TTS. 16 nhanh hơn nhưng dễ kém mượt; "
        "32 là mặc định cân bằng; 48-64 có thể tốt hơn nhưng chậm hơn."
    ),
    "f5_cfg": (
        "Độ bám vào prompt/giọng mẫu. Mặc định 2.0. Tăng quá cao có thể làm giọng gắt "
        "hoặc thiếu tự nhiên."
    ),
    "f5_sway": (
        "Hệ số Sway Sampling điều khiển đường lấy mẫu của F5. Mặc định -1.0 theo model; "
        "chỉ đổi khi đang A/B test chất lượng."
    ),
    "f5_crossfade": (
        "Thời gian cross-fade khi F5 phải ghép nhiều phần audio. 0.15 giây thường đủ để "
        "mối nối bớt gắt."
    ),
    "f5_rms": (
        "Mức âm lượng chuẩn hóa của reference audio. Mặc định 0.1; đổi sai có thể làm audio "
        "quá nhỏ hoặc bị nén mạnh."
    ),
    "f5_fix_duration": (
        "Ép tổng thời lượng F5 sinh ra. Để 0 để tự động; chỉ dùng khi cần khớp timing đặc biệt."
    ),
    "f5_seed": (
        "Seed cố định giúp chạy lại ra kết quả gần giống. Để trống (hoặc -1) thì mỗi lần "
        "tạo sẽ random."
    ),
    "f5_remove_silence": (
        "Cắt khoảng lặng sau khi sinh. Có thể gọn file hơn nhưng đôi khi làm mất nhịp nghỉ "
        "tự nhiên."
    ),
    # --- Chatterbox -----------------------------------------------------------
    "chatterbox_temperature": (
        "Độ ngẫu nhiên khi Chatterbox chọn token giọng. Mặc định 0.8; tăng thì đa dạng hơn "
        "nhưng dễ lệch, giảm thì ổn định hơn nhưng có thể đều."
    ),
    "chatterbox_top_p": (
        "Giới hạn nhóm token có tổng xác suất cao nhất. Mặc định 0.95; chỉ giảm khi audio "
        "bị quá ngẫu nhiên hoặc phát âm lạc."
    ),
    "chatterbox_top_k": (
        "Số lựa chọn token tối đa mỗi bước. Mặc định 1000 theo Turbo; giảm mạnh có thể làm "
        "giọng kém tự nhiên."
    ),
    "chatterbox_repetition": (
        "Phạt lặp token để tránh nói lặp/kẹt nhịp. Mặc định 1.2 theo bản Turbo mới; tăng nhẹ "
        "nếu nghe bị lặp từ."
    ),
    "chatterbox_seed": (
        "Seed cố định giúp chạy lại ra kết quả gần giống. Để trống (hoặc -1) thì mỗi lần "
        "tạo sẽ random."
    ),
    "chatterbox_norm_loudness": (
        "Chuẩn hóa độ lớn audio mẫu trước khi clone. Nên bật để giọng mẫu quá nhỏ/quá lớn "
        "không làm lệch kết quả."
    ),
    "chatterbox_tags": (
        "Turbo hiểu tag trong text như [laugh], [chuckle], [sigh], [gasp], [cough], "
        "[whisper], [breath]. Chỉ dùng khi cần hiệu ứng biểu cảm."
    ),
    # --- Higgs TTS 3 qua SGLang-Omni -----------------------------------------
    "higgs_endpoint": (
        "Dán URL gốc hoặc URL đầy đủ kết thúc bằng /v1/audio/speech. App tự chuẩn hoá "
        "đường dẫn health, models và speech. URL Quick Tunnel của TryCloudflare đổi khi "
        "tunnel khởi động lại, nên hãy cập nhật và kiểm tra trước khi chạy."
    ),
    "higgs_check": (
        "Gọi /health và /v1/models ở luồng nền; không tạo audio và không khoá giao diện."
    ),
    "higgs_auth": (
        "Máy GPU riêng có thể dùng không authorization. Boson/gateway có thể dùng Bearer "
        "token lấy từ biến môi trường, để secret không nằm trong cấu hình hoặc job manifest."
    ),
    "higgs_model": (
        "ID gửi ở trường model. Để trống để SGLang dùng model đang serve mặc định. "
        "Bấm Kiểm tra kết nối để xem ID mà /v1/models thực sự công bố."
    ),
    "higgs_voice": (
        "Giá trị trường voice của OpenAI-compatible API; thông thường giữ 'default'. "
        "Với clone giọng, Profile/audio tham chiếu vẫn được gửi riêng dưới dạng references Data URI."
    ),
    "higgs_stream": (
        "Bật để nhận PCM ngay khi server bắt đầu sinh, giảm nguy cơ Cloudflare timeout "
        "khi phải chờ toàn bộ WAV. Khi bật, response_format luôn là PCM."
    ),
    "higgs_format": "PCM dùng cho streaming; WAV chỉ dùng khi tắt streaming.",
    "higgs_temperature": "Độ ngẫu nhiên khi sinh. 1.0 là mặc định của API Higgs/SGLang.",
    "higgs_top_p": "Giới hạn nucleus sampling. Bỏ chọn để server dùng mặc định.",
    "higgs_top_k": "Giới hạn số token ứng viên. Bỏ chọn để server dùng mặc định.",
    "higgs_max_tokens": "Giới hạn token audio mới; tăng cho đoạn dài nhưng tốn thời gian/GPU hơn.",
    "higgs_seed": "Seed cố định để dễ tái lập; -1 nghĩa là không gửi seed.",
    "higgs_codec_frames": "Số codec frame ở chunk streaming đầu; mặc định 1 để có audio sớm.",
    "higgs_concurrency": (
        "Số chunk gửi song song từ app. Server anh Tùng đặt trần 16, nhưng nên bắt đầu 1 "
        "và chỉ tăng sau khi đo VRAM/độ ổn định."
    ),
    "higgs_connect_timeout": "Thời gian tối đa để thiết lập kết nối tới endpoint.",
    "higgs_request_timeout": (
        "Thời gian tối đa cho một lượt sinh. Mặc định 600 giây; streaming giúp tránh chờ "
        "im lặng quá lâu qua proxy."
    ),
    "higgs_retries": "Chỉ retry lỗi mạng và lỗi tạm thời 502–504/520–524; không retry request sai.",
    "higgs_tags": (
        "Higgs control token nằm trong nội dung. Dùng thanh Higgs Script để chèn đúng vị trí, "
        "ví dụ <|prosody:pause|> hoặc <|sfx:laughter|>Haha."
    ),
    "higgs_emotion": "21 emotion chính thức của Higgs; token được đặt đầu lượt đọc.",
    "higgs_style": "Singing, shouting hoặc whispering; để Mặc định nếu không cần.",
    "higgs_speed": "Điều khiển prosody toàn đoạn: rất chậm, chậm, nhanh hoặc rất nhanh.",
    "higgs_pitch": "Điều khiển pitch toàn đoạn: thấp khoảng -3 hoặc cao khoảng +2.5 nửa cung.",
    "higgs_expressiveness": "Độ biểu cảm toàn đoạn cao hoặc thấp.",
    # --- Bảo vệ GPU (toàn cục) ------------------------------------------------
    "gpu_enabled": (
        "Áp dụng cho MỌI model chạy CUDA, không riêng Chatterbox. Nếu tắt, app sẽ không chờ "
        "GPU rảnh và không tự dừng theo nhiệt độ, VRAM hoặc NVENC."
    ),
    "gpu_start_temp": (
        "Chỉ bắt đầu file mới khi nhiệt độ GPU không vượt mức này. Khuyến nghị 75°C. "
        "Đây không phải nhiệt độ tối đa của card."
    ),
    "gpu_abort_temp": (
        "Mốc bắt đầu đếm thời gian quá nhiệt, không dừng ngay khi vừa chạm. Khuyến nghị 82°C "
        "cho GTX 1080 Ti. NVIDIA công bố max 91°C, nhưng đó không phải mức nên chạy liên tục."
    ),
    "gpu_abort_sustain": (
        "Chỉ chuyển sang tạm nghỉ khi nhiệt độ nằm trên ngưỡng liên tục đủ số giây này. "
        "Mặc định 10 giây để bỏ qua các đỉnh nhiệt ngắn; nhiệt độ hạ xuống dưới ngưỡng sẽ "
        "xóa bộ đếm. Đặt 0 để dừng ngay. Nếu chạm ngưỡng nguy cấp riêng, app vẫn dừng ngay "
        "bất kể thời gian này."
    ),
    "gpu_emergency_temp": (
        "Mốc chuyển ngay sang chế độ tạm nghỉ, không chờ bộ đếm liên tục. Phải bằng hoặc cao "
        "hơn ngưỡng bắt đầu đếm. GTX 1080 Ti bắt đầu giảm xung khoảng 93°C và báo tự tắt ở "
        "96°C; đặt cao hơn mức tự tắt nghĩa là bảo vệ này sẽ không kịp can thiệp."
    ),
    "gpu_cooldown_max_wait": (
        "Tổng thời gian tối đa app được tạm dừng worker để chờ GPU phục hồi. Mặc định 300 giây "
        "(5 phút). App kiểm tra theo nhịp 10s, 20s, 40s, 80s... và tự tiếp tục ngay khi nhiệt độ, "
        "VRAM, NVENC đều an toàn. Đặt 0 để không chờ và báo lỗi ngay."
    ),
    "gpu_resume_temp": (
        "Sau một lỗi/nhiệt độ cao, phải nguội xuống mức này mới chạy tiếp. Giá trị phải nhỏ "
        "hơn hoặc bằng nhiệt độ bắt đầu; khuyến nghị 72°C."
    ),
    "gpu_start_vram": (
        "VRAM trống tối thiểu trước khi khởi động worker. GTX 1080 Ti có 11264 MB. "
        "Mặc định 6000 MB; nếu tiến trình khác giữ VRAM nhưng không chạy nặng, có thể thử 5000 MB."
    ),
    "gpu_runtime_vram": (
        "Nếu VRAM trống tụt dưới mức này trong lúc sinh audio, worker sẽ tạm nghỉ để tránh lỗi "
        "CUDA. Khuyến nghị 700 MB; không nên đặt dưới 512 MB."
    ),
    "gpu_usage": (
        "Chỉ bắt đầu khi mức dùng GPU không vượt tỷ lệ này. 20% là an toàn. "
        "Tăng lên 30-40% nếu tác vụ khác chỉ dùng GPU nhẹ; 100% gần như bỏ điều kiện này."
    ),
    "gpu_nvenc": (
        "Chỉ bắt đầu khi bộ mã hóa video NVENC không vượt tỷ lệ này. Giữ 5% để tránh chạy TTS "
        "đồng thời với render video; 100% gần như bỏ điều kiện NVENC."
    ),
    "gpu_reset": (
        "Đặt lại: 75°C / 82°C / 10 giây / 90°C nguy cấp / chờ tối đa 300 giây / "
        "72°C / 6000 MB / 700 MB / 20% / 5%."
    ),
    "gpu_hardware": (
        "Các mốc target/giảm xung/tự tắt được đọc trực tiếp từ nvidia-smi của card hiện tại. "
        "Luôn đặt ngưỡng dừng thấp hơn đáng kể so với giới hạn phần cứng."
    ),
    # --- Đầu ra ---------------------------------------------------------------
    "output_dir": (
        "Để trống thì file kết quả nằm cùng thư mục file nguồn và lấy tên file nguồn."
    ),
    "output_stem": (
        "Tên file xuất khi tạo từ văn bản nhập tay. Để trống thì app tự đặt theo thời điểm chạy."
    ),
    "output_format": (
        "WAV giữ nguyên chất lượng model sinh ra; MP3 nhẹ hơn nhiều nhưng là nén mất dữ liệu."
    ),
    "output_bitrate": (
        "Chỉ dùng khi xuất MP3. 192 kbps đủ cho giọng nói; tăng lên chỉ làm file nặng thêm."
    ),
    "output_overwrite": (
        "Ghi đè file trùng tên. Tắt thì app tự thêm hậu tố để không mất kết quả cũ."
    ),
    "output_split": (
        "Mỗi cue SRT / mỗi đoạn văn cách nhau bằng dòng trống thành một file audio riêng."
    ),
    "output_srt": (
        "Xuất kèm file phụ đề .srt khớp timeline với audio vừa tạo."
    ),
    "output_join": (
        "Ngoài các file lẻ, nối thêm một file audio tổng theo đúng thứ tự đoạn. "
        "Chỉ dùng được khi đang bật tách file."
    ),
}


def tooltip(key: str) -> str:
    """Help text for one control; empty string when the key is unknown."""
    return TOOLTIPS.get(key, "")
