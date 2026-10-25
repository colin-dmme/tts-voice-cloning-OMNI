import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import soundfile as sf

from omni_tts_core.chapter_music import (
    ChapterMusicLibrary,
    ChapterMusicRenderer,
    prepare_master,
    preview_chapter_music,
)
from omni_tts_core.engines.base import TtsEngineResult
from omni_tts_shared.epub import ChapterMusicOptions
from omni_tts_shared.errors import ConfigError
from omni_tts_shared.schemas import GenerateSpeechRequest
from tests.test_epub import fake_service, make_epub


def add_test_music(root):
    rate = 24000
    source = root / "source.wav"
    sound = 0.2 * np.sin(2 * np.pi * 330 * np.arange(rate * 4) / rate)
    sf.write(
        source, np.concatenate([np.zeros(rate // 5), sound, np.zeros(rate // 2)]), rate
    )
    library = ChapterMusicLibrary(root / "library")
    track = library.import_track(source, "Test phrase", track_id="test-music")
    return library, track


class ChapterMusicTests(unittest.TestCase):
    def test_srt_uses_real_pcm_gap_lengths_for_non_integral_sample_counts(self):
        from omni_tts_core.epub_generation import _read_timings
        from omni_tts_core.text.source_reader import SourceUnit

        rate = 22050
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            library, track = add_test_music(root)
            service, _ = fake_service(root)

            class Engine:
                def generate_batch(self, requests, **kwargs):
                    return [
                        TtsEngineResult(
                            audio=np.full(22050, 0.25, dtype=np.float32),
                            sample_rate=22050,
                        )
                        for _ in requests
                    ]

            service._engines["fake"] = Engine()
            units = [
                SourceUnit(i + 1, "Một câu thử.", 333 if i < 99 else 0, "title")
                for i in range(100)
            ]
            request = GenerateSpeechRequest(
                text="test",
                model_id="fake",
                language="vi",
                output_mode="merged",
                output_srt=True,
                output_dir=root / "out",
                epub_options={
                    "music": {
                        "enabled": True,
                        "track_id": track.track_id,
                        "after_title": True,
                    }
                },
            )
            with patch(
                "omni_tts_core.chapter_music.default_music_root",
                return_value=library.root,
            ):
                result = service.generate_audio(request, source_units=units)
            timings = _read_timings(result.srt_path, 0)
            self.assertLess(
                abs(timings[-1].end_seconds - result.duration_seconds), 0.001
            )
            self.assertAlmostEqual(
                result.duration_seconds,
                (100 * rate + 99 * int(rate * 0.333)) / rate,
                places=6,
            )

    def test_import_trim_levels_and_exact_preview_length(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            library, track = add_test_music(root)
            self.assertLess(track.duration_seconds, 4.5)
            self.assertGreater(track.duration_seconds, 4.0)
            path = preview_chapter_music(
                track.track_id, duration_ms=1200, volume_percent=30, library=library
            )
            audio, rate = sf.read(path)
            self.assertEqual(len(audio), round(1.2 * rate))
            self.assertEqual(audio[0], 0)
            self.assertAlmostEqual(audio[-1], 0, places=5)
            self.assertGreater(np.max(np.abs(audio)), 0.01)
            self.assertLess(np.max(np.abs(audio)), 0.26)

    def test_short_slot_fades_resampling_padding_and_volume(self):
        with tempfile.TemporaryDirectory() as temp:
            library, track = add_test_music(Path(temp))
            loud = ChapterMusicRenderer(
                ChapterMusicOptions(track_id=track.track_id, volume_percent=60), library
            )
            quiet = ChapterMusicRenderer(
                ChapterMusicOptions(track_id=track.track_id, volume_percent=30), library
            )
            for rate in (22050, 24000, 44100, 48000):
                with self.subTest(rate=rate):
                    a, b = loud.render(2500, rate), quiet.render(2500, rate)
                    self.assertEqual(len(a), int(rate * 2.5))
                    np.testing.assert_allclose(a, b * 2)
                    tiny = loud.render(5, rate)
                    self.assertEqual(len(tiny), int(rate * 0.005))
                    self.assertTrue(np.isfinite(tiny).all())
                    self.assertAlmostEqual(tiny[-1], 0, places=5)
            long = loud.render(10000, 24000)
            self.assertEqual(len(long), 240000)
            self.assertTrue(np.all(long[120000:] == 0))
            self.assertEqual(len(loud.render(0, 24000)), 0)

    def test_rejects_silence_and_missing_track(self):
        with self.assertRaises(ConfigError):
            prepare_master(np.zeros(100), 24000)
        with tempfile.TemporaryDirectory() as temp:
            lib = ChapterMusicLibrary(Path(temp))
            with self.assertRaises(ConfigError):
                lib.resolve("missing")
            with self.assertRaises(ConfigError):
                preview_chapter_music("missing", duration_ms=0, library=lib)

    def test_music_replaces_pause_only_and_srt_stays_identical_at_each_rate(self):
        for rate in (22050, 24000, 48000):
            with self.subTest(rate=rate), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                library, track = add_test_music(root)
                source = make_epub(root / "book.epub")
                service, _ = fake_service(root)

                class Engine:
                    def __init__(self, sample_rate):
                        self.sample_rate = sample_rate

                    def generate_batch(self, requests, **kwargs):
                        return [
                            TtsEngineResult(
                                audio=np.full(self.sample_rate, 0.25, dtype=np.float32),
                                sample_rate=self.sample_rate,
                            )
                            for _ in requests
                        ]

                service._engines["fake"] = Engine(rate)
                base = {
                    "text": "file",
                    "model_id": "fake",
                    "language": "vi",
                    "output_dir": root / "out",
                    "output_srt": True,
                    "chunk_join_mode": "direct",
                    "max_chunk_chars": 800,
                }
                plain = GenerateSpeechRequest(
                    **base,
                    epub_options={"include_volumes": False, "output_mode": "merged"},
                )
                musical = GenerateSpeechRequest(
                    **base,
                    epub_options={
                        "include_volumes": False,
                        "output_mode": "merged",
                        "music": {
                            "enabled": True,
                            "track_id": track.track_id,
                            "after_title": True,
                        },
                    },
                )
                with patch(
                    "omni_tts_core.chapter_music.default_music_root",
                    return_value=library.root,
                ):
                    a = service.generate_from_source_file(source, plain)
                    b = service.generate_from_source_file(source, musical)
                dry, _ = sf.read(a.audio_path)
                wet, _ = sf.read(b.audio_path)
                self.assertEqual(len(dry), len(wet))
                self.assertEqual(
                    a.srt_path.read_text(encoding="utf-8"),
                    b.srt_path.read_text(encoding="utf-8"),
                )
                np.testing.assert_array_equal(dry[:rate], wet[:rate])
                np.testing.assert_array_equal(
                    dry[int(2.2 * rate) : int(3.2 * rate)],
                    wet[int(2.2 * rate) : int(3.2 * rate)],
                )
                self.assertGreater(np.max(np.abs(wet[rate : int(2.2 * rate)])), 0.01)
                self.assertGreater(
                    np.max(np.abs(wet[int(5.4 * rate) : int(7.9 * rate)])), 0.01
                )
                self.assertTrue(
                    np.all(wet[int(3.2 * rate) : int(4.4 * rate)] == 0)
                )  # scene stays silent


class MusicUiTests(unittest.TestCase):
    def test_disabled_music_does_not_change_historical_default_settings(self):
        import os

        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication

        from omni_tts_shared.epub import EpubOptions
        from omni_tts_ui_qt.widgets.epub_options import EpubOptionsWidget

        app = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as temp:
            library, track = add_test_music(Path(temp))
            with patch(
                "omni_tts_core.chapter_music.default_music_root",
                return_value=library.root,
            ):
                editor = EpubOptionsWidget()
                self.assertEqual(editor.options(), EpubOptions().model_dump())
                options = EpubOptions(
                    music={
                        "enabled": True,
                        "track_id": track.track_id,
                        "volume_percent": 42,
                        "after_title": True,
                    }
                )
                editor.set_options(options.model_dump())
                self.assertEqual(editor.options(), options.model_dump())
                editor.close()
        app.processEvents()


class MusicProtocolTests(unittest.IsolatedAsyncioTestCase):
    async def test_library_import_list_and_preview_via_mcp(self):
        try:
            from mcp import Client
        except ImportError:
            self.skipTest("MCP extra not installed")
        from colin_studio_tts_mcp.server import mcp

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "clip.wav"
            sf.write(source, np.sin(np.arange(48000) * 0.07) * 0.15, 24000)
            with patch(
                "omni_tts_core.chapter_music.default_music_root",
                return_value=root / "library",
            ):
                async with Client(mcp) as client:
                    item = await client.call_tool(
                        "import_chapter_music",
                        {"source_file": str(source), "name": "Imported phrase"},
                    )
                    track_id = item.structured_content["track_id"]
                    tracks = await client.call_tool("list_chapter_music", {})
                    self.assertEqual(tracks.structured_content["count"], 1)
                    cue = await client.call_tool(
                        "preview_chapter_music",
                        {"track_id": track_id, "duration_ms": 1200},
                    )
                    self.assertEqual(
                        sf.info(cue.structured_content["audio_path"]).frames, 28800
                    )


if __name__ == "__main__":
    unittest.main()
