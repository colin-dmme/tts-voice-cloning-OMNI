from __future__ import annotations

import pytest

from omni_tts_core.narrative_pacing.audio_analysis import PacingUnit
from omni_tts_core.narrative_pacing.boundary_classifier import (
    boundary_kind,
    bridge_strength,
    looks_like_closing,
    looks_like_intro,
    resolve_language,
)
from omni_tts_core.narrative_pacing.music_bridge_planner import plan_bridges
from omni_tts_core.narrative_pacing.topic_shift import topic_shift_scores
from omni_tts_shared.narrative_pacing import NarrativeMusicOptions

LONG_EN = (" and this sentence keeps going with enough words so that it never counts as a short"
           " punchy line in a long spoken episode, adding a little more.")
LONG_VI = " với đủ chữ để không bị coi là một câu ngắn chốt ý trong bài nói chuyện dài hơi này, kéo dài thêm."


@pytest.mark.parametrize(("language", "text", "expected"), [
    ("en", "", "en"), ("en-US", "", "en"), ("vi", "", "vi"),
    ("auto", "Welcome back to the show, today we talk about books.", "en"),
    ("auto", "Chào mừng các bạn đến với kênh, hôm nay ta nói về sách.", "vi"),
    ("auto", "", "vi"), ("auto", "这是一个测试", "other"), ("ja", "", "ja"),
])
def test_resolve_language(language, text, expected) -> None:
    assert resolve_language(language, text) == expected


@pytest.mark.parametrize(("next_text", "kind"), [
    ("So, the answer was simple" + LONG_EN, "connector"),
    ("But nobody believed him" + LONG_EN, "connector"),
    ("In other words, the book was a mirror" + LONG_EN, "connector"),
    ("First, let us look at the author" + LONG_EN, "subtopic"),
    ("Now let's turn to the second question" + LONG_EN, "subtopic"),
    ("Moving on, the story changes" + LONG_EN, "subtopic"),
    ("Nowhere is this clearer than here" + LONG_EN, "paragraph"),
    ("Something entirely ordinary happens" + LONG_EN, "paragraph"),
])
def test_english_boundary_tiers(next_text, kind) -> None:
    assert boundary_kind("The previous paragraph ends here" + LONG_EN, next_text, "en") == kind


def test_vietnamese_markers_unchanged_and_not_applied_to_english() -> None:
    prev = "Đoạn trước kết thúc ở đây" + LONG_VI
    assert boundary_kind(prev, "Bởi vậy, câu trả lời rất đơn giản" + LONG_VI, "vi") == "connector"
    assert boundary_kind(prev, "Trước hết, ta xem tác giả" + LONG_VI, "auto") == "subtopic"
    # English text tagged as Vietnamese simply gets no marker tiers.
    assert boundary_kind("Previous" + LONG_EN, "So, the answer" + LONG_EN, "vi") == "paragraph"


def test_english_music_anchors_intro_and_closing() -> None:
    assert bridge_strength("End.", "Now let's turn to the second part.", "en") == 3
    assert bridge_strength("End.", "Another reason is cost.", "en") == 2
    assert bridge_strength("Why?", "It was cheap.", "en") == 1
    assert looks_like_intro("Welcome to The Reading Room, a podcast about old books.", "en")
    assert looks_like_intro("This is episode twelve of our series.", "en")
    assert looks_like_closing("That's all for today. Thanks for listening, and see you next week.", "en")
    assert not looks_like_closing("We kept listening to the rain all night.", "en")


def test_english_shift_phrase_raises_topic_score() -> None:
    body = ["The library opened at dawn" + LONG_EN for _ in range(8)]
    plain = body[:4] + ["The library stayed open late" + LONG_EN] + body[4:]
    shifted = body[:4] + ["Which brings us to the library staying open late" + LONG_EN] + body[4:]
    units = lambda texts: [PacingUnit(i * 30.0, i * 30.0 + 28, t) for i, t in enumerate(texts)]
    assert topic_shift_scores(units(shifted), "en")[4] > topic_shift_scores(units(plain), "en")[4] + 0.3
    # "auto" on English text behaves like "en".
    assert topic_shift_scores(units(shifted), "auto") == topic_shift_scores(units(shifted), "en")


def test_english_bridges_prefer_markers_and_closing() -> None:
    texts = ["A hook that grabs attention" + LONG_EN]
    texts += [("Now let's turn to" if i % 4 == 0 else "Perhaps the point is") + LONG_EN for i in range(1, 40)]
    texts[-1] = "And that's all for today, thanks for listening" + LONG_EN
    units = [PacingUnit(i * 60.0, i * 60.0 + 55, t) for i, t in enumerate(texts)]
    plan = plan_bridges(units, NarrativeMusicOptions(enabled=True, interval_minutes=10), "auto")
    assert 39 in plan.bridges_before
    assert all(texts[b].startswith("Now let's turn") for b in plan.bridges_before[:-1])
