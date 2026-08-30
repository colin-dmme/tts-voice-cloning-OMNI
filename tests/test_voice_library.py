from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from omni_tts_core.designed_voices import DesignedVoiceStore
from omni_tts_core.voice_library import (
    build_voice_items,
    filter_voice_items,
    group_by_project,
    list_projects,
    list_tags,
)
from omni_tts_shared.schemas import DesignedVoice, VoiceProfile


def _profile(pid, name, project="", tags=None, dur=8.0):
    return VoiceProfile(
        profile_id=pid,
        name=name,
        audio_path=Path(f"{pid}.wav"),
        project=project,
        tags=tags or [],
        duration_seconds=dur,
    )


def _design(did, name, instruct, project="", tags=None):
    return DesignedVoice(
        designed_voice_id=did, name=name, instruct=instruct, project=project, tags=tags or []
    )


class VoiceLibraryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.items = build_voice_items(
            [
                _profile("p1", "Ads Nam", project="ads", tags=["nam", "quang-cao"]),
                _profile("p2", "Cô Tấm", project="truyen", tags=["nu"]),
            ],
            [
                _design("d1", "Nữ tin tức", "female, news anchor", project="ads", tags=["nu"]),
            ],
        )

    def test_build_marks_kinds(self) -> None:
        kinds = {i.item_id: i.kind for i in self.items}
        self.assertEqual(kinds, {"p1": "clone", "p2": "clone", "d1": "design"})

    def test_filter_by_kinds(self) -> None:
        clone_only = filter_voice_items(self.items, kinds=("clone",))
        self.assertEqual({i.item_id for i in clone_only}, {"p1", "p2"})

    def test_filter_by_project_and_tag(self) -> None:
        ads = filter_voice_items(self.items, project="ads")
        self.assertEqual({i.item_id for i in ads}, {"p1", "d1"})
        nu = filter_voice_items(self.items, tag="nu")
        self.assertEqual({i.item_id for i in nu}, {"p2", "d1"})

    def test_query_matches_name_project_tag_subtitle(self) -> None:
        self.assertEqual(
            {i.item_id for i in filter_voice_items(self.items, query="tấm")}, {"p2"}
        )
        self.assertEqual(
            {i.item_id for i in filter_voice_items(self.items, query="news")}, {"d1"}
        )
        self.assertEqual(
            {i.item_id for i in filter_voice_items(self.items, query="ads")}, {"p1", "d1"}
        )

    def test_projects_and_tags_listing(self) -> None:
        self.assertEqual(list_projects(self.items), ["ads", "truyen"])
        self.assertEqual(list_tags(self.items), ["nam", "nu", "quang-cao"])

    def test_group_by_project(self) -> None:
        groups = group_by_project(self.items)
        self.assertEqual(set(groups), {"ads", "truyen"})
        self.assertEqual({i.item_id for i in groups["ads"]}, {"p1", "d1"})


class DesignedVoiceStoreTests(unittest.TestCase):
    def test_crud_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = DesignedVoiceStore(store_dir=Path(tmp))
            voice = store.save_voice(
                name="Nữ trầm", instruct="female, low pitch", project="ads", tags=["nu", "nu"]
            )
            self.assertEqual(voice.tags, ["nu"])  # deduped
            self.assertEqual([v.name for v in store.list_voices()], ["Nữ trầm"])
            self.assertEqual(store.get_voice(voice.designed_voice_id).instruct, "female, low pitch")
            store.delete_voice(voice.designed_voice_id)
            self.assertEqual(store.list_voices(), [])

    def test_requires_name_and_instruct(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = DesignedVoiceStore(store_dir=Path(tmp))
            with self.assertRaises(Exception):
                store.save_voice(name="", instruct="x")
            with self.assertRaises(Exception):
                store.save_voice(name="x", instruct="  ")


if __name__ == "__main__":
    unittest.main()
