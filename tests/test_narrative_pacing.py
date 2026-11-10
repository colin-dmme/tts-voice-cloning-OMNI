import json
import random
import unittest
from itertools import pairwise
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
import soundfile as sf

from omni_tts_core.chapter_music import ChapterMusicLibrary
from omni_tts_core.narrative_pacing import (
    PacingUnit,
    apply_narrative_pacing,
    repace_existing_output,
)
from omni_tts_core.narrative_pacing.audio_analysis import SilenceMap
from omni_tts_core.narrative_pacing.boundary_classifier import boundary_kind
from omni_tts_core.narrative_pacing.existing_output_repacer import read_srt_units
from omni_tts_core.narrative_pacing.music_bridge_planner import plan_bridges
from omni_tts_core.narrative_pacing.section_planner import plan_sections
from omni_tts_core.narrative_pacing.sentence_pause_aligner import plan_sentence_pauses
from omni_tts_core.narrative_pacing.topic_shift import topic_shift_scores
from omni_tts_core.subtitles.srt_builder import write_srt
from omni_tts_shared.narrative_pacing import (
    NarrativeMusicOptions,
    NarrativePacingOptions,
)
from omni_tts_shared.schemas import GenerateSpeechRequest, SegmentTiming
from tests.test_epub import fake_service

RATE = 24000
LONG = " với đủ chữ để không bị coi là một câu ngắn chốt ý trong bài nói chuyện dài hơi này, kéo dài thêm một chút."


def tone(seconds: float) -> np.ndarray:
    t = np.arange(int(seconds * RATE)) / RATE
    return (0.3 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)


def narration(texts: list[str], seconds: float = 4.0, gap: float = 0.3):
    parts, units, cursor = [], [], 0.0
    for i, text in enumerate(texts):
        parts.append(tone(seconds))
        units.append(PacingUnit(cursor, cursor + seconds, text))
        cursor += seconds
        if i < len(texts) - 1:
            parts.append(np.zeros(int(gap * RATE), dtype=np.float32))
            cursor += gap
    return np.concatenate(parts), units


def library_with_music(root: Path) -> ChapterMusicLibrary:
    library = ChapterMusicLibrary(root / "library")
    for track_id, seconds, themes in (("bridge-a", 6, ["co-trang"]), ("bridge-b", 5, ["co-trang"]),
                                      ("series-theme", 14, ["mo-ket"])):
        source = root / f"{track_id}.wav"
        t = np.arange(seconds * RATE) / RATE
        sf.write(source, 0.2 * np.sin(2 * np.pi * 330 * t), RATE)
        library.import_track(source, track_id, track_id=track_id, themes=themes)
    return library


class BoundaryClassifierTests(unittest.TestCase):
    def test_vietnamese_tiers(self):
        self.assertEqual(boundary_kind("A" + LONG, "Trước hết, ta xem" + LONG, "vi"), "subtopic")
        self.assertEqual(boundary_kind("A" + LONG, "Nhưng điều ấy" + LONG, "vi"), "connector")
        self.assertEqual(boundary_kind("Vì sao" + LONG + "?", "Có lẽ" + LONG, "vi"), "question")
        self.assertEqual(boundary_kind("Chính là bản thân chúng ta.", "Có lẽ" + LONG, "vi"), "emphasis")
        self.assertEqual(boundary_kind("A" + LONG, "Có lẽ" + LONG, "vi"), "paragraph")
        self.assertEqual(boundary_kind("A" + LONG, "Nhưng điều ấy" + LONG, "en"), "paragraph")


