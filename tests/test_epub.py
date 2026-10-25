import shutil
import tempfile
import unittest
from pathlib import Path
from threading import Event
from unittest.mock import patch
from zipfile import ZipFile

import numpy as np
import soundfile as sf

from colin_studio_tts_mcp.contracts import FileGenerationInput
from omni_tts_core.engines.base import TtsEngineResult
from omni_tts_core.model_registry import ModelSpec
from omni_tts_core.service import TtsService
from omni_tts_core.text.epub_reader import read_epub
from omni_tts_core.text.source_reader import source_text_stats
from omni_tts_shared.epub import EpubOptions
from omni_tts_shared.errors import ConfigError, GenerationCancelled
from omni_tts_shared.schemas import GenerateSpeechRequest, ModelCapabilities
from tests.test_service_split_batch import DummySettings, FakeRegistry, FakeStorage


def make_epub(path):
    def html(body):
        return (
            '<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops"><head><title>DO NOT READ HEAD TITLE</title></head><body>'
            + body
            + "</body></html>"
        )

    with ZipFile(path, "w") as z:
        z.writestr("mimetype", "application/epub+zip")
        z.writestr(
            "META-INF/container.xml",
            '<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles><rootfile full-path="OPS/book.opf"/></rootfiles></container>',
        )
        z.writestr(
            "OPS/book.opf",
            '<package xmlns="http://www.idpf.org/2007/opf"><metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>Truyện thử</dc:title><dc:language>vi</dc:language></metadata><manifest><item id="two" href="second.xhtml" media-type="application/xhtml+xml"/><item id="toc" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/><item id="part" href="part.xhtml" media-type="application/xhtml+xml"/><item id="one" href="first.xhtml" media-type="application/xhtml+xml"/></manifest><spine><itemref idref="toc"/><itemref idref="part"/><itemref idref="one"/><itemref idref="two"/></spine></package>',
        )
        z.writestr(
            "OPS/nav.xhtml",
            html(
                '<nav epub:type="toc"><a href="first.xhtml">Chương một</a><a href="second.xhtml">Chương hai</a></nav>'
            ),
        )
        z.writestr(
            "OPS/part.xhtml",
            html('<section epub:type="part"><h1>Quyển I</h1></section>'),
        )
        z.writestr(
            "OPS/first.xhtml",
            html(
                '<section epub:type="chapter"><h1>Chương 1: Mở đầu</h1><p>Lâm <em>Phong</em> nhìn quanh.</p><p class="scene">...</p><p>Hắn bước đi.</p><p hidden="hidden">HIDDEN</p><aside epub:type="footnote">FOOTNOTE</aside></section>'
            ),
        )
        z.writestr(
            "OPS/second.xhtml",
            html(
                '<section epub:type="chapter"><h1>Chương 2: Tiếp tục</h1><p>Gió nổi.</p></section>'
            ),
        )
    return path


class OneSecondEngine:
    def __init__(self):
        self.calls = []

    def generate_batch(self, requests, progress_callback=None, **kwargs):
        self.calls.append([r.text for r in requests])
        return [
            TtsEngineResult(
                audio=np.full(24000, 0.25, dtype=np.float32), sample_rate=24000
            )
            for r in requests
        ]


def fake_service(root, provider="qwen"):
    spec = ModelSpec(
        model_id="fake",
        display_name="Test",
        provider=provider,
        model_type="tts",
        local_path=root / "model",
        hf_repo="fake/model",
        language_priority="multilingual",
        capabilities=ModelCapabilities(supported_languages=["vi"]),
    )
    service = TtsService(
        settings=DummySettings(root), registry=FakeRegistry(spec), storage=FakeStorage()
    )
    engine = OneSecondEngine()
    service._engines["fake"] = engine
    return service, engine


