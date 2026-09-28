from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from omni_tts_core.engines.base import BaseTtsEngine
from omni_tts_core.engines.chatterbox_engine import ChatterboxSubprocessEngine
from omni_tts_core.engines.f5tts_engine import F5TtsSubprocessEngine
from omni_tts_core.engines.higgs_remote_engine import HiggsRemoteEngine
from omni_tts_core.engines.omnivoice_engine import OmniVoiceEngine
from omni_tts_core.engines.piper_engine import PiperSubprocessEngine
from omni_tts_core.engines.preset_onnx_engine import PresetOnnxSubprocessEngine
from omni_tts_core.engines.qwen_engine import QwenSubprocessEngine
from omni_tts_core.engines.valtec_engine import ValtecSubprocessEngine
from omni_tts_core.engines.vieneu_engine import VieneuSubprocessEngine
from omni_tts_core.model_registry import ModelSpec
from omni_tts_core.provider_options import ProviderSettingSpec

StorageMode = Literal["folder", "hf_cache", "remote"]
AutomaticChunkJoin = Literal["native", "punctuation", "silence"]
EngineFactory = Callable[[ModelSpec, object | None], BaseTtsEngine]


@dataclass(frozen=True)
class ProviderDescriptor:
    provider_id: str
    label: str
    storage_mode: StorageMode
    worker_name: str | None
    engine_factory: EngineFactory
    controls: frozenset[str] = frozenset()
    max_parallel_jobs: int = 1
    # Optional provider-neutral authoring contract.  A future TTS provider only
    # declares its dialect/features and supplies an adapter; GUI code never
    # branches on provider_id.
    authoring_dialect: str | None = None
    authoring_features: frozenset[str] = frozenset()
    # Core owns the generic join modes, while each provider declares what
    # "Auto" means.  Frontends only display the resulting metadata.
    automatic_chunk_join: AutomaticChunkJoin = "silence"
    settings: tuple[ProviderSettingSpec, ...] = ()
    speed_minimum: float = 0.5
    speed_maximum: float = 1.8
    # Some providers own both text normalization and long-form splitting.  In
    # that case Core must preserve the original text so their documented
    # preprocessing switches remain truthful.
    native_text_preprocessing: bool = False


def _omnivoice(spec: ModelSpec, cache: object | None) -> BaseTtsEngine:
    return OmniVoiceEngine(spec, cache)


def _vieneu(spec: ModelSpec, cache: object | None) -> BaseTtsEngine:
    return VieneuSubprocessEngine(spec, cache)


def _qwen(spec: ModelSpec, cache: object | None) -> BaseTtsEngine:
    return QwenSubprocessEngine(spec, cache)


def _simple(factory):
    return lambda spec, _cache: factory(spec)


def _preset_onnx(spec: ModelSpec, _cache: object | None) -> BaseTtsEngine:
    return PresetOnnxSubprocessEngine(spec)


