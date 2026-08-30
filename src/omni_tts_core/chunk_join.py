"""Provider-neutral policy for joining independently rendered TTS chunks."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from omni_tts_core.provider_registry import AutomaticChunkJoin, ProviderDescriptor


ChunkJoinMode = Literal["auto", "crossfade", "direct", "silence"]
EffectiveChunkJoin = Literal[
    "native", "punctuation", "silence", "crossfade", "direct"
]

CUSTOM_CHUNK_JOIN_CHOICES: tuple[tuple[str, ChunkJoinMode], ...] = (
    ("Chèn khoảng lặng", "silence"),
    ("Crossfade", "crossfade"),
    ("Nối thẳng", "direct"),
)


@dataclass(frozen=True)
class ChunkJoinPolicy:
    requested: ChunkJoinMode
    effective: EffectiveChunkJoin
    provider_label: str

    @property
    def delegates_text_boundaries(self) -> bool:
        return self.effective == "native"


def resolve_chunk_join_policy(
    requested: str,
    descriptor: ProviderDescriptor | None,
) -> ChunkJoinPolicy:
    mode: ChunkJoinMode = (
        requested
        if requested in {"auto", "crossfade", "direct", "silence"}
        else "auto"
    )
    provider_label = descriptor.label if descriptor is not None else "provider"
    automatic: AutomaticChunkJoin = (
        descriptor.automatic_chunk_join if descriptor is not None else "silence"
    )
    effective: EffectiveChunkJoin = automatic if mode == "auto" else mode
    return ChunkJoinPolicy(mode, effective, provider_label)


def describe_chunk_join_policy(policy: ChunkJoinPolicy) -> str:
    if policy.requested == "auto" and policy.effective == "native":
        return (
            f"AUTO: giao việc chia và nối đoạn nhỏ cho {policy.provider_label}; "
            "ứng dụng không tự chèn khoảng lặng hoặc crossfade giữa các chunk nội bộ."
        )
    if policy.requested == "auto" and policy.effective == "punctuation":
        return (
            f"AUTO: {policy.provider_label} dùng mức nghỉ theo dấu câu; chỉ dùng "
            "khoảng lặng kỹ thuật khi điểm cắt không có dấu phù hợp."
        )
    if policy.requested == "auto":
        return (
            f"AUTO: {policy.provider_label} chưa có bộ nối riêng đã kiểm thử; "
            "ứng dụng dùng khoảng lặng kỹ thuật an toàn."
        )
    if policy.effective == "crossfade":
        return (
            "CUSTOM: Core chồng nhẹ cuối chunk trước với đầu chunk sau; không "
            "chèn im lặng tại điểm nối do Core tạo."
        )
    if policy.effective == "direct":
        return (
            "CUSTOM: Core nối thẳng hai waveform; không chèn im lặng và không "
            "crossfade tại điểm nối do Core tạo."
        )
    return "CUSTOM: Core chèn một khoảng im lặng cố định giữa hai chunk."
