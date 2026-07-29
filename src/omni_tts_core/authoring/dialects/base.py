from __future__ import annotations

from typing import Protocol

from omni_tts_core.authoring.schemas import (
    AuthoringBrief,
    PerformancePlan,
)


class AuthoringDialect(Protocol):
    dialect_id: str

    def render(
        self,
        source_text: str,
        plan: PerformancePlan,
        brief: AuthoringBrief,
    ) -> tuple[str, list[str]]: ...
