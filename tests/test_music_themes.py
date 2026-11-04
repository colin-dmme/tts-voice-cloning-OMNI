import hashlib
import json
import os
import tempfile
import unittest
from itertools import pairwise
from pathlib import Path
from unittest.mock import patch

import numpy as np
import soundfile as sf
from pydantic import ValidationError

from omni_tts_core.chapter_music import (
    ChapterMusicLibrary,
    ChapterMusicRenderer,
    ChapterMusicSelector,
)
from omni_tts_core.epub_generation import build_epub_music_plan
from omni_tts_core.text.epub_reader import read_epub
from omni_tts_shared.epub import ChapterMusicOptions, EpubOptions
from omni_tts_shared.errors import ConfigError
from omni_tts_shared.schemas import GenerateSpeechRequest
from tests.test_epub import fake_service, make_epub


def make_library(root):
    library = ChapterMusicLibrary(root / "library")
    for i in range(4):
        source = root / f"source-{i}.wav"
        sf.write(
            source,
            0.2 * np.sin(2 * np.pi * (220 + i * 90) * np.arange(24000 * 4) / 24000),
            24000,
        )
        library.import_track(
            source,
            f"Music {i}",
            track_id=f"cue-{i}",
            description=f"Description {i}",
            themes=["tam-quoc" if i < 3 else "ngon-tinh"],
            tags=["noble"],
        )
    return library


