from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, model_validator


LanguageCode = Literal["auto", "vi", "en", "zh", "ja", "ko", "de", "fr", "ru", "pt", "es", "it"]
OutputMode = Literal["merged", "split"]
OutputAudioFormat = Literal["wav", "mp3"]
RuntimeTarget = Literal["auto", "cpu", "cuda"]
VoiceSourceMode = Literal["fixed", "profile"]
RemoteAuthMode = Literal["none", "bearer_env"]
HiggsApiFlavor = Literal["sglang", "boson", "compatible"]
HiggsResponseFormat = Literal["wav", "mp3", "flac", "opus", "aac", "pcm"]


class ModelStatus(BaseModel):
    model_id: str
    display_name: str
    provider: str
    model_type: str
    hf_repo: str
    local_path: Path
    installed: bool
    required: bool = False
    size_mb: float = 0.0
    cache_size_mb: float = 0.0
    worker_size_mb: float = 0.0
    total_size_mb: float = 0.0
    notes: str = ""
    usage: str = ""
    category: str = ""
    storage_kind: str = ""
    storage_path: Path | None = None
    cache_path: Path | None = None
    worker_path: Path | None = None
    storage_note: str = ""
    worker_installed: bool | None = None  # None = không áp dụng (non-worker model)
    hf_cached: bool | None = None         # None = không áp dụng (non-worker model)


class ModelCapabilities(BaseModel):
    supported_languages: list[LanguageCode] = Field(default_factory=lambda: ["vi", "en"])
    supports_voice_profile: bool = True
    requires_voice_profile: bool = False
    supports_voice_presets: bool = False
    supports_reference_text: bool = True
    supports_speed: bool = False
    supports_pitch_shift: bool = False
    supports_emotion: bool = False
    emotions: list[str] = Field(default_factory=list)


class VoiceInputConfig(BaseModel):
    """Declarative voice-source contract consumed by services and UI presenters."""

    modes: list[VoiceSourceMode] = Field(default_factory=list)
    default_mode: VoiceSourceMode = "fixed"
    fixed_label: str = "Giọng cố định"
    fixed_tooltip: str = (
        "Giọng đã được huấn luyện sẵn. Không dùng Profile giọng hoặc audio tham chiếu."
    )
    profile_label: str = "Profile giọng"
    profile_tooltip: str = (
        "Clone giọng từ Profile đã lưu. Chỉ dùng khi model hỗ trợ audio tham chiếu."
    )

    @model_validator(mode="after")
    def validate_modes(self):
        self.modes = list(dict.fromkeys(self.modes))
        if not self.modes:
            self.modes = ["fixed"]
        if self.default_mode not in self.modes:
            self.default_mode = self.modes[0]
        return self


class VoiceOption(BaseModel):
    voice_id: str
    label: str


class GenerationFormDescriptor(BaseModel):
    model_id: str
    voice_modes: list[VoiceSourceMode]
    selected_voice_mode: VoiceSourceMode
    show_voice_mode_selector: bool
    fixed_label: str
    fixed_tooltip: str
    profile_label: str
    profile_tooltip: str
    fixed_voices: list[VoiceOption] = Field(default_factory=list)
    default_fixed_voice_id: str | None = None
    requires_fixed_voice: bool = False
    show_fixed_voice: bool = False
    show_profile: bool = False
    status_text: str = ""


class RuntimeStatus(BaseModel):
    model_id: str
    display_name: str
    provider: str
    installed: bool
    gpu_available: bool = False
    actual_device: str = "unknown"
    device_name: str = ""
    message: str = ""


class SetupTaskStatus(BaseModel):
    task_id: str
    label: str
    scope: str
    status: str
    detail: str = ""
    provider: str = ""
    model_id: str = ""
    required: bool = False
    recommended: bool = False
    can_run: bool = False
    action_label: str = ""
    script_name: str = ""