class SentencePauseTests(unittest.TestCase):
    def test_only_sentence_final_silence_is_stretched(self):
        text = "Một hai ba bốn năm sáu, bảy tám chín mười. Mười một mười hai mười ba mười bốn."
        speech = 6.0
        marks = [text.index(","), text.index(".")]
        audio = tone(speech)
        for pos in marks:
            centre = speech * pos / len(text)
            audio[int((centre - 0.12) * RATE):int((centre + 0.12) * RATE)] = 0
        unit = PacingUnit(0.0, speech, text)
        inserts = plan_sentence_pauses(SilenceMap(audio, RATE), unit, NarrativePacingOptions(), random.Random(1))
        self.assertEqual(len(inserts), 1)
        at, extra = inserts[0]
        self.assertAlmostEqual(at, speech * marks[1] / len(text), delta=0.05)
        self.assertTrue(0.1 < extra < 0.3)


    def test_rushed_commas_get_a_floor_only(self):
        text = "Một hai ba bốn năm sáu bảy tám, chín mười mười một mười hai mười ba mười bốn mười lăm mười sáu."
        speech = 6.0
        audio = tone(speech)
        centre = speech * text.index(",") / len(text)
        audio[int((centre - 0.07) * RATE):int((centre + 0.07) * RATE)] = 0  # 0.14 s comma
        unit = PacingUnit(0.0, speech, text)
        silence = SilenceMap(audio, RATE)
        floor = NarrativePacingOptions(comma_min_pause_ms=250)
        [(at, extra)] = plan_sentence_pauses(silence, unit, floor, random.Random(1))
        self.assertAlmostEqual(at, centre, delta=0.05)
        self.assertAlmostEqual(extra, 0.11, delta=0.03)
        self.assertEqual(plan_sentence_pauses(silence, unit, floor.model_copy(update={"comma_min_pause_ms": 0}),
                                              random.Random(1)), [])

    def test_short_sentences_get_a_longer_beat(self):
        text = ("Một người nói một câu rất dài để kể lại câu chuyện cũ của gia đình mình. Con người ấy là ai? "
                "Chính là bản thân chúng ta, những người vẫn nghe và tin vào câu chuyện ấy mỗi ngày.")
        speech = 9.0
        marks = [text.index(". "), text.index("? ")]
        audio = tone(speech)
        for pos in marks:
            centre = speech * pos / len(text)
            audio[int((centre - 0.1) * RATE):int((centre + 0.1) * RATE)] = 0
        options = NarrativePacingOptions(short_sentence_pause_ms=700)
        inserts = plan_sentence_pauses(SilenceMap(audio, RATE), PacingUnit(0.0, speech, text), options,
                                       random.Random(1))
        self.assertEqual(len(inserts), 2)
        self.assertTrue(all(extra > 0.4 for _, extra in inserts))  # 0.2 s -> about 0.7 s


def topic_script(blocks: int = 6, per_block: int = 5, seconds: float = 50.0):
    vocab = [("phủ đệ", "gia tộc", "lễ giáo"), ("tiểu thuyết", "nhân vật", "tác giả"),
             ("âm nhạc", "phức điệu", "giai điệu"), ("phương đông", "phương tây", "trưởng phòng"),
             ("bản hiệu chú", "chú thích", "tranh màu"), ("Đại Quan Viên", "khu vườn", "kiến trúc")]
    texts = []
    for k in range(blocks):
        a, b, c = vocab[k % len(vocab)]
        for j in range(per_block):
            texts.append(f"Câu chuyện về {a} và {b} còn gắn với {c}, lần thứ {j} chúng ta nhắc lại {a} cùng {b}.")
    return [PacingUnit(i * seconds, i * seconds + seconds - 1, t) for i, t in enumerate(texts)]


