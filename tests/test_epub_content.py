import hashlib
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from zipfile import ZipFile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from omni_tts_core.text.epub_content import (
    filter_urls,
    parse_han_readings,
    prepare_epub,
)
from omni_tts_core.text.epub_reader import read_epub
from omni_tts_core.text.vi_normalizer import normalize_vietnamese_text
from omni_tts_shared.epub import EpubOptions
from omni_tts_shared.schemas import GenerateSpeechRequest
from tests.test_epub import fake_service


def content_epub(path, pages=None):
    pages = pages or [
        '<section epub:type="chapter"><h1>Chương một</h1><p>Nội dung chính: 88% và 0,12.</p><div class="sources"><p class="label">Nguồn:</p><p>Lei J 等 (2020). Reference title. <a href="https://doi.org/10.1001/example.279.20">https://doi.org/10.1001/example.279.20</a></p></div><div class="note"><p>Ghi chú: kết quả có giới hạn.</p></div><p>Đọc <a href="https://example.org/doc">hướng dẫn</a>, xem <a href="#item">mục 18</a>. 万.</p></section>',
        '<section epub:type="chapter"><h1>Chương hai</h1><p>Nội dung tiếp tục.</p></section>',
    ]
    with ZipFile(path, "w") as archive:
        archive.writestr(
            "META-INF/container.xml",
            '<container><rootfiles><rootfile full-path="OPS/book.opf"/></rootfiles></container>',
        )
        manifest = "".join(
            f'<item id="c{i}" href="c{i}.xhtml" media-type="application/xhtml+xml"/>'
            for i in range(len(pages))
        )
        spine = "".join(f'<itemref idref="c{i}"/>' for i in range(len(pages)))
        archive.writestr(
            "OPS/book.opf",
            f"<package><metadata><title>Sách có nguồn</title><language>vi</language></metadata><manifest>{manifest}</manifest><spine>{spine}</spine></package>",
        )
        for i, body in enumerate(pages):
            archive.writestr(
                f"OPS/c{i}.xhtml",
                '<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops"><body>'
                + body
                + "</body></html>",
            )
    return path