class MusicThemeTests(unittest.TestCase):
    def test_shuffle_bag_stays_in_group_uses_all_and_repeats_stably(self):
        with tempfile.TemporaryDirectory() as temp:
            library = make_library(Path(temp))
            options = ChapterMusicOptions(
                selection_mode="random_theme", theme="tam-quoc", random_seed=34
            )

            def sequence(seed_options):
                selector = ChapterMusicSelector(
                    seed_options, library, context="same-book"
                )
                return [selector.choose(f"chapter:{i + 1}").track_id for i in range(36)]

            a = sequence(options)
            self.assertEqual(a, sequence(options))
            self.assertNotEqual(
                a, sequence(options.model_copy(update={"random_seed": 35}))
            )
            self.assertEqual(set(a), {"cue-0", "cue-1", "cue-2"})
            self.assertTrue(all(x != y for x, y in pairwise(a)))
            self.assertTrue(all(len(set(a[i : i + 3])) == 3 for i in range(0, 36, 3)))

    def test_single_track_empty_group_and_explicit_override(self):
        with tempfile.TemporaryDirectory() as temp:
            library = make_library(Path(temp))
            single = ChapterMusicSelector(
                ChapterMusicOptions(selection_mode="random_theme", theme="ngon-tinh"),
                library,
            )
            self.assertEqual(
                [single.choose(str(i)).track_id for i in range(3)], ["cue-3"] * 3
            )
            for theme in (None, "missing"):
                with self.assertRaises(ConfigError):
                    ChapterMusicSelector(
                        ChapterMusicOptions(selection_mode="random_theme", theme=theme),
                        library,
                    )
            options = ChapterMusicOptions(
                selection_mode="random_theme",
                theme="tam-quoc",
                track_overrides={"title:2": "cue-3"},
            )
            selector = ChapterMusicSelector(options, library)
            self.assertEqual(selector.choose("title:2").track_id, "cue-3")
            self.assertIn(
                selector.choose("chapter:2").track_id, {"cue-0", "cue-1", "cue-2"}
            )
            with self.assertRaises(ValidationError):
                ChapterMusicOptions(track_overrides={"scene:2": "cue-0"})
            with self.assertRaises(ConfigError):
                ChapterMusicSelector(
                    options.model_copy(
                        update={"track_overrides": {"title:2": "missing"}}
                    ),
                    library,
                )

    def test_metadata_catalog_migration_and_companion_do_not_modify_audio(self):
        with tempfile.TemporaryDirectory() as temp:
            library = make_library(Path(temp))
            track, path = library.resolve("cue-0")
            original = path.read_bytes()
            updated = library.update_metadata(
                "cue-0",
                description="Mưu lược · cổ cầm",
                themes=["tam-quoc", "tam-quoc"],
                tags=["strategy"],
            )
            self.assertEqual(updated.themes, ["tam-quoc"])
            self.assertEqual(updated.provenance, track.provenance)
            self.assertEqual(path.read_bytes(), original)
            self.assertIn(
                "Mưu lược · cổ cầm",
                (library.root / "MUSIC_CATALOG.md").read_text(encoding="utf-8"),
            )
            self.assertEqual(
                [
                    t.track_id
                    for t in library.list_tracks(theme="tam-quoc", tag="strategy")
                ],
                ["cue-0"],
            )
            data = json.loads(library.catalog.read_text(encoding="utf-8"))
            data["version"] = 1
            for item in data["tracks"]:
                item.pop("description")
                item.pop("themes")
            library.catalog.write_text(json.dumps(data), encoding="utf-8")
            self.assertEqual(library.list_tracks()[0].description, "")
            self.assertEqual(library.list_tracks()[0].themes, [])
            with self.assertRaises(ConfigError):
                library.update_metadata("cue-0", themes=["../bad"])

    def test_plan_skips_disabled_zero_final_boundaries_and_preserves_book_positions(
        self,
    ):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            library = make_library(root)
            source = make_epub(root / "book.epub")
            book = read_epub(source)
            digest = hashlib.sha256(source.read_bytes()).hexdigest()
            options = EpubOptions(
                music={
                    "enabled": True,
                    "selection_mode": "random_theme",
                    "theme": "tam-quoc",
                    "after_title": True,
                    "track_overrides": {"title:2": "cue-3"},
                }
            )
            plan = build_epub_music_plan(book, options, digest, library=library)
            self.assertEqual(
                [b["key"] for b in plan["boundaries"]],
                ["title:1", "chapter:1", "title:2"],
            )
            self.assertEqual(plan["boundaries"][-1]["track_id"], "cue-3")
            self.assertEqual(
                plan, build_epub_music_plan(book, options, digest, library=library)
            )
            subset = options.model_copy(update={"chapter_start": 2})
            self.assertEqual(
                [
                    b["key"]
                    for b in build_epub_music_plan(
                        book, subset, digest, library=library
                    )["boundaries"]
                ],
                ["title:2"],
            )
            no_titles = options.model_copy(
                update={"title_pause_ms": 0, "chapter_pause_ms": 0}
            )
            self.assertEqual(
                build_epub_music_plan(book, no_titles, digest, library=library)[
                    "boundaries"
                ],
                [],
            )

    def test_random_audio_srt_checkpoint_and_actual_asset_hash_invalidation(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            library = make_library(root)
            source = make_epub(root / "book.epub")
            service, engine = fake_service(root)
            base = {
                "text": "file",
                "model_id": "fake",
                "language": "vi",
                "output_dir": root / "out",
                "output_srt": True,
                "chunk_join_mode": "direct",
                "max_chunk_chars": 800,
            }
            dry_request = GenerateSpeechRequest(
                **base, epub_options={"include_volumes": False, "output_mode": "merged"}
            )
            wet_request = GenerateSpeechRequest(
                **base,
                epub_options={
                    "include_volumes": False,
                    "output_mode": "merged",
                    "music": {
                        "enabled": True,
                        "selection_mode": "random_theme",
                        "theme": "tam-quoc",
                        "random_seed": 23,
                        "after_title": True,
                    },
                },
            )
            with patch(
                "omni_tts_core.chapter_music.default_music_root",
                return_value=library.root,
            ):
                dry = service.generate_from_source_file(source, dry_request)
                wet = service.generate_from_source_file(source, wet_request)
                plan = json.loads(wet.music_plan_path.read_text(encoding="utf-8"))
                self.assertEqual(len({b["track_id"] for b in plan["boundaries"]}), 3)
                dry_audio, rate = sf.read(dry.audio_path)
                wet_audio, _ = sf.read(wet.audio_path)
                self.assertEqual(len(dry_audio), len(wet_audio))
                self.assertEqual(
                    dry.srt_path.read_text(encoding="utf-8"),
                    wet.srt_path.read_text(encoding="utf-8"),
                )
                renderer = ChapterMusicRenderer(wet_request.epub_options.music, library)
                expected = renderer.render(
                    1200, rate, track_id=plan["boundaries"][0]["track_id"]
                )
                np.testing.assert_allclose(
                    wet_audio[rate : int(rate * 2.2)], expected, atol=1 / 32768
                )
                before = len(engine.calls)
                replay = service.generate_from_source_file(source, wet_request)
                self.assertEqual(len(engine.calls), before)
                self.assertEqual(replay.music_plan_path, wet.music_plan_path)
                library.update_metadata("cue-0", description="Edited description only")
                service.generate_from_source_file(source, wet_request)
                self.assertEqual(len(engine.calls), before)
                _, path = library.resolve("cue-0")
                audio, rate = sf.read(path)
                sf.write(path, audio / 2, rate)
                changed = service.generate_from_source_file(source, wet_request)
                self.assertGreater(len(engine.calls), before)
                self.assertNotEqual(changed.music_plan_path, wet.music_plan_path)

    def test_missing_random_group_fails_before_engine_generation(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            library = make_library(root)
            source = make_epub(root / "book.epub")
            service, engine = fake_service(root)
            request = GenerateSpeechRequest(
                text="file",
                model_id="fake",
                epub_options={
                    "music": {
                        "enabled": True,
                        "selection_mode": "random_theme",
                        "theme": "missing",
                    }
                },
            )
            with (
                patch(
                    "omni_tts_core.chapter_music.default_music_root",
                    return_value=library.root,
                ),
                self.assertRaises(ConfigError),
            ):
                service.generate_from_source_file(source, request)
            self.assertEqual(engine.calls, [])

    def test_qt_random_roundtrip_preserves_overrides_and_shows_metadata(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication

        from omni_tts_ui_qt.widgets.chapter_music import ChapterMusicWidget

        app = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as temp:
            library = make_library(Path(temp))
            with patch(
                "omni_tts_core.chapter_music.default_music_root",
                return_value=library.root,
            ):
                widget = ChapterMusicWidget()
                options = ChapterMusicOptions(
                    enabled=True,
                    selection_mode="random_theme",
                    theme="tam-quoc",
                    random_seed=92,
                    track_overrides={"chapter:1": "cue-3"},
                    fade_out_ms=720,
                )
                widget.set_options(options.model_dump())
                self.assertEqual(widget.options(), options.model_dump())
                self.assertFalse(widget.track.isEnabled())
                self.assertTrue(widget.theme.isEnabled())
                widget.set_options(
                    ChapterMusicOptions(enabled=True, track_id="cue-0").model_dump()
                )
                self.assertIn("Description 0", widget.note.text())
                widget.close()
        app.processEvents()


class MusicThemeProtocolTests(unittest.IsolatedAsyncioTestCase):
    async def test_mcp_filters_metadata_and_previews_exact_core_plan(self):
        try:
            from mcp import Client
        except ImportError:
            self.skipTest("MCP extra not installed")

        from colin_studio_tts_mcp.server import mcp

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            library = make_library(root)
            source = make_epub(root / "book.epub")
            with patch(
                "omni_tts_core.chapter_music.default_music_root",
                return_value=library.root,
            ):
                async with Client(mcp) as client:
                    result = await client.call_tool(
                        "list_chapter_music", {"theme": "tam-quoc", "tag": "noble"}
                    )
                    self.assertEqual(result.structured_content["count"], 3)
                    self.assertIn("description", result.structured_content["tracks"][0])
                    updated = await client.call_tool(
                        "update_chapter_music_metadata",
                        {
                            "track_id": "cue-0",
                            "description": "Mưu lược",
                            "tags": ["strategy"],
                        },
                    )
                    self.assertEqual(
                        updated.structured_content["description"], "Mưu lược"
                    )
                    epub = EpubOptions(
                        music={
                            "enabled": True,
                            "selection_mode": "random_theme",
                            "theme": "tam-quoc",
                            "after_title": True,
                        }
                    )
                    planned = await client.call_tool(
                        "plan_epub_music",
                        {"source_file": str(source), "epub": epub.model_dump()},
                    )
                    expected = build_epub_music_plan(
                        read_epub(source),
                        epub,
                        hashlib.sha256(source.read_bytes()).hexdigest(),
                        library=library,
                    )
                    self.assertEqual(planned.structured_content, expected)


if __name__ == "__main__":
    unittest.main()