class RemoteEndpointOptions(BaseModel):
    """Connection policy shared by remote model providers.

    Secrets are deliberately represented by an environment-variable name, not
    by a token value, so preferences/job manifests never persist credentials.
    """

    endpoint_id: str = "higgs-default"
    api_flavor: HiggsApiFlavor = "sglang"
    base_url: str = ""
    auth_mode: RemoteAuthMode = "none"
    auth_env: str = "OMNI_TTS_REMOTE_API_KEY"
    connect_timeout_seconds: float = Field(default=10.0, ge=1.0, le=120.0)
    request_timeout_seconds: float = Field(default=600.0, ge=10.0, le=7200.0)
    max_retries: int = Field(default=1, ge=0, le=5)

    @model_validator(mode="after")
    def normalize_identity(self):
        self.endpoint_id = self.endpoint_id.strip() or "higgs-default"
        self.auth_env = self.auth_env.strip() or "OMNI_TTS_REMOTE_API_KEY"
        return self


class HiggsTtsOptions(BaseModel):
    """Higgs TTS 3 ``/v1/audio/speech`` options shared by remote API flavors."""

    model: str | None = None
    voice: str = "default"
    response_format: HiggsResponseFormat = "pcm"
    stream: bool = True
    max_new_tokens: int = Field(default=2048, ge=1, le=32768)
    temperature: float | None = Field(default=1.0, ge=0.1, le=2.0)
    top_p: float | None = Field(default=None, ge=0.01, le=1.0)
    top_k: int | None = Field(default=None, ge=1, le=2000)
    seed: int | None = Field(default=None, ge=0)
    initial_codec_chunk_frames: int = Field(default=1, ge=0, le=64)
    concurrency: int = Field(default=1, ge=1, le=16)
    emotion: str = ""
    style: str = ""
    speed: str = ""
    pitch: str = ""
    expressiveness: str = ""
    delivery_tags: str = ""

    @model_validator(mode="after")
    def normalize_stream_format(self):
        # The SGLang streaming endpoint emits raw signed 16-bit PCM. WAV stays
        # available for non-streaming calls.
        if self.stream:
            self.response_format = "pcm"
        self.model = (self.model or "").strip() or None
        self.voice = self.voice.strip() or "default"
        self.emotion = self.emotion.strip()
        self.style = self.style.strip()
        self.speed = self.speed.strip()
        self.pitch = self.pitch.strip()
        self.expressiveness = self.expressiveness.strip()
        self.delivery_tags = self.delivery_tags.strip()
        return self


class HiggsCustomVoice(BaseModel):
    """Reusable remote Higgs voice ID scoped to one logical endpoint profile."""

    voice_id: str
    title: str
    endpoint_id: str = "higgs-default"
    api_flavor: HiggsApiFlavor = "boson"
    ref_text: str = ""
    source_profile_id: str = ""
    created_at: str = ""

    @model_validator(mode="after")
    def normalize_fields(self):
        self.voice_id = self.voice_id.strip()
        self.title = self.title.strip()
        self.endpoint_id = self.endpoint_id.strip() or "higgs-default"
        self.ref_text = self.ref_text.strip()
        self.source_profile_id = self.source_profile_id.strip()
        if not self.voice_id:
            raise ValueError("voice_id không được để trống")
        if not self.title:
            raise ValueError("title không được để trống")
        return self


