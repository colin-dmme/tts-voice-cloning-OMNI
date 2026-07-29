from __future__ import annotations

from dataclasses import dataclass

from omni_tts_core.provider_registry import ProviderDescriptor


@dataclass(frozen=True)
class AuthoringPolicy:
    supported: bool
    configured: bool
    dialect_id: str = ""
    provider_label: str = ""
    features: tuple[str, ...] = ()
    reason: str = ""

    @property
    def enabled(self) -> bool:
        return self.supported and self.configured

    @property
    def tooltip(self) -> str:
        if not self.supported:
            return self.reason or "Provider TTS này không hỗ trợ điều khiển cách diễn."
        if not self.configured:
            return (
                "Provider TTS có hỗ trợ nhưng chưa có Gemini API key khả dụng. "
                "Mở mục AI / API để cấu hình."
            )
        return (
            "AI phân tích nội dung và profile giọng, tạo nhiều phương án điều khiển "
            f"theo dialect {self.dialect_id}."
        )


def build_authoring_policy(
    descriptor: ProviderDescriptor | None,
    *,
    ai_configured: bool,
) -> AuthoringPolicy:
    if descriptor is None or not descriptor.authoring_dialect:
        return AuthoringPolicy(
            supported=False,
            configured=ai_configured,
            provider_label=descriptor.label if descriptor else "",
            reason="Provider TTS này chưa khai báo authoring dialect.",
        )
    return AuthoringPolicy(
        supported=True,
        configured=ai_configured,
        dialect_id=descriptor.authoring_dialect,
        provider_label=descriptor.label,
        features=tuple(sorted(descriptor.authoring_features)),
    )
