"""Read EPUB structure without extracting archives or executing book content."""

from __future__ import annotations

import posixpath
import re
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import unquote, urlsplit
from xml.etree import ElementTree as ET
from zipfile import BadZipFile, ZipFile

from omni_tts_shared.epub import EpubOptions
from omni_tts_shared.errors import ConfigError

EPUB_TYPE = "{http://www.idpf.org/2007/ops}type"
_SKIP = {"script", "style", "nav", "head", "rt", "rp"}
_SKIP_TYPES = {"noteref", "footnote", "endnote", "pagebreak", "toc", "landmarks"}


def _tag(el) -> str:
    return el.tag.rsplit("}", 1)[-1]


def _hidden(el) -> bool:
    style = re.sub(r"\s+", "", el.get("style", "")).lower()
    return (
        "hidden" in el.attrib
        or el.get("aria-hidden") == "true"
        or "display:none" in style
        or "visibility:hidden" in style
    )


def _inline(el) -> str:
    if (
        _tag(el) in _SKIP
        or _hidden(el)
        or _SKIP_TYPES.intersection(el.get(EPUB_TYPE, "").split())
    ):
        return ""
    parts = [el.text or ""]
    for child in el:
        parts.append("\n" if _tag(child) == "br" else _inline(child))
        parts.append(child.tail or "")
    return "".join(parts)


def _clean(value: str) -> str:
    return " ".join(value.split())


def _path(base: str, href: str) -> str:
    uri = urlsplit(href)
    if uri.scheme or uri.netloc:
        raise ConfigError(
            "EPUB tham chiếu nội dung bên ngoài; cần nội dung nằm trong sách."
        )
    result = posixpath.normpath(
        posixpath.join(posixpath.dirname(base), unquote(uri.path))
    )
    if result.startswith(("../", "/")) or "\\" in result:
        raise ConfigError("Đường dẫn bên trong EPUB không hợp lệ.")
    return result


def _xml(z: ZipFile, path: str):
    try:
        info = z.getinfo(path)
        if info.file_size > 20 * 1024 * 1024:
            raise ConfigError(f"Tài liệu EPUB quá lớn: {path}")
        data = z.read(path)
        if b"<!ENTITY" in data.upper():
            raise ConfigError("EPUB có khai báo XML entity không được hỗ trợ.")
        return ET.fromstring(data)
    except (KeyError, ET.ParseError, RuntimeError) as exc:
        raise ConfigError(f"Không đọc được tài liệu EPUB {path}: {exc}") from exc


@dataclass
class BookBlock:
    text: str
    role: str = "paragraph"


@dataclass
class BookChapter:
    index: int
    title: str
    href: str
    blocks: list[BookBlock]
    volume: str = ""


@dataclass
class EpubBook:
    title: str
    author: str
    language: str
    chapters: list[BookChapter]
    warnings: list[str] = field(default_factory=list)
    skipped_documents: list[str] = field(default_factory=list)

    def select(self, options: EpubOptions) -> list[BookChapter]:
        end = options.chapter_end or len(self.chapters)
        if options.chapter_start > len(self.chapters) or end > len(self.chapters):
            raise ConfigError(
                f"Sách có {len(self.chapters)} chương; khoảng chương đã chọn vượt quá sách."
            )
        return self.chapters[options.chapter_start - 1 : end]

    def preview(self, options: EpubOptions | None = None, limit: int = 50) -> dict:
        options = options or EpubOptions()
        selected = self.select(options)
        return {
            "title": self.title,
            "author": self.author,
            "language": self.language,
            "chapter_count": len(self.chapters),
            "selected_count": len(selected),
            "character_count": sum(
                len(b.text)
                for c in self.chapters
                for b in c.blocks
                if b.role != "scene"
            ),
            "scene_count": sum(
                b.role == "scene" for c in self.chapters for b in c.blocks
            ),
            "warnings": self.warnings,
            "skipped_documents": self.skipped_documents,
            "chapters": [
                {
                    "index": c.index,
                    "title": c.title,
                    "href": c.href,
                    "volume": c.volume,
                    "paragraph_count": sum(b.role != "scene" for b in c.blocks),
                    "preview": " ".join(b.text for b in c.blocks if b.role != "scene")[
                        :250
                    ],
                }
                for c in selected[: max(1, min(limit, 500))]
            ],
            "options": options.model_dump(),
            "truncated": len(selected) > limit,
        }


