from __future__ import annotations

import re
import unittest

from omni_tts_core.authoring.dialects.higgs import (
    HiggsDialectAdapter,
    sentence_spans,
)
from omni_tts_core.authoring.schemas import (
    AuthoringBrief,
    PerformanceDecision,
    PerformancePlan,
)


class HiggsDialectAdapterTest(unittest.TestCase):
    def test_sentence_spans_preserve_every_source_character(self) -> None:
        source = "Câu một.  Câu hai!\n\nCâu ba chưa chấm"
        spans = sentence_spans(source)
        rebuilt = "".join(item.text for item in spans)
        self.assertEqual(rebuilt, source)
        self.assertEqual(len(spans), 3)

    def test_renderer_inserts_sentence_and_positional_controls(self) -> None:
        source = "The spring does not remember. Here is the clever part."
        plan = PerformancePlan(
            decisions=[
                PerformanceDecision(
                    sentence_index=0,
                    emotion="contemplation",
                    pause_after="long",
                    reason="Đính chính quan niệm.",
                ),
                PerformanceDecision(
                    sentence_index=1,
                    emotion="awe",
                    expressiveness="high",
                    reason="Điểm tiết lộ.",
                ),
            ]
        )
        rendered, warnings = HiggsDialectAdapter().render(
            source,
            plan,
            AuthoringBrief(),
        )
        self.assertFalse(warnings)
        self.assertTrue(rendered.startswith("<|emotion:contemplation|>The spring"))
        self.assertIn(". <|prosody:long_pause|> ", rendered)
        self.assertIn(
            "<|emotion:awe|><|prosody:expressive_high|>Here",
            rendered,
        )
        spoken = re.sub(r"<\|[^|]+:[^|]+\|>", "", rendered)
        self.assertEqual(" ".join(spoken.split()), " ".join(source.split()))

    def test_sfx_requires_opt_in_and_an_existing_cue(self) -> None:
        source = "She laughed: haha."
        decision = PerformanceDecision(
            sentence_index=0,
            sfx_before="laughter",
            sfx_cue="haha",
        )
        disabled, _ = HiggsDialectAdapter().render(
            source,
            PerformancePlan(decisions=[decision]),
            AuthoringBrief(allow_vocal_sfx=False),
        )
        enabled, _ = HiggsDialectAdapter().render(
            source,
            PerformancePlan(decisions=[decision]),
            AuthoringBrief(allow_vocal_sfx=True),
        )
        self.assertNotIn("<|sfx:", disabled)
        self.assertIn("<|sfx:laughter|>haha", enabled)


if __name__ == "__main__":
    unittest.main()