class GenerateSpeechRequest(BaseModel):
    text: str = Field(min_length=1)
    language: LanguageCode = "vi"
    model_id: str = "omnivoice_vietnamese"
    voice_source_mode: VoiceSourceMode | None = None
    voice_profile_id: str | None = None
    reference_audio_path: Path | None = None
    reference_text: str | None = None
    speaker_id: str | None = None
    speed: float = Field(default=1.0, ge=0.5, le=1.8)
    pitch_shift: float = Field(default=0.0, ge=-12.0, le=12.0)
    emotion: str = "natural"
    runtime_target: RuntimeTarget = "auto"
    codec_repo: str | None = None
    temperature: float | None = Field(default=None, ge=0.1, le=2.0)
    top_k: int | None = Field(default=None, ge=1, le=200)
    f5_nfe_step: int | None = Field(default=None, ge=4, le=128)
    f5_cfg_strength: float | None = Field(default=None, ge=0.0, le=10.0)
    f5_sway_sampling_coef: float | None = Field(default=None, ge=-5.0, le=5.0)
    f5_cross_fade_duration: float | None = Field(default=None, ge=0.0, le=2.0)
    f5_target_rms: float | None = Field(default=None, ge=0.01, le=1.0)
    f5_remove_silence: bool = False
    f5_seed: int | None = Field(default=None, ge=0)
    f5_fix_duration: float | None = Field(default=None, ge=0.0, le=120.0)
    chatterbox_temperature: float | None = Field(default=None, ge=0.1, le=2.0)
    chatterbox_top_p: float | None = Field(default=None, ge=0.05, le=1.0)
    chatterbox_top_k: int | None = Field(default=None, ge=1, le=2000)
    chatterbox_repetition_penalty: float | None = Field(default=None, ge=1.0, le=3.0)
    chatterbox_seed: int | None = Field(default=None, ge=0)
    chatterbox_norm_loudness: bool = True
    gpu_safety_enabled: bool = True
    gpu_start_temperature_c: int | None = Field(default=None, ge=50, le=85)
    gpu_abort_temperature_c: int | None = Field(default=None, ge=60, le=90)
    gpu_abort_temperature_sustain_seconds: float | None = Field(default=None, ge=0.0, le=120.0)
    gpu_emergency_temperature_c: int | None = Field(default=None, ge=60, le=120)
    gpu_cooldown_max_wait_seconds: float | None = Field(default=None, ge=0.0, le=3600.0)
    gpu_resume_temperature_c: int | None = Field(default=None, ge=45, le=80)
    gpu_minimum_free_vram_mb: int | None = Field(default=None, ge=256, le=65536)
    gpu_runtime_minimum_free_vram_mb: int | None = Field(default=None, ge=128, le=16384)
    gpu_maximum_utilization_percent: int | None = Field(default=None, ge=0, le=100)
    gpu_maximum_encoder_utilization_percent: int | None = Field(default=None, ge=0, le=100)
    punctuation_pause_enabled: bool = True
    sentence_pause_ms: int = Field(default=320, ge=0, le=3000)
    comma_pause_ms: int = Field(default=90, ge=0, le=3000)
    clause_pause_ms: int = Field(default=180, ge=0, le=3000)
    ellipsis_pause_ms: int = Field(default=450, ge=0, le=3000)
    chunk_pause_ms: int = Field(default=120, ge=0, le=3000)
    paragraph_pause_ms: int = Field(default=600, ge=0, le=10000)
    srt_file_padding_ms: int = Field(default=0, ge=0, le=10000)
    max_chunk_chars: int = Field(default=220, ge=60, le=800)
    output_dir: Path | None = None
    output_stem: str | None = None
    source_path: Path | None = None
    overwrite: bool = False
    output_mode: OutputMode = "split"
    output_audio_format: OutputAudioFormat = "wav"
    mp3_bitrate_kbps: int = Field(default=192, ge=64, le=320)
    output_srt: bool = False
    join_split_output_audio: bool = False
    remote_endpoint: RemoteEndpointOptions | None = None
    higgs: HiggsTtsOptions | None = None

    @model_validator(mode="before")
    @classmethod
    def migrate_legacy_pause_fields(cls, data):
        if isinstance(data, dict):
            data = dict(data)
            if "paragraph_pause_ms" not in data and "srt_file_padding_ms" in data:
                data["paragraph_pause_ms"] = data["srt_file_padding_ms"]
            # Before punctuation-aware providers existed, sentence_pause_ms was
            # actually the pause between Core chunks. Preserve old API calls.
            punctuation_keys = {
                "punctuation_pause_enabled",
                "comma_pause_ms",
                "clause_pause_ms",
                "ellipsis_pause_ms",
            }
            if (
                "chunk_pause_ms" not in data
                and "sentence_pause_ms" in data
                and not punctuation_keys.intersection(data)
            ):
                data["chunk_pause_ms"] = data["sentence_pause_ms"]
        return data

    @model_validator(mode="after")
    def sync_legacy_pause_field(self):
        self.srt_file_padding_ms = self.paragraph_pause_ms
        return self

    @model_validator(mode="after")
    def normalize_voice_source(self):
        if self.voice_source_mode is None:
            self.voice_source_mode = (
                "profile"
                if self.voice_profile_id or self.reference_audio_path
                else "fixed"
            )
        if self.voice_source_mode == "fixed":
            self.voice_profile_id = None
            self.reference_audio_path = None
            self.reference_text = None
        else:
            self.speaker_id = None
        return self

    @model_validator(mode="after")
    def validate_gpu_safety_thresholds(self):
        if self.gpu_resume_temperature_c is not None and self.gpu_start_temperature_c is not None:
            if self.gpu_resume_temperature_c > self.gpu_start_temperature_c:
                raise ValueError("Nhiệt độ chạy lại phải nhỏ hơn hoặc bằng nhiệt độ bắt đầu.")
        if self.gpu_start_temperature_c is not None and self.gpu_abort_temperature_c is not None:
            if self.gpu_start_temperature_c >= self.gpu_abort_temperature_c:
                raise ValueError("Nhiệt độ bắt đầu phải thấp hơn nhiệt độ dừng.")
        if self.gpu_emergency_temperature_c is not None and self.gpu_abort_temperature_c is not None:
            if self.gpu_emergency_temperature_c < self.gpu_abort_temperature_c:
                raise ValueError("Ngưỡng nguy cấp không được thấp hơn ngưỡng bắt đầu đếm quá nhiệt.")
        if (
            self.gpu_runtime_minimum_free_vram_mb is not None
            and self.gpu_minimum_free_vram_mb is not None
            and self.gpu_runtime_minimum_free_vram_mb > self.gpu_minimum_free_vram_mb
        ):
            raise ValueError("VRAM tối thiểu khi chạy không được lớn hơn VRAM cần trước khi bắt đầu.")
        return self


