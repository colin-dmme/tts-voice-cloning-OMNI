import hashlib
import json
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import numpy as np
import soundfile as sf

from omni_tts_core.audio.wav_tools import read_audio_mono
from omni_tts_core.chapter_music import (
    ChapterMusicLibrary,
    ChapterMusicRenderer,
    preview_chapter_music,
)
from omni_tts_core.engines.base import TtsEngineResult
from omni_tts_core.epub_generation import _read_timings, build_epub_music_plan
from omni_tts_core.text.epub_reader import read_epub
from omni_tts_shared.epub import ChapterMusicOptions, EpubOptions
from omni_tts_shared.schemas import GenerateSpeechRequest
from tests.test_epub import fake_service, make_epub


def full_track_library(root):
    library = ChapterMusicLibrary(root / "library")
    for i, frames in enumerate([123457, 90013, 65011]):
        source = root / f"source-{i}.wav"
        sf.write(source, np.sin(np.arange(frames) * (0.07 + i * 0.013)) * 0.2, 24000)
        library.import_track(
            source, f"Phrase {i}", track_id=f"phrase-{i}", themes=["tam-quoc"]
        )
    return library


class FullChapterMusicTests(unittest.TestCase):
    def test_full_playback_keeps_every_source_sample_and_preview_ignores_slot_length(
        self,
    ):
        with TemporaryDirectory() as temp:
            library = full_track_library(Path(temp))
            options = ChapterMusicOptions(
                track_id="phrase-0",
                duration_mode="full_track",
                fade_in_ms=0,
                fade_out_ms=0,
            )
            renderer = ChapterMusicRenderer(options, library)
            source, rate = sf.read(library.resolve("phrase-0")[1], dtype="float32")

            for slot in [100, 3000, 10000]:
                audio = renderer.render(slot, rate)
                self.assertEqual(len(audio), 123457)
                np.testing.assert_allclose(audio, source * 0.3, atol=1e-7)
            path = preview_chapter_music(
                "phrase-0", duration_ms=0, duration_mode="full_track", library=library
            )
            self.assertEqual(sf.info(path).frames, 123457)

    def test_full_playback_still_respects_disabled_boundary_and_zero_pause(self):
        with TemporaryDirectory() as temp:
            library = full_track_library(Path(temp))
            options = ChapterMusicOptions(
                enabled=True, track_id="phrase-0", duration_mode="full_track"
            )
            renderer = ChapterMusicRenderer(options, library)
            self.assertEqual(len(renderer.for_boundary("chapter", 3000, 24000)), 123457)
            self.assertIsNone(renderer.for_boundary("chapter", 0, 24000))
            self.assertIsNone(renderer.for_boundary("title", 3000, 24000))
            self.assertIsNone(renderer.for_boundary("scene", 3000, 24000))
            renderer = ChapterMusicRenderer(
                options.model_copy(update={"enabled": False}), library
            )
            self.assertIsNone(renderer.for_boundary("chapter", 3000, 24000))

    def test_random_full_plan_reports_each_files_duration_and_configured_pause_separately(
        self,
    ):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            library = full_track_library(root)
            source = make_epub(root / "book.epub")
            options = EpubOptions(
                title_pause_ms=3000,
                chapter_pause_ms=3000,
                music={
                    "enabled": True,
                    "selection_mode": "random_theme",
                    "theme": "tam-quoc",
                    "after_title": True,
                    "duration_mode": "full_track",
                },
            )
            plan = build_epub_music_plan(
                read_epub(source),
                options,
                hashlib.sha256(source.read_bytes()).hexdigest(),
                library=library,
            )
            self.assertEqual(plan["duration_mode"], "full_track")
            self.assertEqual(len(plan["boundaries"]), 3)
            self.assertEqual(len({b["track_id"] for b in plan["boundaries"]}), 3)
            for boundary in plan["boundaries"]:
                self.assertEqual(boundary["configured_pause_ms"], 3000)
                frames = {"phrase-0": 123457, "phrase-1": 90013, "phrase-2": 65011}[
                    boundary["track_id"]
                ]
                self.assertAlmostEqual(boundary["duration_ms"], frames / 24, places=3)

    def test_full_random_epub_srt_and_checkpoint_follow_actual_pcm_at_each_rate(self):
        for rate in [22050, 24000, 48000]:
            with self.subTest(rate=rate), TemporaryDirectory() as temp:
                root = Path(temp)
                library = full_track_library(root)
                source = make_epub(root / "book.epub")
                service, _ = fake_service(root)

                class Engine:
                    def __init__(self, sample_rate):
                        self.rate = sample_rate
                        self.calls = 0

                    def generate_batch(self, requests, **kwargs):
                        self.calls += 1
                        return [
                            TtsEngineResult(
                                audio=np.full(self.rate, 0.25, dtype=np.float32),
                                sample_rate=self.rate,
                            )
                            for _ in requests
                        ]

                engine = Engine(rate)
                service._engines["fake"] = engine
                request = GenerateSpeechRequest(
                    text="file",
                    model_id="fake",
                    language="vi",
                    output_dir=root / "out",
                    output_srt=True,
                    chunk_join_mode="direct",
                    max_chunk_chars=800,
                    epub_options={
                        "include_volumes": False,
                        "output_mode": "merged",
                        "title_pause_ms": 3000,
                        "chapter_pause_ms": 3000,
                        "music": {
                            "enabled": True,
                            "selection_mode": "random_theme",
                            "theme": "tam-quoc",
                            "after_title": True,
                            "duration_mode": "full_track",
                        },
                    },
                )
                with patch(
                    "omni_tts_core.chapter_music.default_music_root",
                    return_value=library.root,
                ):
                    result = service.generate_from_source_file(source, request)
                    audio, audio_rate = sf.read(result.audio_path)
                    # Five one-second speech units, one unchanged 1.2s scene pause,
                    # and one complete occurrence of each of the three library files.
                    music_frames = sum(
                        len(
                            read_audio_mono(
                                library.resolve(track_id)[1], target_sample_rate=rate
                            )[0]
                        )
                        for track_id in ["phrase-0", "phrase-1", "phrase-2"]
                    )
                    expected = rate * 5 + int(rate * 1.2) + music_frames
                    self.assertEqual(audio_rate, rate)
                    self.assertEqual(len(audio), expected)
                    timings = _read_timings(result.srt_path, 0)
                    self.assertEqual(len(timings), 5)
                    self.assertLess(
                        abs(timings[-1].end_seconds - len(audio) / rate), 0.001
                    )
                    plan = json.loads(
                        result.music_plan_path.read_text(encoding="utf-8")
                    )
                    expected_gaps = [
                        plan["boundaries"][0]["duration_ms"] / 1000,
                        1.2,
                        plan["boundaries"][1]["duration_ms"] / 1000,
                        plan["boundaries"][2]["duration_ms"] / 1000,
                    ]
                    for i, gap in enumerate(expected_gaps):
                        self.assertAlmostEqual(
                            timings[i + 1].start_seconds - timings[i].end_seconds,
                            gap,
                            delta=0.0011,
                        )
                    before = engine.calls
                    service.generate_from_source_file(source, request)
                    self.assertEqual(engine.calls, before)

    def test_qt_duration_choice_roundtrips_and_preserves_default_fit_mode(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication

        from omni_tts_ui_qt.widgets.chapter_music import ChapterMusicWidget

        app = QApplication.instance() or QApplication([])
        with TemporaryDirectory() as temp:
            library = full_track_library(Path(temp))
            with patch(
                "omni_tts_core.chapter_music.default_music_root",
                return_value=library.root,
            ):
                widget = ChapterMusicWidget()
                self.assertEqual(widget.options()["duration_mode"], "fit_pause")
                options = ChapterMusicOptions(
                    enabled=True, track_id="phrase-0", duration_mode="full_track"
                )
                widget.set_options(options.model_dump())
                self.assertEqual(widget.options(), options.model_dump())
                self.assertIn("trọn", widget.note.text().casefold())
                widget.close()
        app.processEvents()


class FullMusicProtocolTests(unittest.IsolatedAsyncioTestCase):
    async def test_mcp_full_preview_reports_real_length_and_generation_contract_accepts_mode(
        self,
    ):
        try:
            from mcp import Client
        except ImportError:
            self.skipTest("MCP extra not installed")
        from colin_studio_tts_mcp.server import mcp

        with TemporaryDirectory() as temp:
            library = full_track_library(Path(temp))
            with patch(
                "omni_tts_core.chapter_music.default_music_root",
                return_value=library.root,
            ):
                async with Client(mcp) as client:
                    preview = await client.call_tool(
                        "preview_chapter_music",
                        {
                            "track_id": "phrase-0",
                            "duration_ms": 3000,
                            "duration_mode": "full_track",
                        },
                    )
                    self.assertFalse(preview.is_error)
                    data = preview.structured_content
                    self.assertEqual(sf.info(data["audio_path"]).frames, 123457)
                    self.assertAlmostEqual(data["duration_ms"], 123457 / 24, places=3)
                    self.assertEqual(data["duration_mode"], "full_track")


if __name__ == "__main__":
    unittest.main()