class TopicLayerTests(unittest.TestCase):
    def test_vocabulary_change_scores_highest_at_block_edges(self):
        units = topic_script()
        scores = topic_shift_scores(units, "vi")
        edges = {5, 10, 15, 20, 25}
        top = sorted(range(1, len(units)), key=lambda b: -scores[b])[:len(edges)]
        self.assertEqual(set(top), edges)

    def test_sections_avoid_music_and_respect_spacing(self):
        units = topic_script()
        scores = [0.5] * len(units)
        for b, value in ((5, 1.3), (10, 1.2), (15, 1.9), (20, 1.4), (21, 1.35), (25, 1.1)):
            scores[b] = value
        options = NarrativePacingOptions(section_interval_minutes=4)
        sections = plan_sections(units, scores, options, reserved={15})
        self.assertTrue(sections)
        self.assertNotIn(15, sections)
        self.assertEqual(sections, [5, 10, 20, 25])  # 21 is too close to 20, 15 holds music
        starts = sorted(units[b].start for b in sections + [15])
        self.assertTrue(all(b - a >= 0.45 * 240 for a, b in pairwise(starts)))
        explicit = plan_sections(units, scores, options.model_copy(update={"section_before_units": [8, 16]}), {15})
        self.assertEqual(explicit, [7])

    def test_section_boundary_gets_the_long_silence(self):
        texts = [("Câu chuyện về phủ đệ và gia tộc, lễ giáo " if i < 5 else
                  "Tiểu thuyết có nhân vật và tác giả, sáng tác ") + LONG for i in range(10)]
        audio, units = narration(texts, seconds=40.0)
        options = NarrativePacingOptions(enabled=True, jitter_ms=0, sentence_pauses_enabled=False,
                                         section_before_units=[6])
        result = apply_narrative_pacing(audio, RATE, units, options)
        gap = result.remap(units[5].start) - result.remap(units[4].end)
        self.assertAlmostEqual(gap, 2.0, delta=0.02)  # sections are not length-scaled
        self.assertEqual([s["before_unit"] for s in result.report["sections"]], [6])
        self.assertEqual(result.report["boundary_kinds"]["section"], 1)