PROVIDERS: dict[str, ProviderDescriptor] = {
    "omnivoice": ProviderDescriptor(
        "omnivoice", "OmniVoice", "folder", None, _omnivoice,
        frozenset({"speed"}),
    ),
    "vieneu": ProviderDescriptor(
        "vieneu", "VieNeu", "hf_cache", "vieneu_worker", _vieneu,
        frozenset({"codec", "sampling", "emotion"}),
        automatic_chunk_join="native",
    ),
    "qwen": ProviderDescriptor(
        "qwen", "Qwen", "folder", "qwen_worker", _qwen,
    ),
    "valtec": ProviderDescriptor(
        "valtec", "Valtec", "hf_cache", "valtec_worker", _simple(ValtecSubprocessEngine),
    ),
    "f5tts": ProviderDescriptor(
        "f5tts", "F5-TTS", "folder", "f5_worker", _simple(F5TtsSubprocessEngine),
        frozenset({"f5"}),
    ),
    "chatterbox": ProviderDescriptor(
        "chatterbox", "Chatterbox", "folder", "chatterbox_worker",
        _simple(ChatterboxSubprocessEngine), frozenset({"chatterbox"}),
    ),
    "piper": ProviderDescriptor(
        "piper", "Piper ONNX", "folder", "piper_worker", _simple(PiperSubprocessEngine),
        frozenset({"speed", "punctuation_pauses", "piper"}), 2,
        automatic_chunk_join="punctuation",
    ),
    "kokoro_onnx": ProviderDescriptor(
        "kokoro_onnx",
        "Kokoro ONNX",
        "folder",
        "kokoro_worker",
        _preset_onnx,
        frozenset({"speed", "punctuation_pauses", "provider_options"}),
        1,
        automatic_chunk_join="punctuation",
        settings=(
            ProviderSettingSpec(
                "trim_silence",
                "Cắt im lặng đầu/cuối",
                "boolean",
                True,
                "Bỏ khoảng im lặng dư do model tạo ở đầu và cuối từng đoạn nhỏ.",
            ),
            ProviderSettingSpec(
                "continuous_prosody",
                "Ngữ điệu liên tục",
                "boolean",
                False,
                "Giữ mạch ngữ điệu tốt hơn giữa các câu; chậm hơn và chỉ dùng với model timestamped.",
            ),
        ),
    ),
    "supertonic": ProviderDescriptor(
        "supertonic",
        "Supertonic 3",
        "folder",
        "supertonic_worker",
        _preset_onnx,
        frozenset({"speed", "punctuation_pauses", "provider_options"}),
        1,
        automatic_chunk_join="punctuation",
        settings=(
            ProviderSettingSpec(
                "total_steps",
                "Mức chất lượng",
                "integer",
                8,
                "Số bước khử nhiễu: cao hơn thường rõ hơn nhưng xử lý chậm hơn. Khuyến nghị 8.",
                minimum=5,
                maximum=12,
                step=1,
            ),
        ),
        speed_minimum=0.7,
        speed_maximum=1.8,
    ),
    "zerotts": ProviderDescriptor(
        "zerotts",
        "ZeroTTS",
        "folder",
        "zerotts_worker",
        _preset_onnx,
        frozenset({"provider_options"}),
        1,
        automatic_chunk_join="native",
        settings=(
            ProviderSettingSpec(
                "normalize_vi_text",
                "Chuẩn hóa số và viết tắt tiếng Việt",
                "boolean",
                True,
                "Dùng bộ chuẩn hóa chính thức của ZeroTTS cho ngày, giờ, số, phân số và viết tắt. Chỉ áp dụng khi chọn tiếng Việt.",
            ),
            ProviderSettingSpec(
                "normalize_punctuation",
                "Chuẩn hóa dấu câu và xuống dòng",
                "boolean",
                True,
                "Đổi dấu chấm phẩy thành dấu phẩy và bảo toàn nhịp nghỉ của xuống dòng trước khi chia đoạn.",
            ),
            ProviderSettingSpec(
                "clean_segment_punctuation",
                "Làm sạch dấu câu từng đoạn",
                "boolean",
                True,
                "Chuẩn hóa dấu kết thúc của từng đoạn theo pipeline long-form chính thức.",
            ),
            ProviderSettingSpec(
                "max_chunk_sec",
                "Độ dài đoạn ước tính",
                "number",
                15.0,
                "Ngân sách thời lượng ước tính cho bộ chia đoạn riêng của ZeroTTS.",
                minimum=5.0,
                maximum=25.0,
                step=1.0,
                decimals=1,
            ),
            ProviderSettingSpec(
                "segment_gap_seconds",
                "Khoảng lặng giữa đoạn",
                "number",
                0.08,
                "Khoảng lặng chèn giữa các đoạn nội bộ; 0,08 giây tương ứng một frame codec 12,5 Hz.",
                minimum=0.0,
                maximum=2.0,
                step=0.01,
                decimals=2,
            ),
            ProviderSettingSpec(
                "cfg_scale",
                "CFG scale cho danh tính giọng",
                "number",
                1.0,
                "1,0 là tắt. Giá trị lớn hơn 1 tăng độ bám giọng nhưng gần gấp đôi chi phí mỗi frame.",
                minimum=1.0,
                maximum=4.0,
                step=0.1,
                decimals=1,
            ),
            ProviderSettingSpec(
                "text_temperature",
                "Text temperature",
                "number",
                1.0,
                "Temperature của kênh điều khiển văn bản trong API ZeroTTS.",
                minimum=0.01,
                step=0.05,
                decimals=2,
            ),
            ProviderSettingSpec(
                "text_topk",
                "Text top-k",
                "integer",
                50,
                "Top-k của kênh điều khiển văn bản; vocab model hiện tại có 8192 token.",
                minimum=1,
                maximum=8192,
                step=1,
            ),
            ProviderSettingSpec(
                "audio_temperature",
                "Audio temperature",
                "number",
                0.8,
                "Temperature lấy mẫu audio; mặc định benchmark chính thức là 0,8.",
                minimum=0.1,
                maximum=1.5,
                step=0.05,
                decimals=2,
            ),
            ProviderSettingSpec(
                "audio_topk",
                "Audio top-k",
                "integer",
                25,
                "Top-k lấy mẫu audio; giao diện chính thức cho phép từ 1 đến 200.",
                minimum=1,
                maximum=200,
                step=1,
            ),
            ProviderSettingSpec(
                "audio_topp",
                "Audio top-p",
                "number",
                0.95,
                "Top-p lấy mẫu audio.",
                minimum=0.1,
                maximum=1.0,
                step=0.01,
                decimals=2,
            ),
            ProviderSettingSpec(
                "audio_repetition_penalty",
                "Audio repetition penalty",
                "number",
                1.2,
                "Mặc định benchmark là 1,2; 1,0 tắt penalty và theo tác giả làm tăng WER cùng khoảng lặng dư.",
                minimum=1.0,
                maximum=2.0,
                step=0.05,
                decimals=2,
            ),
            ProviderSettingSpec(
                "min_frames",
                "Số frame tối thiểu",
                "integer",
                4,
                "Cấm tín hiệu kết thúc trước số frame này; mỗi frame dài khoảng 0,08 giây.",
                minimum=0,
                maximum=1500,
                step=1,
            ),
            ProviderSettingSpec(
                "max_frames",
                "Số frame tối đa",
                "integer",
                1500,
                "Giới hạn an toàn số frame cho một đoạn; mặc định API là 1500.",
                minimum=1,
                maximum=1500,
                step=1,
            ),
            ProviderSettingSpec(
                "eoa_extra_frames",
                "Frame đuôi sau tín hiệu dừng",
                "integer",
                1,
                "Giữ thêm frame đuôi sau tín hiệu dừng; 0 có thể cắt cụt âm cuối.",
                minimum=0,
                maximum=4,
                step=1,
            ),
            ProviderSettingSpec(
                "seed",
                "Seed lấy mẫu",
                "integer",
                -1,
                "-1 là ngẫu nhiên; số không âm giúp tái lập kết quả với cùng văn bản và setting.",
                minimum=-1,
                maximum=2147483647,
                step=1,
            ),
            ProviderSettingSpec(
                "streaming_decoder",
                "Dùng decoder streaming",
                "boolean",
                True,
                "Dùng đường synthesize_stream chính thức. App vẫn lưu xong file trước khi phát hoặc trả kết quả MCP.",
            ),
            ProviderSettingSpec(
                "first_chunk_frames",
                "Frame của chunk streaming đầu",
                "integer",
                1,
                "Số frame codec trong chunk streaming đầu tiên.",
                minimum=1,
                maximum=64,
                step=1,
            ),
            ProviderSettingSpec(
                "max_chunk_frames",
                "Frame tối đa mỗi chunk streaming",
                "integer",
                16,
                "Trần frame mỗi lần giải mã streaming sau giai đoạn tăng dần.",
                minimum=1,
                maximum=64,
                step=1,
            ),
            ProviderSettingSpec(
                "intra_op_num_threads",
                "Luồng suy luận model",
                "integer",
                4,
                "Số luồng cho model: ONNX Runtime ở bản ONNX, ggml ở bản GGUF.",
                minimum=1,
                maximum=64,
                step=1,
            ),
            ProviderSettingSpec(
                "codec_intra_op_num_threads",
                "Luồng ONNX cho codec",
                "integer",
                0,
                "0 dùng cùng số luồng của model; giá trị dương đặt riêng cho codec.",
                minimum=0,
                maximum=64,
                step=1,
            ),
            ProviderSettingSpec(
                "warmup",
                "Warmup khi nạp model",
                "boolean",
                True,
                "Chạy một lượt giả qua đường nóng để lần tạo thật đầu tiên không chịu chi phí khởi tạo lazy.",
            ),
        ),
        native_text_preprocessing=True,
    ),
    "higgs_remote": ProviderDescriptor(
        "higgs_remote",
        "Higgs Remote GPU",
        "remote",
        None,
        _simple(HiggsRemoteEngine),
        frozenset({"higgs_remote", "higgs_script"}),
        2,
        "higgs_v1",
        frozenset(
            {
                "emotion",
                "style",
                "pace",
                "pitch",
                "expressiveness",
                "pause",
                "vocal_sfx",
            }
        ),
    ),
}


def provider_descriptor(provider_id: str) -> ProviderDescriptor | None:
    return PROVIDERS.get(provider_id)