class GenerateSpeechResult(BaseModel):
    job_id: str
    audio_path: Path
    srt_path: Path | None = None
    job_dir: Path
    segment_count: int
    duration_seconds: float
    message: str
    item_audio_paths: list[Path] = Field(default_factory=list)
    item_srt_paths: list[Path] = Field(default_factory=list)


class SegmentTiming(BaseModel):
    index: int
    text: str
    start_seconds: float
    end_seconds: float


class AudioSampleMeta(BaseModel):
    sample_id: str = ""
    role: str = "neutral"
    audio_path: Path
    transcript: str = ""
    duration_seconds: float = 0.0
    sample_rate: int = 0


class ProfileSaveWarning(BaseModel):
    code: str
    message: str


class RefAudioHints(BaseModel):
    min_seconds: float = 0.0
    max_seconds: float = 30.0
    optimal_min_seconds: float = 3.0
    optimal_max_seconds: float = 15.0
    needs_transcript: bool = False


class VoiceProfile(BaseModel):
    profile_id: str
    name: str
    audio_path: Path
    transcript: str = ""
    language: LanguageCode = "vi"
    project: str = ""
    notes: str = ""
    created_at: str = ""
    updated_at: str = ""
    schema_version: int = 1
    duration_seconds: float = 0.0
    sample_rate: int = 0
    default_sample_id: str = ""
    extra_samples: list[AudioSampleMeta] = Field(default_factory=list)