class RendererTests(unittest.TestCase):
    def test_pauses_follow_tiers_and_speech_is_untouched(self):
        audio, units = narration(["Mở đầu" + LONG, "Nhưng rồi" + LONG, "Trước hết, ta xem" + LONG])
        options = NarrativePacingOptions(enabled=True, jitter_ms=0, sentence_pauses_enabled=False)
        result = apply_narrative_pacing(audio, RATE, units, options)
        voiced = np.abs(result.audio) > 0
        np.testing.assert_array_equal(result.audio[voiced], audio[np.abs(audio) > 0])
        gaps = [result.remap(units[i].start) - result.remap(units[i - 1].end) for i in (1, 2)]
        short_paragraph = 0.9  # both paragraphs are short: 0.9x the tier length
        self.assertAlmostEqual(gaps[0], 0.60 * short_paragraph, delta=0.02)
        self.assertAlmostEqual(gaps[1], 1.30 * short_paragraph, delta=0.02)
        self.assertEqual(result.report["music"], [])
        onset = int(result.remap(units[2].start) * RATE)
        self.assertGreater(abs(result.audio[onset + 5]), 0)

    def test_long_bridge_plays_longer_than_short_bridge(self):
        texts = ["Có bao giờ" + LONG, "Hôm nay" + LONG, "Bây giờ" + LONG, "Trước hết" + LONG]
        audio, units = narration(texts, seconds=20.0)
        with TemporaryDirectory() as temp:
            library = library_with_music(Path(temp))
            music = NarrativeMusicOptions(enabled=True, selection_mode="random_theme", theme="co-trang",
                                          theme_track_id="series-theme", intro_before_unit=None,
                                          hook_min_seconds=300, outro_enabled=False,
                                          bridge_before_units=[2, 4], major_before_units=[3])
            options = NarrativePacingOptions(enabled=True, sentence_pauses_enabled=False, music=music)
            result = apply_narrative_pacing(audio, RATE, units, options, library=library)
        heard = {m["before_unit"]: (m["length"], m["heard_seconds"]) for m in result.report["music"]}
        self.assertEqual({k: v[0] for k, v in heard.items()}, {2: "short", 3: "long", 4: "short"})
        self.assertGreater(heard[3][1], heard[2][1] + 4)  # ~10.5 s vs ~5-6 s
        self.assertEqual(result.report["music"][1]["track_id"], "series-theme")

    def test_long_pool_rotates_keeps_closing_track_and_short_solo_is_capped(self):
        texts = ["Có bao giờ" + LONG] + ["Hôm nay" + LONG] * 4 + ["Và đến đây, chúng ta tạm khép lại" + LONG]
        audio, units = narration(texts, seconds=20.0)
        with TemporaryDirectory() as temp:
            root = Path(temp)
            library = library_with_music(root)
            for track_id, tags in (("long-a", []), ("long-b", []), ("long-end", ["closing"])):
                source = root / f"{track_id}.wav"
                t = np.arange(16 * RATE) / RATE
                sf.write(source, 0.2 * np.sin(2 * np.pi * 262 * t), RATE)
                library.import_track(source, track_id, track_id=track_id, themes=["chuyen-chuong"], tags=tags)
            music = NarrativeMusicOptions(enabled=True, selection_mode="fixed", track_id="bridge-a",
                                          hook_min_seconds=300, max_solo_ms=2500, major_theme="chuyen-chuong",
                                          bridge_before_units=[2, 3, 4, 5, 6], major_before_units=[3, 5, 6])
            options = NarrativePacingOptions(enabled=True, sentence_pauses_enabled=False, music=music)
            result = apply_narrative_pacing(audio, RATE, units, options, library=library)
        by_unit = {m["before_unit"]: m for m in result.report["music"]}
        longs = [by_unit[u]["track_id"] for u in (3, 5)]
        self.assertEqual(sorted(longs), ["long-a", "long-b"])          # rotated, no repeat
        self.assertEqual(by_unit[6]["track_id"], "long-end")             # closing words get the ending
        self.assertLessEqual(by_unit[2]["heard_seconds"], 1.0 + 2.5 + 0.35 + 1.6 + 0.05)  # capped solo
        pinned = music.model_copy(update={"bridge_tracks": {4: "bridge-b", 5: "long-end"}})
        with TemporaryDirectory() as temp:
            library = library_with_music(Path(temp))
            for track_id in ("long-a", "long-b", "long-end"):
                source = Path(temp) / f"{track_id}.wav"
                sf.write(source, 0.2 * np.sin(2 * np.pi * 262 * np.arange(16 * RATE) / RATE), RATE)
                library.import_track(source, track_id, track_id=track_id, themes=["chuyen-chuong"])
            result = apply_narrative_pacing(audio, RATE, units, options.model_copy(update={"music": pinned}),
                                            library=library)
        by_unit = {m["before_unit"]: m for m in result.report["music"]}
        self.assertEqual((by_unit[4]["track_id"], by_unit[5]["track_id"]), ("bridge-b", "long-end"))

    def test_hook_is_dry_theme_enters_at_series_intro_and_bridges_overlap_voice(self):
        texts = ["Có bao giờ" + LONG, "Đây là series podcast" + LONG, "Hôm nay" + LONG, "Bây giờ" + LONG]
        audio, units = narration(texts, seconds=20.0)
        with TemporaryDirectory() as temp:
            library = library_with_music(Path(temp))
            music = NarrativeMusicOptions(enabled=True, selection_mode="random_theme", theme="co-trang",
                                          theme_track_id="series-theme", bridge_before_units=[4])
            options = NarrativePacingOptions(enabled=True, sentence_pauses_enabled=False, music=music)
            result = apply_narrative_pacing(audio, RATE, units, options, library=library)
        kinds = [(m["kind"], m.get("before_unit")) for m in result.report["music"]]
        self.assertEqual(kinds, [("theme", 2), ("bridge", 4), ("outro", None)])
        hook = int((units[0].end - 1.2) * RATE)
        np.testing.assert_array_equal(result.audio[:hook], audio[:hook])
        def window(signal, at, length=0.3):
            i = int(round(at * RATE))
            return signal[i:i + int(length * RATE)]

        voice_end = result.remap(units[2].end)
        tail = window(result.audio, voice_end - 0.3) - window(audio, units[2].end - 0.3)
        self.assertGreater(np.max(np.abs(tail)), 1e-4)       # music rises under the last words
        voice_in = result.remap(units[3].start)
        overlap = window(result.audio, voice_in + 0.2) - window(audio, units[3].start + 0.2)
        self.assertGreater(np.max(np.abs(overlap)), 1e-4)    # and sinks under the first words
        late = window(result.audio, voice_in + 2.5) - window(audio, units[3].start + 2.5)
        self.assertLess(np.max(np.abs(late)), 1e-6)          # then is fully gone
        self.assertGreater(len(result.audio), len(audio) + 10 * RATE)  # theme solo + outro

    def test_long_bridges_mark_the_biggest_turns_and_the_closing(self):
        texts = ["Hook" + LONG] + [("Bây giờ" if i % 4 == 0 else "Có lẽ") + LONG for i in range(1, 90)]
        texts[-1] = "Và đến đây, chúng ta tạm khép lại" + LONG
        units = [PacingUnit(i * 60.0, i * 60.0 + 55, t) for i, t in enumerate(texts)]
        plan = plan_bridges(units, NarrativeMusicOptions(enabled=True, major_interval_minutes=30), "vi")
        self.assertIn(89, plan.majors_before)
        self.assertTrue(set(plan.majors_before) <= set(plan.bridges_before))
        self.assertGreater(len(plan.bridges_before), len(plan.majors_before))
        starts = sorted(units[b].start for b in plan.majors_before)
        self.assertTrue(all(b - a >= 0.6 * 1800 for a, b in pairwise(starts)))
        explicit = plan_bridges(units, NarrativeMusicOptions(enabled=True, bridge_before_units=[10, 30],
                                                             major_before_units=[50]), "vi")
        self.assertEqual((explicit.bridges_before, explicit.majors_before), ([9, 29, 49], [49]))

    def test_auto_plan_prefers_markers_and_closing(self):
        texts = ["Hook" + LONG] + [("Bây giờ" if i % 4 == 0 else "Có lẽ") + LONG for i in range(1, 40)]
        texts[-1] = "Và đến đây, chúng ta tạm khép lại" + LONG
        units = [PacingUnit(i * 60.0, i * 60.0 + 55, t) for i, t in enumerate(texts)]
        plan = plan_bridges(units, NarrativeMusicOptions(enabled=True, interval_minutes=10), "vi")
        self.assertIn(39, plan.bridges_before)
        self.assertTrue(all(texts[b].startswith("Bây giờ") for b in plan.bridges_before[:-1]))
        self.assertGreaterEqual(len(plan.bridges_before), 3)