class EpubContentTests(unittest.TestCase):
    def test_sources_are_archived_notes_and_link_labels_survive(self):
        with tempfile.TemporaryDirectory() as temp:
            source = content_epub(Path(temp) / "book.epub")
            before = source.read_bytes()
            book = read_epub(source)
            plan = prepare_epub(book)
            self.assertIn("Lei J", str(book))
            self.assertNotIn("Lei J", plan.text())
            self.assertNotIn("https", plan.text())
            self.assertIn("88% và 0,12", plan.text())
            self.assertIn("Ghi chú: kết quả có giới hạn.", plan.text())
            self.assertIn("hướng dẫn, xem mục 18", plan.text())
            self.assertEqual(plan.summary["reference_groups_skipped"], 1)
            self.assertIn("Lei J", plan.references[0]["text"])
            self.assertEqual(before, source.read_bytes())

    def test_heading_scope_ends_before_notes_or_next_section(self):
        page = '<section epub:type="chapter"><h1>Chương</h1><p>Nguồn nước sạch cần thiết.</p><h2>Nguồn</h2><p>Author Reference</p><h3>Chi tiết tài liệu</h3><p>More references</p><h2>Ghi chú</h2><p>Giải thích cần giữ.</p><h2>Nội dung tiếp</h2><p>Kết luận.</p></section>'
        with tempfile.TemporaryDirectory() as temp:
            book = read_epub(content_epub(Path(temp) / "book.epub", [page]))
            plan = prepare_epub(book)
            self.assertNotIn("Author Reference", plan.text())
            self.assertNotIn("More references", plan.text())
            self.assertIn("Giải thích cần giữ", plan.text())
            self.assertIn("Nguồn nước sạch", plan.text())
            self.assertIn("Kết luận", plan.text())

    def test_nested_bibliography_never_discards_the_whole_chapter(self):
        for page in [
            '<section epub:type="chapter"><h1>Main</h1><p>Keep A</p><section epub:type="bibliography"><h2>References</h2><p>Ref only</p></section><p>Keep B</p></section>',
            '<section epub:type="chapter"><h1>Main</h1><p>Keep A</p></section><section epub:type="bibliography"><h2>References</h2><p>Ref only</p></section>',
        ]:
            with self.subTest(page=page), tempfile.TemporaryDirectory() as temp:
                book = read_epub(content_epub(Path(temp) / "book.epub", [page]))
                plan = prepare_epub(book)
                self.assertIn("Keep A", plan.text())
                self.assertNotIn("Ref only", plan.text())
                self.assertEqual(len(book.chapters), 1)

    def test_explicit_note_ends_a_heuristic_reference_heading_scope(self):
        for note in (
            '<div class="note"><p>Giải thích cần giữ.</p></div>',
            '<p class="label">Ghi chú:</p><p>Giải thích cần giữ.</p>',
        ):
            with self.subTest(note=note), tempfile.TemporaryDirectory() as temp:
                page = (
                    "<h1>Main</h1><p>Content</p><h2>Nguồn</h2><p>Only reference</p>"
                    + note
                )
                plan = prepare_epub(
                    read_epub(content_epub(Path(temp) / "book.epub", [page]))
                )
                self.assertNotIn("Only reference", plan.text())
                self.assertIn("Giải thích cần giữ", plan.text())

    def test_han_glosses_custom_readings_and_unresolved_warnings(self):
        page = "<h1>Thuật ngữ</h1><p>医保 (bảo hiểm y tế), 户口 (hộ khẩu), 北京 (Beijing), 万.</p>"
        with tempfile.TemporaryDirectory() as temp:
            book = read_epub(content_epub(Path(temp) / "book.epub", [page]))
            plan = prepare_epub(
                book, EpubOptions(content={"han_readings": {"万": "vạn"}})
            )
            self.assertIn("bảo hiểm y tế, hộ khẩu", plan.text())
            self.assertIn("北京 (Beijing)", plan.text())
            self.assertIn("vạn", plan.text())
            self.assertEqual(plan.summary["glosses_used"], 2)
            self.assertEqual(plan.summary["han_characters"], 2)
            self.assertTrue(plan.warnings)
            keep = prepare_epub(book, EpubOptions(content={"han_mode": "keep"}))
            self.assertIn("医保", keep.text())
            self.assertFalse(keep.warnings)
        self.assertEqual(
            parse_han_readings("万 = vạn\n医保 = bảo hiểm y tế"),
            {"万": "vạn", "医保": "bảo hiểm y tế"},
        )
        with self.assertRaises(ValueError):
            parse_han_readings("万 = vạn\n万 = mười nghìn")

    def test_document_filters_preserve_original_chapter_positions(self):
        pages = [
            '<section epub:type="preface"><h1>Giới thiệu</h1><p>Mở đầu</p></section>',
            '<section epub:type="chapter"><h1>Main</h1><p>Body</p></section>',
            '<section epub:type="appendix"><h1>Phụ lục</h1><p>Thông tin</p></section>',
            "<h1>Ghi chú kỹ thuật</h1><p>Commit abcd123</p>",
        ]
        with tempfile.TemporaryDirectory() as temp:
            book = read_epub(content_epub(Path(temp) / "book.epub", pages))
            plan = prepare_epub(
                book,
                EpubOptions(
                    content={"include_frontmatter": False, "include_appendices": False}
                ),
            )
            self.assertEqual([c.index for c in plan.chapters], [2])
            self.assertEqual(plan.summary["documents_skipped"], 3)
            self.assertFalse(plan.chapter_preview(1)["included"])

    def test_url_modes_do_not_remove_labels_dates_or_fractions(self):
        text = "Xem https://example.org/a?q=1. Ngày 10/01/2020, tỷ lệ 1/2."
        cleaned, urls = filter_urls(text, "skip")
        self.assertEqual(urls, ["https://example.org/a?q=1"])
        self.assertIn("10/01/2020", cleaned)
        self.assertIn("1/2", cleaned)
        self.assertNotIn("example", cleaned)
        self.assertIn("example chấm org", filter_urls(text, "domain")[0])
        self.assertEqual(filter_urls(text, "read")[0], text)
        self.assertNotIn("10.1001", filter_urls("DOI:10.1001/jama.1234", "skip")[0])

    def test_full_url_normalization_protects_doi_from_date_rewrite(self):
        for value in (
            "https://doi.org/10.1001/jama.279.20.1633",
            "doi:10.1001/jama.279.20.1633",
        ):
            with self.subTest(value=value):
                normalized = normalize_vietnamese_text(value)
                self.assertNotIn("tháng", normalized)
                self.assertNotIn("năm một nghìn", normalized)
                self.assertIn("hai chấm", normalized)

    def test_explicit_han_reading_does_not_duplicate_existing_gloss(self):
        with tempfile.TemporaryDirectory() as temp:
            book = read_epub(
                content_epub(
                    Path(temp) / "book.epub",
                    ["<h1>Term</h1><p>医保 (bảo hiểm y tế).</p>"],
                )
            )
            plan = prepare_epub(
                book, EpubOptions(content={"han_readings": {"医保": "bảo hiểm y tế"}})
            )
            self.assertEqual(plan.text().count("bảo hiểm y tế"), 1)