def _blocks(body) -> list[BookBlock]:
    result = []

    def walk(el):
        tag = _tag(el)
        if (
            tag in _SKIP
            or _hidden(el)
            or _SKIP_TYPES.intersection(el.get(EPUB_TYPE, "").split())
        ):
            return
        if tag == "hr":
            result.append(BookBlock("", "scene"))
            return
        if tag in {
            "p",
            "h1",
            "h2",
            "h3",
            "h4",
            "h5",
            "h6",
            "li",
            "dt",
            "dd",
            "pre",
            "figcaption",
        }:
            value = _inline(el)
            if not value.strip():
                return
            if (
                "scene" in el.get("class", "").split()
                and not re.search(r"\w", value, re.UNICODE)
                and re.fullmatch(r"[\s.…*·•—_\-]+", value)
            ):
                result.append(BookBlock("", "scene"))
            else:
                for line in value.splitlines():
                    if line.strip():
                        result.append(
                            BookBlock(
                                _clean(line),
                                "heading" if tag.startswith("h") else "paragraph",
                            )
                        )
            return
        if el.text and el.text.strip():
            result.append(BookBlock(_clean(el.text)))
        for child in el:
            walk(child)
            if child.tail and child.tail.strip():
                result.append(BookBlock(_clean(child.tail)))

    walk(body)
    return result


def read_epub(path: Path) -> EpubBook:
    try:
        with ZipFile(path) as z:
            infos = z.infolist()
            if (
                len(infos) > 10000
                or sum(i.file_size for i in infos) > 200 * 1024 * 1024
            ):
                raise ConfigError(
                    "EPUB vượt giới hạn 10.000 tệp hoặc 200 MB sau giải nén."
                )
            container = _xml(z, "META-INF/container.xml")
            rootfile = next(
                (e for e in container.iter() if _tag(e) == "rootfile"), None
            )
            if rootfile is None:
                raise ConfigError("EPUB thiếu khai báo rootfile.")
            opf_path = _path("", rootfile.get("full-path", ""))
            opf = _xml(z, opf_path)
            metadata = next((e for e in opf if _tag(e) == "metadata"), [])
            values = {_tag(e): _clean(e.text or "") for e in metadata}
            manifest = {e.get("id"): e for e in opf.iter() if _tag(e) == "item"}
            refs = [e for e in opf.iter() if _tag(e) == "itemref"]
            if not refs:
                raise ConfigError("EPUB không có thứ tự đọc spine.")
            book = EpubBook(
                values.get("title") or path.stem,
                values.get("creator", ""),
                values.get("language", ""),
                [],
            )
            labels = {}
            for item in manifest.values():
                if "nav" in item.get("properties", "").split():
                    nav_path = _path(opf_path, item.get("href", ""))
                    nav = _xml(z, nav_path)
                    for e in nav.iter():
                        if _tag(e) == "a" and e.get("href"):
                            labels.setdefault(
                                _path(nav_path, e.get("href")), _clean(_inline(e))
                            )
            volume = ""
            for ref in refs:
                item = manifest.get(ref.get("idref"))
                if item is None:
                    raise ConfigError(
                        "EPUB spine tham chiếu file không tồn tại trong manifest."
                    )
                name = _path(opf_path, item.get("href", ""))
                if (
                    ref.get("linear") == "no"
                    or "nav" in item.get("properties", "").split()
                ):
                    book.skipped_documents.append(name)
                    continue
                if item.get("media-type") not in {"application/xhtml+xml", "text/html"}:
                    book.warnings.append(f"Bỏ nội dung không phải văn bản: {name}")
                    continue
                root = _xml(z, name)
                body = next((e for e in root.iter() if _tag(e) == "body"), None)
                if body is None:
                    raise ConfigError(f"EPUB thiếu body: {name}")
                types = {t for e in body.iter() for t in e.get(EPUB_TYPE, "").split()}
                if types.intersection(
                    {
                        "toc",
                        "landmarks",
                        "cover",
                        "titlepage",
                        "copyright-page",
                        "index",
                        "bibliography",
                        "endnotes",
                    }
                ) or re.search(
                    r"(?:^|/)(?:toc|cover|intro|copyright|titlepage)(?:[._-]|$)",
                    name,
                    re.IGNORECASE,
                ):
                    book.skipped_documents.append(name)
                    continue
                blocks = _blocks(body)
                heading = next((b for b in blocks if b.role == "heading"), None)
                if "part" in types or (
                    re.search(r"(?:^|/)(?:volume|part)[_-]?\d", name, re.IGNORECASE)
                    and len(blocks) <= 1
                ):
                    volume = heading.text if heading else labels.get(name, "")
                    continue
                title = heading.text if heading else labels.get(name, "")
                if heading:
                    blocks.remove(heading)
                if not any(b.text for b in blocks):
                    book.warnings.append(f"Không có nội dung chữ để đọc: {name}")
                    continue
                if not title and book.chapters and "chapter" not in types:
                    book.chapters[-1].blocks.extend(blocks)
                    book.warnings.append(f"Ghép phần tiếp nối không có tiêu đề: {name}")
                    continue
                title = title or f"Chương {len(book.chapters) + 1}"
                book.chapters.append(
                    BookChapter(len(book.chapters) + 1, title, name, blocks, volume)
                )
            if not book.chapters:
                raise ConfigError(
                    "Không tìm thấy chương có chữ trong EPUB. Sách ảnh/scan cần OCR trước."
                )
            return book
    except (OSError, BadZipFile) as exc:
        raise ConfigError(f"Không mở được EPUB: {exc}") from exc
