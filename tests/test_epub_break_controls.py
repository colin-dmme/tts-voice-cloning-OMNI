import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import soundfile as sf

from omni_tts_core.chapter_music import ChapterMusicLibrary
from omni_tts_core.epub_generation import _read_timings, build_epub_music_plan
from omni_tts_core.text.epub_reader import read_epub
from omni_tts_shared.epub import EpubOptions
from omni_tts_shared.schemas import GenerateSpeechRequest
from tests.test_epub import fake_service, make_epub


def fixture_library(root):
    source = root / "music.wav"
    sf.write(source, np.sin(np.arange(144000) * 0.09) * 0.2, 24000)
    library = ChapterMusicLibrary(root / "library")
    library.import_track(
        source, "Six seconds", track_id="six-seconds", themes=["tam-quoc"]
    )
    return library


class EpubBreakControlsTests(unittest.TestCase):
    def test_qt_loading_new_breaks_keeps_legacy_fields_stable_until_user_edits(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication

        from omni_tts_ui_qt.widgets.epub_options import EpubOptionsWidget

        app = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as temp:
            library = fixture_library(Path(temp))
            options = EpubOptions(
                title_pause_ms=9000,
                chapter_pause_ms=8000,
                music={"track_id": "six-seconds"},
                breaks={
                    "title": {"mode": "silence", "duration_ms": 1000},
                    "chapter": {
                        "mode": "music",
                        "duration_mode": "full_track",
                        "duration_ms": 3000,
                    },
                },
            )
            with patch(
                "omni_tts_core.chapter_music.default_music_root",
                return_value=library.root,
            ):
                editor = EpubOptionsWidget()
                editor.set_options(options.model_dump())
                self.assertEqual(editor.options(), options.model_dump())
                editor.close()
        app.processEvents()

    def test_old_music_settings_resolve_to_independent_breaks(self):
        options = EpubOptions(
            title_pause_ms=1200,
            chapter_pause_ms=3000,
            music={
                "enabled": True,
                "track_id": "six-seconds",
                "duration_mode": "full_track",
                "after_title": False,
                "between_chapters": True,
                "fade_in_ms": 500,
                "fade_out_ms": 700,
            },
        )
        self.assertEqual(options.break_for("title").mode, "silence")
        chapter = options.break_for("chapter")
        self.assertEqual(chapter.mode, "music")
        self.assertEqual(chapter.duration_mode, "full_track")
        self.assertEqual((chapter.fade_in_ms, chapter.fade_out_ms), (500, 700))

    def test_explicit_silence_and_full_music_have_no_stale_global_dependency(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            library = fixture_library(root)
            source = make_epub(root / "book.epub")
            service, _ = fake_service(root)
            options = EpubOptions(
                include_volumes=False,
                output_mode="merged",
                title_pause_ms=9000,
                chapter_pause_ms=9000,
                music={
                    "enabled": False,
                    "track_id": "six-seconds",
                    "after_title": False,
                    "between_chapters": False,
                },
                breaks={
                    "title": {"mode": "silence", "duration_ms": 1000},
                    "chapter": {
                        "mode": "music",
                        "duration_mode": "full_track",
                        "duration_ms": 3000,
                        "fade_in_ms": 250,
                        "fade_out_ms": 750,
                    },
                },
            )
            request = GenerateSpeechRequest(
                text="file",
                model_id="fake",
                language="vi",
                output_dir=root / "out",
                output_srt=True,
                chunk_join_mode="direct",
                max_chunk_chars=800,
                epub_options=options,
            )
            with patch(
                "omni_tts_core.chapter_music.default_music_root",
                return_value=library.root,
            ):
                result = service.generate_from_source_file(source, request)
            audio, rate = sf.read(result.audio_path)
            self.assertEqual(
                len(audio), int(rate * 14.2)
            )  # 5s voice + 1.2s scene + 2x1s silence + 6s music
            timings = _read_timings(result.srt_path, 0)
            self.assertAlmostEqual(
                timings[1].start_seconds - timings[0].end_seconds, 1, places=3
            )
            self.assertAlmostEqual(
                timings[3].start_seconds - timings[2].end_seconds, 6, places=3
            )
            self.assertAlmostEqual(
                timings[4].start_seconds - timings[3].end_seconds, 1, places=3
            )
            self.assertTrue(np.all(audio[rate : 2 * rate] == 0))
            self.assertGreater(
                float(np.max(np.abs(audio[int(5.2 * rate) : int(11.2 * rate)]))), 0.01
            )
            expected_music, _ = sf.read(library.resolve("six-seconds")[1])
            expected_music *= 0.3
            expected_music[:6000] *= np.sin(np.linspace(0, np.pi / 2, 6000)) ** 2
            expected_music[-18000:] *= np.cos(np.linspace(0, np.pi / 2, 18000)) ** 2
            np.testing.assert_allclose(
                audio[124800:268800], expected_music, atol=1 / 32768
            )
            plan = build_epub_music_plan(
                read_epub(source), options, "book", library=library
            )
            self.assertEqual([x["key"] for x in plan["boundaries"]], ["chapter:1"])
            self.assertEqual(plan["boundaries"][0]["duration_ms"], 6000)
            self.assertEqual(plan["boundaries"][0]["fade_in_ms"], 250)
            self.assertEqual(plan["boundaries"][0]["fade_out_ms"], 750)

    def test_music_can_be_full_after_title_and_fixed_between_chapters(self):
        options = EpubOptions(
            music={"track_id": "six-seconds"},
            breaks={
                "title": {
                    "mode": "music",
                    "duration_mode": "full_track",
                    "duration_ms": 0,
                },
                "chapter": {
                    "mode": "music",
                    "duration_mode": "fit_pause",
                    "duration_ms": 2000,
                    "fade_in_ms": 400,
                    "fade_out_ms": 900,
                },
            },
        )
        self.assertTrue(options.uses_music())
        self.assertEqual(options.music_for("title").duration_mode, "full_track")
        self.assertEqual(options.music_for("chapter").duration_mode, "fit_pause")
        self.assertEqual(options.music_for("chapter").fade_out_ms, 900)
        self.assertGreater(options.break_for("title").trigger_ms, 0)

    def test_qt_controls_disable_full_seconds_silent_fades_and_unused_music(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication

        from omni_tts_ui_qt.widgets.epub_options import EpubOptionsWidget

        app = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as temp:
            library = fixture_library(Path(temp))
            with patch(
                "omni_tts_core.chapter_music.default_music_root",
                return_value=library.root,
            ):
                editor = EpubOptionsWidget()
                title = editor.breaks["title"]
                chapter = editor.breaks["chapter"]
                self.assertFalse(editor.music.isEnabled())
                self.assertTrue(title.seconds.isEnabled())
                self.assertFalse(title.fade_in.isEnabled())
                chapter.kind.setCurrentIndex(chapter.kind.findData("music"))
                chapter.duration_mode.setCurrentIndex(
                    chapter.duration_mode.findData("full_track")
                )
                self.assertFalse(chapter.seconds.isEnabled())
                self.assertTrue(chapter.fade_in.isEnabled())
                self.assertTrue(editor.music.isEnabled())
                chapter.duration_mode.setCurrentIndex(
                    chapter.duration_mode.findData("fit_pause")
                )
                chapter.seconds.setValue(2)
                chapter.fade_in.setValue(0.4)
                chapter.fade_out.setValue(0.9)
                selected = EpubOptions.model_validate(editor.options())
                self.assertEqual(selected.break_for("chapter").duration_ms, 2000)
                self.assertEqual(selected.break_for("chapter").fade_in_ms, 400)
                self.assertEqual(selected.break_for("chapter").fade_out_ms, 900)
                editor.titles.setChecked(False)
                editor.volumes.setChecked(False)
                self.assertFalse(title.isEnabled())
                self.assertFalse(editor.pauses["volume_pause_ms"].isEnabled())
                chapter.kind.setCurrentIndex(chapter.kind.findData("silence"))
                self.assertFalse(chapter.fade_out.isEnabled())
                self.assertFalse(editor.music.isEnabled())
                editor.close()
        app.processEvents()

    def test_disabling_music_by_break_ignores_stale_missing_legacy_track(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = make_epub(root / "book.epub")
            service, _ = fake_service(root)
            options = EpubOptions(
                include_volumes=False,
                output_mode="merged",
                music={"enabled": True, "track_id": "missing", "after_title": True},
                breaks={
                    "title": {"mode": "none"},
                    "chapter": {"mode": "silence", "duration_ms": 2000},
                },
            )
            self.assertFalse(options.uses_music())
            result = service.generate_from_source_file(
                source,
                GenerateSpeechRequest(
                    text="file",
                    model_id="fake",
                    language="vi",
                    output_dir=root / "out",
                    chunk_join_mode="direct",
                    max_chunk_chars=800,
                    epub_options=options,
                ),
            )
            self.assertIsNone(result.music_plan_path)
            self.assertAlmostEqual(result.duration_seconds, 8.2, places=5)

    def test_web_disabled_states_match_each_boundary_choice(self):
        from omni_tts_ui_gradio.handlers import (
            epub_break_updates,
            epub_music_source_updates,
        )

        full = epub_break_updates(True, "music", "full_track", 3)
        self.assertFalse(full[2]["interactive"])
        self.assertTrue(full[3]["interactive"])
        self.assertTrue(full[4]["interactive"])
        silent = epub_break_updates(True, "silence", "full_track", 3)
        self.assertTrue(silent[2]["interactive"])
        self.assertFalse(silent[1]["interactive"])
        self.assertFalse(silent[3]["interactive"])
        zero = epub_break_updates(True, 'music', 'fit_pause', 0)
        self.assertFalse(zero[3]['interactive'])
        self.assertFalse(zero[4]['interactive'])
        self.assertFalse(zero[5]['interactive'])
        disabled = epub_break_updates(False, "music", "full_track", 3)
        self.assertTrue(all(not d["interactive"] for d in disabled[:6]))
        sources = epub_music_source_updates(
            False, "music", "full_track", 3, "silence", "fit_pause", 2, "random_theme"
        )
        self.assertTrue(all(not d["interactive"] for d in sources))


class EpubBreakProtocolTests(unittest.IsolatedAsyncioTestCase):
    async def test_mcp_uses_explicit_break_timing_and_fades_with_legacy_music_disabled(
        self,
    ):
        try:
            from mcp import Client
        except ImportError:
            self.skipTest("MCP extra not installed")
        from colin_studio_tts_mcp.contracts import FileGenerationInput
        from colin_studio_tts_mcp.server import mcp

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            library = fixture_library(root)
            source = make_epub(root / "book.epub")
            epub = {
                "music": {"track_id": "six-seconds"},
                "breaks": {
                    "title": {"mode": "silence", "duration_ms": 1000},
                    "chapter": {
                        "mode": "music",
                        "duration_mode": "full_track",
                        "fade_in_ms": 250,
                        "fade_out_ms": 750,
                    },
                },
            }
            request = FileGenerationInput(
                source_files=[str(source)],
                model_id="piper_ngoc_huyen",
                generation={"epub": epub},
            )
            core = request.to_settings().to_request("file")
            self.assertEqual(core.epub_options.break_for("title").duration_ms, 1000)
            self.assertEqual(core.epub_options.music_for("chapter").fade_out_ms, 750)
            with patch(
                "omni_tts_core.chapter_music.default_music_root",
                return_value=library.root,
            ):
                async with Client(mcp) as client:
                    result = await client.call_tool(
                        "plan_epub_music", {"source_file": str(source), "epub": epub}
                    )
                    self.assertFalse(result.is_error)
                    entries = result.structured_content["boundaries"]
                    self.assertEqual(len(entries), 1)
                    self.assertEqual(entries[0]["key"], "chapter:1")
                    self.assertEqual(entries[0]["duration_ms"], 6000)
                    self.assertEqual(entries[0]["fade_in_ms"], 250)
                    self.assertEqual(entries[0]["fade_out_ms"], 750)


if __name__ == "__main__":
    unittest.main()