class ExistingOutputTests(unittest.TestCase):
    def test_repace_writes_audio_srt_chapters_and_report(self):
        audio, units = narration(["Mở đầu" + LONG, "Nhưng rồi" + LONG, "Trước hết" + LONG])
        with TemporaryDirectory() as temp:
            root = Path(temp)
            wav, srt = root / "talk.wav", root / "talk.srt"
            sf.write(wav, audio, RATE)
            write_srt(srt, [SegmentTiming(index=i + 1, text=u.text, start_seconds=u.start, end_seconds=u.end)
                            for i, u in enumerate(units)])
            out = repace_existing_output(wav, srt, NarrativePacingOptions(), output_dir=root / "out")
            paced = read_srt_units(Path(out["srt_path"]))
            self.assertEqual(len(paced), 3)
            self.assertGreater(out["paced_seconds"], out["source_seconds"])
            self.assertGreater(paced[2].start - paced[1].end, 1.0)
            self.assertTrue(Path(out["chapters_path"]).read_text(encoding="utf-8").startswith("0:00"))
            self.assertIn("boundary_kinds", json.loads(Path(out["report_path"]).read_text(encoding="utf-8")))


class ServiceIntegrationTests(unittest.TestCase):
    def test_merged_text_job_is_paced_and_srt_shifted(self):
        text = "\n\n".join(["Mở đầu" + LONG, "Trước hết, ta xem" + LONG, "Có lẽ" + LONG])
        with TemporaryDirectory() as temp:
            service, _ = fake_service(Path(temp))
            base = dict(text=text, model_id="fake", output_mode="merged", output_srt=True,
                        output_dir=Path(temp) / "out", paragraph_pause_ms=300)
            plain = service.generate_audio(GenerateSpeechRequest(**base, output_stem="plain"))
            paced = service.generate_audio(GenerateSpeechRequest(
                **base, output_stem="paced", narrative_pacing=NarrativePacingOptions(enabled=True)))
            self.assertIsNone(plain.pacing_report_path)
            self.assertTrue(paced.pacing_report_path.is_file())
            self.assertGreater(paced.duration_seconds, plain.duration_seconds + 0.8)
            cues = read_srt_units(paced.srt_path)
            self.assertGreater(cues[1].start - cues[0].end, 1.0)


if __name__ == "__main__":
    unittest.main()
