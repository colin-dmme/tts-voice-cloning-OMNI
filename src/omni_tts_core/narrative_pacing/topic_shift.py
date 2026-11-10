"""Score how strongly the topic changes at each paragraph boundary.

Scripts often arrive as flat paragraphs with no headings, so the larger
movements have to be inferred from the words. Two signals are combined:

* lexical cohesion (TextTiling-style): vocabulary shared by the paragraphs
  just before and just after a boundary; a deep valley means a new topic;
* discourse markers: openings such as "Trước hết", "Bây giờ", "chuyển sang"
  add weight, while connectors ("Bởi thế", "Đó là") say the thought continues.

Scores are in roughly 0..2; the planners rank boundaries by them.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from itertools import pairwise

from omni_tts_core.narrative_pacing.audio_analysis import PacingUnit
from omni_tts_core.narrative_pacing.boundary_classifier import (
    bridge_strength,
    resolve_language,
    starts_with_connector,
)

WINDOW = 3
_WORD = re.compile(r"\w+", re.UNICODE)
_STOP_VI = frozenset(
    "và là của có những một các cho không được với này đó trong khi thì mà như ta chúng "
    "người cũng đã lại ra vào để từ đến rằng nhưng nếu vì sẽ đang rất hay còn nào gì ấy "
    "thế bao điều lúc nhiều hơn chỉ mình họ ông bà đi việc nên chính về sự làm nói biết "
    "thấy nhìn đây kia vậy rồi luôn thật the a an of to in and is that it for on with as".split()
)
_STOP_EN = frozenset(
    "the a an of to in and is are was were be been it its this that these those for on with "
    "as at by from or but not no so if then than there here we you i he she they them our "
    "your my his her their what which who how when why all any some more most very just "
    "also can could will would should do does did have has had about into over out up "
    "one two like well really now let us".split()
)
_STOPWORDS = {"vi": _STOP_VI, "en": _STOP_EN}
# Phrases inside the opening sentence that announce a new movement.
_SHIFT_VI = re.compile(
    r"(chuyển sang|trở về với|trở lại với|quay lại với|bổ sung|một điểm nữa|"
    r"từ những điều vừa|một chủ đề|câu hỏi tiếp theo|bước sang|đi tiếp|"
    r"hãy cùng tìm đến|chúng ta hãy tìm đến|hãy nghĩ đến|đổi câu hỏi)",
    re.IGNORECASE,
)
_SHIFT_EN = re.compile(
    r"(moving on to|move on to|turn(ing)? to|let's look at|another (point|question|thing|idea)|"
    r"the next (question|point|step|part)|back to|coming back to|shift(ing)? (to|gears)|"
    r"switch(ing)? to|a different (question|topic|angle)|which brings us to)",
    re.IGNORECASE,
)
_SHIFTS = {"vi": _SHIFT_VI, "en": _SHIFT_EN}


def _terms(text: str, stop: frozenset[str] = _STOP_VI) -> list[str]:
    words = [w for w in _WORD.findall(text.lower()) if w not in stop and not w.isdigit()]
    # Vietnamese words are mostly two syllables: bigrams carry the meaning.
    return words + [f"{a}_{b}" for a, b in pairwise(words)]


def _cohesion(units: list[PacingUnit], stop: frozenset[str] = _STOP_VI) -> list[float]:
    docs = [Counter(_terms(u.text, stop)) for u in units]
    count = len(docs)
    df = Counter(term for doc in docs for term in doc)
    idf = {t: math.log(count / (1 + n)) for t, n in df.items()}

    def window(lo: int, hi: int) -> dict[str, float]:
        bag: Counter = Counter()
        for doc in docs[max(0, lo):min(count, hi)]:
            bag.update(doc)
        return {t: n * idf[t] for t, n in bag.items() if idf[t] > 0.5}

    def cosine(a: dict, b: dict) -> float:
        dot = sum(v * b.get(t, 0.0) for t, v in a.items())
        norm = math.sqrt(sum(v * v for v in a.values())) * math.sqrt(sum(v * v for v in b.values()))
        return dot / norm if norm else 0.0

    return [0.0] + [cosine(window(b - WINDOW, b), window(b, b + WINDOW)) for b in range(1, count)]


def _depths(sim: list[float]) -> list[float]:
    depth = [0.0] * len(sim)
    for b in range(1, len(sim)):
        left = b
        while left > 1 and sim[left - 1] >= sim[left]:
            left -= 1
        right = b
        while right < len(sim) - 1 and sim[right + 1] >= sim[right]:
            right += 1
        depth[b] = (sim[left] - sim[b]) + (sim[right] - sim[b])
    return depth


def topic_shift_scores(units: list[PacingUnit], language: str) -> list[float]:
    """score[b] for the boundary before unit b (score[0] is unused)."""
    if len(units) < 2:
        return [0.0] * len(units)
    lang = resolve_language(language, " ".join(u.text for u in units[:40]))
    stop = _STOPWORDS.get(lang, _STOP_VI | _STOP_EN)
    shift = _SHIFTS.get(lang)
    depth = _depths(_cohesion(units, stop))
    ranked = sorted(depth[1:])
    scores = [0.0]
    for b in range(1, len(units)):
        # Percentile of the cohesion valley, so long and short scripts compare alike.
        pct = sum(1 for d in ranked if d < depth[b]) / len(ranked)
        prev_text, next_text = units[b - 1].text, units[b].text
        score = pct + 0.25 * bridge_strength(prev_text, next_text, lang)
        if shift and shift.search(re.split(r"(?<=[.?!:])\s", next_text.strip())[0]):
            score += 0.4
        if starts_with_connector(next_text, lang):
            score -= 0.5
        scores.append(round(score, 3))
    return scores