class EpubFilteredAudioTests(unittest.TestCase):
    def test_filtered_text_reaches_each_provider_route(self):
        for provider in (
            "piper",
            "zerotts",
            "vieneu",
            "omnivoice",
            "qwen",
            "higgs_remote",
            "f5tts",
            "chatterbox",
            "supertonic",
        ):
            with self.subTest(provider=provider), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                source = content_epub(root / "book.epub")
                service, engine = fake_service(root, provider)
                request = GenerateSpeechRequest(
                    text="book",
                    model_id="fake",
                    language="vi",
                    output_dir=root / "out",
                    output_srt=True,
                    epub_options={
                        "chapter_end": 1,
                        "content": {"han_readings": {"万": "vạn"}},
                    },
                )
                with (
                    patch.object(service, "_ensure_request_can_generate"),
                    patch.object(service, "_cached_prompt_path_for", return_value=None),
                ):
                    result = service.generate_from_source_file(source, request)
                sent = " ".join(text for batch in engine.calls for text in batch)
                self.assertNotIn("https", sent)
                self.assertNotIn("Lei", sent)
                self.assertNotIn("万", sent)
                self.assertIn("giới hạn", sent)
                self.assertTrue(result.srt_path.is_file())

    def test_audio_srt_exports_and_cache_use_the_same_filtered_copy(self):
        for mode in ["chapters", "merged"]:
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                source = content_epub(root / "book.epub")
                original_hash = hashlib.sha256(source.read_bytes()).hexdigest()
                service, engine = fake_service(root)
                request = GenerateSpeechRequest(
                    text="book",
                    model_id="fake",
                    language="vi",
                    output_dir=root / "out",
                    output_srt=True,
                    chunk_join_mode="direct",
                    max_chunk_chars=800,
                    epub_options={
                        "output_mode": mode,
                        "content": {"han_readings": {"万": "vạn"}},
                    },
                )
                result = service.generate_from_source_file(source, request)
                spoken = " ".join(text for batch in engine.calls for text in batch)
                self.assertNotIn("Lei", spoken)
                self.assertNotIn("https", spoken)
                self.assertNotIn("万", spoken)
                self.assertIn("giới hạn", spoken)
                srt = " ".join(
                    p.read_text(encoding="utf-8") for p in result.item_srt_paths
                )
                self.assertNotIn("Reference title", srt)
                self.assertIn("Ghi chú", srt)
                self.assertIn("vạn", srt)
                self.assertTrue(result.reading_text_path.is_file())
                self.assertIn(
                    "Lei J", result.references_path.read_text(encoding="utf-8")
                )
                self.assertTrue(result.reading_report_path.is_file())
                calls = len(engine.calls)
                service.generate_from_source_file(source, request)
                self.assertEqual(len(engine.calls), calls)
                changed = request.model_copy(
                    update={
                        "epub_options": EpubOptions(
                            output_mode=mode,
                            content={
                                "skip_references": False,
                                "url_mode": "read",
                                "han_mode": "keep",
                            },
                        )
                    }
                )
                service.generate_from_source_file(source, changed)
                self.assertGreater(len(engine.calls), calls)
                self.assertIn(
                    "Lei", " ".join(t for batch in engine.calls[calls:] for t in batch)
                )
                self.assertEqual(
                    hashlib.sha256(source.read_bytes()).hexdigest(), original_hash
                )


class EpubContentUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication

        cls.app = QApplication.instance() or QApplication([])

    def test_qt_policy_roundtrip_and_three_preview_views(self):
        from omni_tts_ui_qt.widgets.epub_options import EpubImportDialog

        with tempfile.TemporaryDirectory() as temp:
            book = read_epub(content_epub(Path(temp) / "book.epub"))
            options = EpubOptions(
                content={"han_readings": {"万": "vạn"}, "url_mode": "skip"}
            )
            dialog = EpubImportDialog(book, options.model_dump())
            dialog.chapters.setCurrentRow(0)
            dialog._refresh_reading()
            self.assertIn("Lei", dialog.original_preview.toPlainText())
            self.assertNotIn("Lei", dialog.preview.toPlainText())
            self.assertIn("Bỏ nguồn tham khảo", dialog.changes_preview.toPlainText())
            self.assertEqual(
                dialog.editor.options()["content"], options.content.model_dump()
            )
            dialog.close()

    def test_content_changes_notify_studio_with_no_signal_arguments(self):
        from omni_tts_ui_qt.widgets.epub_content import EpubContentWidget

        widget = EpubContentWidget()
        events = []
        widget.changed.connect(lambda: events.append(widget.options()))
        widget.read_notes.setChecked(False)
        widget.url_mode.setCurrentIndex(widget.url_mode.findData("domain"))
        self.assertEqual(len(events), 2)
        self.assertFalse(events[0]["read_notes"])
        self.assertEqual(events[1]["url_mode"], "domain")
        widget.close()


class EpubContentMcpTests(unittest.IsolatedAsyncioTestCase):
    async def test_preview_and_export_match_core_without_synthesizing(self):
        from mcp import Client

        from colin_studio_tts_mcp.server import mcp

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = content_epub(root / "book.epub")
            async with Client(mcp) as client:
                preview = await client.call_tool(
                    "preview_epub_reading",
                    {"source_file": str(source), "max_characters": 100},
                )
                data = preview.structured_content
                self.assertEqual(data["summary"]["reference_groups_skipped"], 1)
                self.assertTrue(data["chapter"]["truncated"])
                exported = await client.call_tool(
                    "export_epub_reading",
                    {
                        "source_file": str(source),
                        "output_directory": str(root / "out"),
                        "epub": {"content": {"han_readings": {"万": "vạn"}}},
                    },
                )
                self.assertEqual(
                    exported.structured_content["summary"]["han_characters"], 0
                )
                self.assertTrue(
                    Path(
                        exported.structured_content["files"]["references_path"]
                    ).is_file()
                )


if __name__ == "__main__":
    unittest.main()