class EpubReaderTests(unittest.TestCase):
    def test_spine_order_headings_scene_and_hidden_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = make_epub(Path(tmp) / "book.epub")
            book = read_epub(source)
            self.assertEqual(
                [c.title for c in book.chapters],
                ["Chương 1: Mở đầu", "Chương 2: Tiếp tục"],
            )
            self.assertEqual(book.chapters[0].blocks[0].text, "Lâm Phong nhìn quanh.")
            self.assertEqual(book.chapters[0].blocks[1].role, "scene")
            self.assertEqual(book.chapters[0].volume, "Quyển I")
            combined = str(book)
            self.assertNotIn("HIDDEN", combined)
            self.assertNotIn("FOOTNOTE", combined)
            self.assertNotIn("DO NOT READ", combined)
            self.assertEqual(source_text_stats(source)[1], 2)
            with self.assertRaises(ConfigError):
                book.select(EpubOptions(chapter_start=3))

    def test_contract_roundtrip_preserves_epub_and_rejects_unknown_options(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = make_epub(Path(tmp) / "book.epub")
            request = FileGenerationInput(
                source_files=[str(source)],
                model_id="fake",
                generation={"epub": {"title_pause_ms": 1700, "chapter_pause_ms": 3300}},
            )
            core = request.to_settings().to_request("test")
            self.assertEqual(core.epub_options.title_pause_ms, 1700)
            self.assertEqual(core.epub_options.chapter_pause_ms, 3300)
            with self.assertRaises(ValueError):
                EpubOptions(chapter_start=3, chapter_end=1)
            with self.assertRaises(ValueError):
                EpubOptions(title_pause_ms=-1)


class EpubAudioTests(unittest.TestCase):
    def test_retry_after_later_chapter_fails_keeps_completed_audio(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = make_epub(root / "book.epub")
            service, engine = fake_service(root)
            request = self.request(root)
            generate = engine.generate_batch
            attempts = []

            def fail_second(requests, **kwargs):
                attempts.append(1)
                if len(attempts) == 2:
                    raise RuntimeError("test interruption")
                return generate(requests, **kwargs)

            with (
                patch.object(engine, "generate_batch", side_effect=fail_second),
                self.assertRaises(RuntimeError),
            ):
                service.generate_from_source_file(source, request)
            result = service.generate_from_source_file(source, request)
            self.assertEqual(len(engine.calls), 2)
            self.assertEqual(len(result.item_audio_paths), 2)

    @unittest.skipUnless(shutil.which("ffmpeg"), "MP3 requires ffmpeg")
    def test_mp3_merged_audio_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = make_epub(root / "book.epub")
            service, _engine = fake_service(root)
            request = self.request(root, output_mode="merged").model_copy(
                update={"output_srt": False, "output_audio_format": "mp3"}
            )
            result = service.generate_from_source_file(source, request)
            self.assertEqual(result.audio_path.suffix, ".mp3")
            self.assertGreater(sf.info(result.audio_path).frames, 0)
            self.assertIsNone(result.srt_path)
            self.assertEqual(result.item_srt_paths, [])

    def request(self, root, **options):
        return GenerateSpeechRequest(
            text="file",
            model_id="fake",
            language="vi",
            output_dir=root / "out",
            output_srt=True,
            output_mode="split",
            chunk_join_mode="direct",
            max_chunk_chars=800,
            epub_options={"include_volumes": False, **options},
        )

    def test_exact_pcm_gaps_and_srt_in_per_chapter_and_merged_outputs(self):
        for mode in ("chapters", "merged"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                source = make_epub(root / "book.epub")
                service, engine = fake_service(root)
                result = service.generate_from_source_file(
                    source, self.request(root, output_mode=mode)
                )
                self.assertEqual(len(engine.calls), 2)
                self.assertNotIn(
                    "...", " ".join(t for call in engine.calls for t in call)
                )
                self.assertEqual(
                    len(result.item_audio_paths), 2 if mode == "chapters" else 1
                )
                audio, sr = sf.read(result.audio_path)
                self.assertEqual(sr, 24000)
                self.assertTrue(np.all(audio[24000:52800] == 0))  # title -> body, 1.2 s
                self.assertTrue(np.all(audio[76800:105600] == 0))  # scene, 1.2 s
                self.assertTrue(np.all(audio[129600:189600] == 0))  # chapter, 2.5 s
                srt = result.srt_path.read_text(encoding="utf-8")
                self.assertIn("00:00:02,200 --> 00:00:03,200", srt)
                if mode == "merged":
                    self.assertAlmostEqual(len(audio) / sr, 11.1, places=3)
                    self.assertIn("00:00:07,900 --> 00:00:08,900", srt)
                    self.assertIn("00:00:10,100 --> 00:00:11,100", srt)
                else:
                    self.assertAlmostEqual(len(audio) / sr, 7.9, places=3)
                    self.assertIn(
                        "00:00:00,000 --> 00:00:01,000",
                        result.item_srt_paths[1].read_text(encoding="utf-8"),
                    )

    def test_completed_chapters_are_reused_and_no_titles_or_zero_gaps_are_honoured(
        self,
    ):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = make_epub(root / "book.epub")
            service, engine = fake_service(root)
            request = self.request(
                root, read_titles=False, chapter_pause_ms=0, scene_pause_ms=0
            )
            first = service.generate_from_source_file(source, request)
            second = service.generate_from_source_file(source, request)
            self.assertEqual(len(engine.calls), 2)
            self.assertEqual(first.item_audio_paths, second.item_audio_paths)
            self.assertTrue(
                all("Chương" not in t for call in engine.calls for t in call)
            )
            audio, sr = sf.read(first.audio_path)
            self.assertAlmostEqual(len(audio) / sr, 2.0)

    def test_bounded_chapter_selection_and_cancellation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = make_epub(root / "book.epub")
            service, engine = fake_service(root)
            result = service.generate_from_source_file(
                source, self.request(root, chapter_start=2, chapter_end=2)
            )
            self.assertEqual(len(engine.calls), 1)
            self.assertEqual(len(result.item_srt_paths), 1)
            event = Event()
            event.set()
            with self.assertRaises(GenerationCancelled):
                service.generate_from_source_file(
                    source, self.request(root), cancel_event=event
                )

    def test_boundary_metadata_never_reaches_provider_text(self):
        for provider in (
            "qwen",
            "piper",
            "omnivoice",
            "vieneu",
            "vieneu_v3",
            "zerotts",
            "chatterbox",
            "f5tts",
            "supertonic",
            "higgs_remote",
        ):
            with self.subTest(provider=provider), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                source = make_epub(root / "book.epub")
                service, engine = fake_service(root, provider)
                # Engine-specific preflight is independently covered by provider tests.
                with (
                    patch.object(service, "_ensure_request_can_generate"),
                    patch.object(service, "_cached_prompt_path_for", return_value=None),
                ):
                    result = service.generate_from_source_file(
                        source, self.request(root, chapter_end=1)
                    )
                self.assertTrue(result.srt_path.exists())
                self.assertTrue(
                    all(
                        "[pause" not in t and "<break" not in t
                        for call in engine.calls
                        for t in call
                    )
                )


class EpubMcpTests(unittest.IsolatedAsyncioTestCase):
    async def test_inspect_and_generate_file_over_real_mcp_protocol(self):
        import asyncio
        from types import SimpleNamespace

        try:
            from mcp import Client
        except ImportError:
            self.skipTest("MCP extra not installed")
        from colin_studio_tts_mcp import server
        from colin_studio_tts_mcp.job_manager import McpJobManager
        from colin_studio_tts_mcp.job_store import McpJobStore
        from omni_tts_core.app_controller import FileGenerationOutcome
        from omni_tts_core.file_queue import FileQueueStatus

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = make_epub(root / "book.epub")
            service, engine = fake_service(root)

            def generate_files(
                tasks, settings, progress_callback=None, cancel_event=None
            ):
                return [
                    FileGenerationOutcome(
                        item_id=item_id,
                        source_path=path,
                        status=FileQueueStatus.DONE,
                        result=service.generate_from_source_file(
                            path,
                            settings.to_request("file"),
                            progress_callback=progress_callback,
                            cancel_event=cancel_event,
                        ),
                    )
                    for item_id, path in tasks
                ]

            controller = SimpleNamespace(service=service, generate_files=generate_files)
            manager = McpJobManager(
                controller,
                McpJobStore(root / "mcp.sqlite3"),
                gpu_preferences=SimpleNamespace(load=dict),
            )
            try:
                with patch.object(
                    server,
                    "runtime",
                    SimpleNamespace(controller=controller, jobs=manager),
                ):
                    async with Client(server.mcp) as client:
                        preview = await client.call_tool(
                            "inspect_epub",
                            {"source_file": str(source), "chapter_end": 2},
                        )
                        self.assertEqual(preview.structured_content["chapter_count"], 2)
                        self.assertEqual(engine.calls, [])
                        started = await client.call_tool(
                            "start_file_generation",
                            {
                                "request": {
                                    "source_files": [str(source)],
                                    "model_id": "fake",
                                    "output": {
                                        "directory": str(root / "out"),
                                        "create_srt": True,
                                    },
                                    "generation": {
                                        "epub": {
                                            "include_volumes": False,
                                            "output_mode": "merged",
                                            "title_pause_ms": 1500,
                                        }
                                    },
                                }
                            },
                        )
                        job_id = started.structured_content["job_id"]
                        for _ in range(100):
                            status = (
                                await client.call_tool("get_job", {"job_id": job_id})
                            ).structured_content
                            if status["status"] in {"succeeded", "failed", "cancelled"}:
                                break
                            await asyncio.sleep(0.02)
                        self.assertEqual(status["status"], "succeeded", status)
                        output = status["result"]["files"][0]["result"]
                        self.assertEqual(len(output["item_srt_paths"]), 1)
                        self.assertIn(
                            "00:00:02,500",
                            Path(output["srt_path"]).read_text(encoding="utf-8"),
                        )
            finally:
                manager._executor.shutdown(wait=True)


class EpubUiSettingsTests(unittest.TestCase):
    def test_options_roundtrip_and_range_editing(self):
        import os

        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication

        from omni_tts_core.ui_presenters.settings_state import GenerationSettings
        from omni_tts_ui_qt.widgets.epub_options import EpubOptionsWidget

        app = QApplication.instance() or QApplication([])
        widget = EpubOptionsWidget()
        widget.set_options(
            {"chapter_end": 2, "title_pause_ms": 2300, "chapter_pause_ms": 4500}
        )
        widget.start.setValue(4)
        self.assertEqual(widget.options()["chapter_end"], 4)
        widget.end.setValue(2)
        self.assertEqual(widget.options()["chapter_start"], 2)
        settings = GenerationSettings(epub_options=widget.options())
        restored = GenerationSettings.from_preferences(
            settings.to_preferences()
        ).to_request("file")
        self.assertEqual(restored.epub_options.title_pause_ms, 2300)
        self.assertEqual(restored.epub_options.chapter_pause_ms, 4500)
        widget.close()
        app.processEvents()


if __name__ == "__main__":
    unittest.main()
