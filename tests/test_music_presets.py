import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from omni_tts_core.chapter_music import ChapterMusicSelector
from omni_tts_shared.epub import ChapterMusicOptions
from omni_tts_shared.errors import ConfigError
from omni_tts_shared.schemas import GenerateSpeechRequest
from tests.test_epub import fake_service, make_epub
from tests.test_music_themes import make_library


class MusicPresetTests(unittest.TestCase):
    def test_editing_preset_candidates_marks_completed_queue_outdated(self):
        from types import SimpleNamespace

        from omni_tts_core.file_queue import (
            FileQueueStatus,
            FileQueueStore,
            queue_settings_fingerprint,
        )
        from omni_tts_core.generation_history import GenerationHistoryStore
        from omni_tts_core.music_presets import MusicPresetStore
        from omni_tts_core.ui_presenters.settings_state import GenerationSettings
        from omni_tts_ui_qt.pages.queue_controller import QueueController

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            library = make_library(root)
            store = MusicPresetStore(library)
            preset = store.save("Queue mix", track_ids=["cue-0"])
            source = root / "story.txt"
            source.write_text("text", encoding="utf-8")
            output = root / "old.wav"
            output.write_bytes(b"audio")
            queue = FileQueueStore(root / "queue.sqlite3")
            item, _ = queue.add(source, 4)
            context = SimpleNamespace(
                controller=SimpleNamespace(
                    preview_pronunciation=lambda text, selection: SimpleNamespace(
                        snapshot_hash="same"
                    )
                )
            )
            controller = QueueController(
                context, GenerationHistoryStore(root / "history.sqlite3"), store=queue
            )
            settings = GenerationSettings(
                epub_options={
                    "music": {
                        "enabled": True,
                        "selection_mode": "preset",
                        "preset_id": preset.preset_id,
                    }
                }
            )
            with patch(
                "omni_tts_core.chapter_music.default_music_root",
                return_value=library.root,
            ):
                fingerprint = queue_settings_fingerprint(
                    controller._settings_payload(settings), "same"
                )
                queue.mark_running(item.item_id)
                queue.mark_done(
                    item.item_id,
                    job_id="old",
                    output_paths=[output],
                    fingerprint=fingerprint,
                )
                store.save("Renamed", preset_id=preset.preset_id, track_ids=["cue-0"])
                controller.mark_settings_outdated(settings)
                self.assertEqual(queue.get(item.item_id).status, FileQueueStatus.DONE)
                store.save("Renamed", preset_id=preset.preset_id, track_ids=["cue-3"])
                controller.mark_settings_outdated(settings)
                self.assertEqual(
                    queue.get(item.item_id).status, FileQueueStatus.OUTDATED
                )

    def test_union_deduplicates_overlapping_themes_and_respects_unchecked_tracks(self):
        with tempfile.TemporaryDirectory() as temp:
            library = make_library(Path(temp))
            library.update_metadata("cue-0", themes=["tam-quoc", "ngon-tinh"])
            library.update_metadata("cue-2", themes=["huyen-huyen"])
            options = ChapterMusicOptions(
                selection_mode="random_selection",
                theme_ids=["tam-quoc", "ngon-tinh"],
                track_ids=["cue-2", "cue-0"],
                excluded_track_ids=["cue-1"],
                random_seed=31,
            )
            chooser = ChapterMusicSelector(options, library, context="book")
            self.assertEqual(
                [t.track_id for t in chooser.pool], ["cue-0", "cue-2", "cue-3"]
            )
            draws = [chooser.choose(f"chapter:{i}").track_id for i in range(30)]
            self.assertEqual(set(draws), {"cue-0", "cue-2", "cue-3"})
            self.assertTrue(
                all(len(set(draws[i : i + 3])) == 3 for i in range(0, 30, 3))
            )

    def test_preset_crud_keeps_id_and_uses_exclusions_after_reload(self):
        from omni_tts_core.music_presets import MusicPresetStore

        with tempfile.TemporaryDirectory() as temp:
            library = make_library(Path(temp))
            store = MusicPresetStore(library)
            saved = store.save(
                "Tam Quốc và tình cảm",
                theme_ids=["tam-quoc", "ngon-tinh"],
                excluded_track_ids=["cue-1"],
            )
            reloaded = MusicPresetStore(library).get(saved.preset_id)
            self.assertEqual(reloaded.name, "Tam Quốc và tình cảm")
            self.assertEqual(reloaded.excluded_track_ids, ["cue-1"])
            updated = store.save(
                "Đổi tên", preset_id=saved.preset_id, track_ids=["cue-2", "cue-3"]
            )
            self.assertEqual(updated.preset_id, saved.preset_id)
            with self.assertRaises(ConfigError):
                store.save("đổi tên", track_ids=["cue-0"])
            chooser = ChapterMusicSelector(
                ChapterMusicOptions(selection_mode="preset", preset_id=saved.preset_id),
                library,
            )
            self.assertEqual([t.track_id for t in chooser.pool], ["cue-2", "cue-3"])
            self.assertTrue(store.delete(saved.preset_id))
            with self.assertRaises(ConfigError):
                ChapterMusicSelector(chooser.options, library)

    def test_empty_or_missing_collection_rejected_before_playback(self):
        with tempfile.TemporaryDirectory() as temp:
            library = make_library(Path(temp))
            for payload in [
                {"theme_ids": []},
                {"theme_ids": ["missing"]},
                {"track_ids": ["missing"]},
                {
                    "theme_ids": ["tam-quoc"],
                    "excluded_track_ids": ["cue-0", "cue-1", "cue-2"],
                },
            ]:
                with self.subTest(payload=payload), self.assertRaises(ConfigError):
                    ChapterMusicSelector(
                        ChapterMusicOptions(
                            selection_mode="random_selection", **payload
                        ),
                        library,
                    )

    def test_preset_update_invalidates_epub_cache_but_rename_does_not(self):
        from omni_tts_core.music_presets import MusicPresetStore

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            library = make_library(root)
            store = MusicPresetStore(library)
            preset = store.save("My mix", track_ids=["cue-0"])
            source = make_epub(root / "book.epub")
            service, engine = fake_service(root)
            request = GenerateSpeechRequest(
                text="file",
                model_id="fake",
                language="vi",
                output_dir=root / "out",
                output_srt=True,
                epub_options={
                    "include_volumes": False,
                    "output_mode": "merged",
                    "music": {
                        "enabled": True,
                        "selection_mode": "preset",
                        "preset_id": preset.preset_id,
                        "after_title": True,
                    },
                },
            )
            with patch(
                "omni_tts_core.chapter_music.default_music_root",
                return_value=library.root,
            ):
                a = service.generate_from_source_file(source, request)
                before = len(engine.calls)
                store.save("Renamed", preset_id=preset.preset_id, track_ids=["cue-0"])
                b = service.generate_from_source_file(source, request)
                self.assertEqual(before, len(engine.calls))
                self.assertEqual(a.music_plan_path, b.music_plan_path)
                store.save("Renamed", preset_id=preset.preset_id, track_ids=["cue-3"])
                c = service.generate_from_source_file(source, request)
                self.assertGreater(len(engine.calls), before)
                self.assertNotEqual(a.music_plan_path, c.music_plan_path)
                plan = json.loads(c.music_plan_path.read_text(encoding="utf-8"))
                self.assertEqual(plan["candidate_track_ids"], ["cue-3"])

    def test_running_book_uses_frozen_plan_if_preset_deleted_between_chapters(self):
        from omni_tts_core.music_presets import MusicPresetStore

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            library = make_library(root)
            store = MusicPresetStore(library)
            preset = store.save("Frozen", track_ids=["cue-0", "cue-1"])
            source = make_epub(root / "book.epub")
            service, original = fake_service(root)

            class Engine:
                def generate_batch(self, requests, **kwargs):
                    if store.list_presets():
                        store.delete(preset.preset_id)
                    return original.generate_batch(requests, **kwargs)

            service._engines["fake"] = Engine()
            request = GenerateSpeechRequest(
                text="file",
                model_id="fake",
                language="vi",
                output_dir=root / "out",
                epub_options={
                    "include_volumes": False,
                    "music": {
                        "enabled": True,
                        "selection_mode": "preset",
                        "preset_id": preset.preset_id,
                        "after_title": True,
                    },
                },
            )
            with patch(
                "omni_tts_core.chapter_music.default_music_root",
                return_value=library.root,
            ):
                result = service.generate_from_source_file(source, request)
            self.assertTrue(result.audio_path.exists())
            self.assertEqual(len(original.calls), 2)


