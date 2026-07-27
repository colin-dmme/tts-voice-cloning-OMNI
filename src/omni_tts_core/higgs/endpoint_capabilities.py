from __future__ import annotations

from dataclasses import dataclass


HIGGS_API_FLAVOR_CHOICES = (
    ("SGLang-Omni / máy GPU riêng", "sglang"),
    ("Boson Cloud / API có Custom Voice", "boson"),
    ("Gateway Higgs tương thích", "compatible"),
)

BOSON_PRESET_VOICES = (
    ("Chloe · thân thiện, rõ ràng", "chloe"),
    ("Eleanor · bình tĩnh, chuyên nghiệp", "eleanor"),
    ("Jake · năng lượng, kịch tính", "jake"),
    ("Marcus · tự tin, thuyết minh", "marcus"),
    ("Nora · kể chuyện nhẹ nhàng", "nora"),
    ("Oliver · trầm tĩnh, suy tưởng", "oliver"),
)


@dataclass(frozen=True)
class HiggsEndpointCapabilities:
    api_flavor: str
    supports_inline_tags: bool = True
    supports_reference_clone: bool = True
    supports_custom_voice_create: bool = False
    supports_preset_voices: bool = False
    supports_reference_codes: bool = False


def endpoint_capabilities(api_flavor: str) -> HiggsEndpointCapabilities:
    flavor = str(api_flavor or "sglang").strip().lower()
    if flavor == "boson":
        return HiggsEndpointCapabilities(
            api_flavor=flavor,
            supports_custom_voice_create=True,
            supports_preset_voices=True,
        )
    if flavor == "compatible":
        return HiggsEndpointCapabilities(
            api_flavor=flavor,
            supports_custom_voice_create=True,
            supports_preset_voices=True,
        )
    return HiggsEndpointCapabilities(
        api_flavor="sglang",
        supports_reference_codes=True,
    )


def endpoint_preset_voices(api_flavor: str) -> tuple[tuple[str, str], ...]:
    capabilities = endpoint_capabilities(api_flavor)
    return BOSON_PRESET_VOICES if capabilities.supports_preset_voices else ()
