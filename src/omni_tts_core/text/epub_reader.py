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
    content_kind: str = "body"
    group_id: str = ""
    source_id: str = ""
    links: list[dict] = field(default_factory=list)


@dataclass
class BookChapter:
    index: int
    title: str
    href: str
    blocks: list[BookBlock]
    volume: str = ""
    kind: str = "body"


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
        from omni_tts_core.text.epub_content import prepare_epub

        options = options or EpubOptions()
        plan = prepare_epub(self, options)
        selected = plan.chapters
        return {
            "title": self.title,
            "author": self.author,
            "language": self.language,
            "chapter_count": len(self.chapters),
            "selected_count": len(selected),
            "character_count": sum(
                len(b.text) for c in selected for b in c.blocks if b.role != "scene"
            ),
            "scene_count": sum(b.role == "scene" for c in selected for b in c.blocks),
            "warnings": [*self.warnings, *plan.warnings],
            "content_summary": plan.summary,
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


_REFERENCE_LABEL = re.compile(
    r"^(?:nguồn(?: tham khảo)?|tài liệu tham khảo|danh mục tài liệu tham khảo|references|bibliography|sources|参考文献|参考资料)\s*[:：]?$",
    re.IGNORECASE,
)
_NOTE_LABEL = re.compile(r"^(?:ghi chú|chú giải|lưu ý|notes)\s*[:：]?$", re.IGNORECASE)


def _blocks(body) -> list[BookBlock]:
    result = []
    positions = {id(el): str(i) for i, el in enumerate(body.iter(), 1)}

    def walk(el, kind="body", group=""):
        tag = _tag(el)
        if (
            tag in _SKIP
            or _hidden(el)
            or _SKIP_TYPES.intersection(el.get(EPUB_TYPE, "").split())
        ):
            return
        classes = set(el.get("class", "").lower().split())
        semantics = set(el.get(EPUB_TYPE, "").split()) | set(el.get("role", "").split())
        if kind != "reference":
            if classes.intersection(
                {
                    "sources",
                    "references",
                    "bibliography",
                    "reference-list",
                    "bibliographic",
                }
            ) or semantics.intersection(
                {"bibliography", "biblioentry", "doc-bibliography", "doc-biblioentry"}
            ):
                kind, group = "reference", "ref-" + positions[id(el)]
            elif classes.intersection(
                {"note", "notes", "annotation", "sidenote"}
            ) or semantics.intersection({"note", "annotation"}):
                kind, group = "note", "note-" + positions[id(el)]
        links = [
            {"href": a.get("href"), "label": _clean(_inline(a))}
            for a in el.iter()
            if _tag(a) == "a" and a.get("href")
        ]

        def emit(text, role="paragraph", suffix=""):
            result.append(
                BookBlock(
                    text,
                    role,
                    kind,
                    group,
                    positions[id(el)] + suffix,
                    links if role != "scene" else [],
                )
            )

        if tag == "hr":
            emit("", "scene")
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
                emit("", "scene")
            else:
                for number, line in enumerate(value.splitlines()):
                    if line.strip():
                        emit(
                            _clean(line),
                            "heading" if tag.startswith("h") else "paragraph",
                            f":{number}",
                        )
            return
        if el.text and el.text.strip():
            emit(_clean(el.text))
        scope_kind, scope_group, scope_level = kind, group, None
        for child in el:
            child_tag = _tag(child)
            structured_label = child_tag == "p" and (
                "label" in child.get("class", "").split()
                or any(_tag(c) in {"strong", "b"} for c in child)
            )
            explicit_note = bool(
                set(child.get("class", "").lower().split()).intersection(
                    {"note", "notes", "annotation", "sidenote"}
                )
            )
            note_label = (
                bool(re.fullmatch(r"h[1-6]", child_tag)) or structured_label
            ) and _NOTE_LABEL.fullmatch(_clean(_inline(child)))
            if (
                kind != "reference"
                and scope_kind == "reference"
                and (explicit_note or note_label)
            ):
                # A separate explanatory note closes a heuristic heading scope;
                # notes *inside* an explicit bibliography stay in that bibliography.
                scope_kind, scope_group, scope_level = kind, group, None
            if re.fullmatch(r"h[1-6]", child_tag) or structured_label:
                level = int(child_tag[1]) if child_tag.startswith("h") else 7
                label = _clean(_inline(child))
                if scope_level is not None and level <= scope_level:
                    scope_kind, scope_group, scope_level = kind, group, None
                if _REFERENCE_LABEL.fullmatch(label):
                    scope_kind, scope_group, scope_level = (
                        "reference",
                        "ref-" + positions[id(child)],
                        level,
                    )
                elif _NOTE_LABEL.fullmatch(label) and scope_kind != "reference":
                    scope_kind, scope_group, scope_level = (
                        "note",
                        "note-" + positions[id(child)],
                        level,
                    )
            walk(child, scope_kind, scope_group)
            if child.tail and child.tail.strip():
                result.append(
                    BookBlock(
                        _clean(child.tail),
                        "paragraph",
                        scope_kind,
                        scope_group,
                        positions[id(child)] + ":tail",
                    )
                )

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
                            uri = urlsplit(e.get("href"))
                            if uri.scheme or uri.netloc:
                                continue
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
                # Document semantics belong to the body/outer wrapper. A nested
                # bibliography or table of contents must never discard its chapter.
                wrappers = [body]
                children = [e for e in body if _tag(e) not in _SKIP and not _hidden(e)]
                while len(children) == 1 and _tag(children[0]) in {
                    "section",
                    "main",
                    "article",
                    "div",
                }:
                    wrappers.append(children[0])
                    children = [
                        e
                        for e in children[0]
                        if _tag(e) not in _SKIP and not _hidden(e)
                    ]
                types = {t for e in wrappers for t in e.get(EPUB_TYPE, "").split()}
                if types.intersection(
                    {
                        "toc",
                        "landmarks",
                        "cover",
                        "titlepage",
                        "copyright-page",
                        "index",
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
                kind = (
                    "reference"
                    if "bibliography" in types
                    else "appendix"
                    if "appendix" in types
                    else "frontmatter"
                    if types.intersection(
                        {"frontmatter", "preface", "glossary", "foreword"}
                    )
                    else "body"
                )
                if (
                    re.fullmatch(
                        r"(?:ghi chú kỹ thuật|technical notes|colophon)\s*[:：]?",
                        title,
                        re.IGNORECASE,
                    )
                    or "colophon" in types
                ):
                    kind = "technical"
                book.chapters.append(
                    BookChapter(
                        len(book.chapters) + 1, title, name, blocks, volume, kind
                    )
                )
            if not book.chapters:
                raise ConfigError(
                    "Không tìm thấy chương có chữ trong EPUB. Sách ảnh/scan cần OCR trước."
                )
            return book
    except (OSError, BadZipFile) as exc:
        raise ConfigError(f"Không mở được EPUB: {exc}") from exc