class MusicPresetProtocolTests(unittest.IsolatedAsyncioTestCase):
    async def test_preset_crud_and_checked_selection_resolve_through_mcp(self):
        try:
            from mcp import Client
        except ImportError:
            self.skipTest("MCP extra not installed")
        from colin_studio_tts_mcp.server import mcp

        with tempfile.TemporaryDirectory() as temp:
            library = make_library(Path(temp))
            with patch(
                "omni_tts_core.chapter_music.default_music_root",
                return_value=library.root,
            ):
                async with Client(mcp) as client:
                    saved = await client.call_tool(
                        "save_chapter_music_preset",
                        {
                            "name": "Mixed",
                            "theme_ids": ["tam-quoc", "ngon-tinh"],
                            "excluded_track_ids": ["cue-1"],
                        },
                    )
                    self.assertFalse(saved.is_error)
                    preset_id = saved.structured_content["preset_id"]
                    resolved = await client.call_tool(
                        "resolve_chapter_music_selection",
                        {"music": {"selection_mode": "preset", "preset_id": preset_id}},
                    )
                    self.assertEqual(
                        [t["track_id"] for t in resolved.structured_content["tracks"]],
                        ["cue-0", "cue-2", "cue-3"],
                    )
                    items = await client.call_tool("list_chapter_music_presets", {})
                    self.assertEqual(items.structured_content["count"], 1)
                    deleted = await client.call_tool(
                        "delete_chapter_music_preset", {"preset_id": preset_id}
                    )
                    self.assertTrue(deleted.structured_content["deleted"])
                    self.assertEqual(len(library.list_tracks()), 4)


if __name__ == "__main__":
    unittest.main()
