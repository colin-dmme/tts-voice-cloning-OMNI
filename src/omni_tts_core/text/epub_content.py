"""Prepare a reviewable reading copy without altering the EPUB or calling a model."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field, replace
from pathlib import Path
from urllib.parse import urlsplit

from filelock import FileLock

from omni_tts_shared.epub import EpubOptions

FILTER_VERSION = 1
HAN = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\U00020000-\U0002fa1f]")
URL = re.compile(
    r"\b(?:https?://|www\.)[^\s<>\"“”；]+|(?<!\w)(?:doi:\s*)?10\.\d{4,9}/[-._;()/:A-Za-z0-9%]+",
    re.IGNORECASE,
)
GLOSS = re.compile(
    r"([\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]+)\s*[(（]([^()（）\n]{2,200})[)）]"
)
VIETNAMESE = re.compile(r"[ăâđêôơưĂÂĐÊÔƠƯ\u1ea0-\u1ef9]")
CHANGE_LABELS = {
    "reference": "Bỏ nguồn tham khảo",
    "note": "Bỏ ghi chú theo lựa chọn",
    "url_skip": "Bỏ địa chỉ URL / DOI",
    "url_domain": "Chỉ giữ tên miền",
    "han_reading": "Dùng cách đọc chữ Hán",
    "existing_vietnamese_gloss": "Dùng nghĩa Việt đã có",
    "document_frontmatter": "Bỏ phần giới thiệu",
    "document_appendix": "Bỏ phụ lục",
    "document_technical": "Bỏ ghi chú kỹ thuật",
    "document_reference": "Bỏ phần tài liệu tham khảo",
}


def format_reading_changes(data):
    text = "\n\n".join(
        f"{CHANGE_LABELS.get(c['reason'], 'Điều chỉnh văn bản đọc')}\n{c['before']}\n→ {c['after'] or '[Không đọc]'}"
        for c in data["changes"]
    )
    if data.get("changes_truncated"):
        text += "\n\nĐang hiển thị một phần thay đổi; xuất báo cáo để xem đầy đủ."
    return text or "Không có thay đổi ở phần này."


def format_han_issues(plan):
    return (
        "\n\n".join(
            f"Phần {x['chapter_index']}: {x['chapter_title']} · Chữ: {x['characters']}\n{x['text'][:1500]}"
            for x in plan.han_issues[:100]
        )
        or "Không còn chữ Hán trong bản đọc."
    )


def parse_han_readings(text):
    from omni_tts_shared.epub import EpubContentOptions

    result = {}
    for number, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        if "=" not in line:
            raise ValueError(f"Dòng {number}: dùng chữ gốc = cách đọc.")
        written, spoken = (value.strip() for value in line.split("=", 1))
        if written in result:
            raise ValueError(f"Dòng {number}: cụm gốc đã có ở dòng trước.")
        result[written] = spoken
    return EpubContentOptions(han_readings=result).han_readings


def _url_parts(raw):
    """Keep sentence punctuation and unmatched closing brackets out of a URL."""
    end = len(raw.rstrip(".,;:!?。、：！？»"))
    for opening, closing in (("(", ")"), ("[", "]"), ("{", "}")):
        while (
            end
            and raw[end - 1] == closing
            and raw[:end].count(closing) > raw[:end].count(opening)
        ):
            end -= 1
    return raw[:end], raw[end:]


def filter_urls(text, mode):
    found = []

    def substitute(match):
        value, punctuation = _url_parts(match.group())
        if mode == "read":
            return match.group()
        found.append(value)
        if mode == "domain":
            if re.match(r"(?:doi:)?10\.", value, re.IGNORECASE):
                domain = "doi.org"
            else:
                try:
                    domain = (
                        urlsplit(
                            value if "://" in value else "https://" + value
                        ).hostname
                        or ""
                    )
                except ValueError:
                    domain = "liên kết"
            return domain.replace(".", " chấm ") + punctuation
        return " " + punctuation

    result = URL.sub(substitute, text)
    result = re.sub(r"[ \t]+", " ", result)
    result = re.sub(r"\s+([,.;:!?])", r"\1", result)
    # A reference-free paragraph can become only separators after URL removal.
    return result.strip(), found


@dataclass
class EpubReadingPlan:
    book: object
    options: EpubOptions
    chapters: list = field(default_factory=list)
    references: list[dict] = field(default_factory=list)
    changes: list[dict] = field(default_factory=list)
    han_issues: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    summary: dict = field(default_factory=dict)

    def text(self):
        pieces = []
        last_volume = None
        for chapter in self.chapters:
            if (
                self.options.include_volumes
                and chapter.volume
                and chapter.volume != last_volume
            ):
                pieces.append(chapter.volume)
            last_volume = chapter.volume
            if self.options.read_titles:
                pieces.append(chapter.title)
            pieces.extend(b.text for b in chapter.blocks if b.text)
        return "\n\n".join(pieces)

    def fingerprint(self):
        payload = {
            "filter_version": FILTER_VERSION,
            "options": self.options.content.model_dump(),
            "chapters": [
                (c.index, c.title, c.volume, [(b.role, b.text) for b in c.blocks])
                for c in self.chapters
            ],
        }
        return hashlib.sha256(
            json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()
        ).hexdigest()

    def chapter_preview(self, index, max_chars=24000):
        original = next((c for c in self.book.chapters if c.index == index), None)
        prepared = next((c for c in self.chapters if c.index == index), None)
        if original is None:
            return {"index": index, "error": "Không có chương này trong sách."}
        raw = "\n\n".join(
            [original.title, *(b.text for b in original.blocks if b.text)]
        )
        pieces = []
        if prepared:
            position = next(i for i, c in enumerate(self.chapters) if c.index == index)
            if (
                self.options.include_volumes
                and prepared.volume
                and (
                    not position
                    or self.chapters[position - 1].volume != prepared.volume
                )
            ):
                pieces.append(prepared.volume)
            if self.options.read_titles:
                pieces.append(prepared.title)
            pieces.extend(b.text for b in prepared.blocks if b.text)
        reading = "\n\n".join(pieces)
        changes = [c for c in self.changes if c["chapter_index"] == index]
        return {
            "index": index,
            "title": original.title,
            "source_href": original.href,
            "original_text": raw[:max_chars],
            "reading_text": reading[:max_chars],
            "original_characters": len(raw),
            "reading_characters": len(reading),
            "truncated": len(raw) > max_chars or len(reading) > max_chars,
            "included": prepared is not None,
            "changes": [
                {**c, "before": c["before"][:800], "after": c["after"][:800]}
                for c in changes[:80]
            ],
            "changes_truncated": len(changes) > 80,
        }

    def report(self, *, full=False):
        return {
            "filter_version": FILTER_VERSION,
            "book_title": self.book.title,
            "content_options": self.options.content.model_dump(),
            "chapter_start": self.options.chapter_start,
            "chapter_end": self.options.chapter_end,
            "reading_sha256": self.fingerprint(),
            "summary": self.summary,
            "warnings": self.warnings,
            "han_issues": self.han_issues
            if full
            else [{**x, "text": x["text"][:400]} for x in self.han_issues[:100]],
            "han_issues_truncated": not full and len(self.han_issues) > 100,
            **(
                {"references": self.references, "changes": self.changes} if full else {}
            ),
        }


def prepare_epub(book, options: EpubOptions | None = None) -> EpubReadingPlan:
    options = options or EpubOptions()
    policy = options.content
    plan = EpubReadingPlan(book, options)
    counts = {
        "selected_chapters": 0,
        "reading_chapters": 0,
        "reference_groups": 0,
        "reference_groups_skipped": 0,
        "note_blocks_kept": 0,
        "note_blocks_skipped": 0,
        "documents_skipped": 0,
        "urls_filtered": 0,
        "glosses_used": 0,
        "custom_han_readings_used": 0,
        "han_blocks": 0,
        "han_characters": 0,
    }
    groups = {}

    def change(chapter, source_id, before, after, reason):
        plan.changes.append(
            {
                "chapter_index": chapter.index,
                "chapter_title": chapter.title,
                "source_href": chapter.href,
                "source_id": source_id,
                "reason": reason,
                "before": before,
                "after": after,
            }
        )

    def transform(text, chapter, source_id):
        original = text
        text, urls = filter_urls(text, policy.url_mode)
        counts["urls_filtered"] += len(urls)
        if urls:
            change(chapter, source_id, original, text, "url_" + policy.url_mode)
            plan.references.append(
                {
                    "chapter_index": chapter.index,
                    "chapter_title": chapter.title,
                    "source_href": chapter.href,
                    "source_id": source_id,
                    "kind": "links",
                    "text": original,
                    "links": urls,
                }
            )
        if policy.han_mode == "prefer_vietnamese":
            before = text

            def gloss(match):
                translated = match[2].strip()
                if HAN.search(translated) or not VIETNAMESE.search(translated):
                    return match.group()
                if match[1] in policy.han_readings:
                    counts["custom_han_readings_used"] += 1
                    return policy.han_readings[match[1]]
                counts["glosses_used"] += 1
                return translated

            text = GLOSS.sub(gloss, text)
            if text != before:
                change(chapter, source_id, before, text, "existing_vietnamese_gloss")
        for written, spoken in sorted(
            policy.han_readings.items(), key=lambda x: -len(x[0])
        ):
            occurrences = text.count(written)
            if occurrences:
                before = text
                text = text.replace(written, spoken)
                counts["custom_han_readings_used"] += occurrences
                change(chapter, source_id, before, text, "han_reading")
        han = HAN.findall(text)
        if han:
            counts["han_blocks"] += 1
            counts["han_characters"] += len(han)
            plan.han_issues.append(
                {
                    "chapter_index": chapter.index,
                    "chapter_title": chapter.title,
                    "source_href": chapter.href,
                    "source_id": source_id,
                    "characters": "".join(dict.fromkeys(han)),
                    "text": text,
                }
            )
        return text

    for chapter in book.select(options):
        counts["selected_chapters"] += 1
        skip_document = (
            (chapter.kind == "frontmatter" and not policy.include_frontmatter)
            or (chapter.kind == "appendix" and not policy.include_appendices)
            or (chapter.kind == "technical" and not policy.include_technical_notes)
            or (chapter.kind == "reference" and policy.skip_references)
        )
        if skip_document:
            counts["documents_skipped"] += 1
            change(
                chapter,
                "document",
                "\n\n".join([chapter.title, *(b.text for b in chapter.blocks)]),
                "",
                "document_" + chapter.kind,
            )
            plan.references.append(
                {
                    "chapter_index": chapter.index,
                    "chapter_title": chapter.title,
                    "source_href": chapter.href,
                    "source_id": "document",
                    "kind": chapter.kind,
                    "text": "\n\n".join(b.text for b in chapter.blocks),
                    "links": [],
                }
            )
            continue
        blocks = []
        for number, block in enumerate(chapter.blocks, 1):
            source_id = block.source_id or str(number)
            reference = block.content_kind == "reference" or chapter.kind == "reference"
            if reference:
                key = (chapter.index, block.group_id or source_id)
                if key not in groups:
                    groups[key] = {
                        "chapter_index": chapter.index,
                        "chapter_title": chapter.title,
                        "source_href": chapter.href,
                        "source_id": block.group_id or source_id,
                        "kind": "reference",
                        "text": "",
                        "links": [],
                        "skipped": policy.skip_references,
                    }
                groups[key]["text"] += (
                    "\n" if groups[key]["text"] else ""
                ) + block.text
                groups[key]["links"].extend(block.links)
                if policy.skip_references:
                    change(chapter, source_id, block.text, "", "reference")
                    continue
            if block.content_kind == "note":
                if not policy.read_notes:
                    counts["note_blocks_skipped"] += 1
                    change(chapter, source_id, block.text, "", "note")
                    continue
                counts["note_blocks_kept"] += 1
            text = transform(block.text, chapter, source_id) if block.text else ""
            if text and re.search(r"\w", text, re.UNICODE) or block.role == "scene":
                blocks.append(replace(block, text=text))
        if not any(b.text for b in blocks):
            counts["documents_skipped"] += 1
            continue
        title = (
            transform(chapter.title, chapter, "title")
            if options.read_titles
            else chapter.title
        )
        volume = (
            transform(chapter.volume, chapter, "volume")
            if options.include_volumes and chapter.volume
            else chapter.volume
        )
        plan.chapters.append(
            replace(chapter, blocks=blocks, title=title, volume=volume)
        )
    plan.references.extend(groups.values())
    counts["reference_groups"] = len(groups)
    counts["reference_groups_skipped"] = len(groups) if policy.skip_references else 0
    counts["reading_chapters"] = len(plan.chapters)
    plan.summary = counts
    if counts["han_blocks"] and policy.han_mode != "keep":
        plan.warnings.append(
            f"Còn {counts['han_characters']} ký tự Hán trong {counts['han_blocks']} đoạn đọc; xem trước hoặc thêm cách đọc trước khi tạo giọng."
        )
    if not plan.chapters:
        plan.warnings.append(
            "Không còn nội dung trong phạm vi đã chọn sau khi lọc; hãy đổi phạm vi hoặc tùy chọn nội dung."
        )
    return plan


def reading_summary(summary):
    return (
        f"Đọc {summary['reading_chapters']}/{summary['selected_chapters']} phần · "
        f"Bỏ {summary['reference_groups_skipped']} nhóm nguồn · "
        f"Xử lý {summary['urls_filtered']} URL · Còn {summary['han_characters']} chữ Hán"
    )


def export_reading_plan(plan, directory: Path, stem: str, source_hash="") -> dict:
    directory.mkdir(parents=True, exist_ok=True)
    suffix = hashlib.sha256((plan.fingerprint() + source_hash).encode()).hexdigest()[
        :12
    ]
    report = plan.report(full=True)
    report["source_sha256"] = source_hash
    paths = {
        "reading_text_path": directory / f"{stem}-reading-{suffix}.txt",
        "reading_report_path": directory / f"{stem}-reading-report-{suffix}.json",
    }
    documents = {
        paths["reading_text_path"]: plan.text(),
        paths["reading_report_path"]: json.dumps(report, ensure_ascii=False, indent=2),
    }
    if plan.options.content.export_references:
        paths["references_path"] = directory / f"{stem}-references-{suffix}.md"
        lines = [
            f"# Nguồn tham khảo — {plan.book.title}",
            "",
            "Bản nguồn được giữ riêng với nội dung đọc. Các liên kết chưa được mở hoặc xác minh.",
            "",
        ]
        for item in plan.references:
            lines.extend(
                [
                    f"## {item['chapter_index']}. {item['chapter_title']} · {item['source_id']}",
                    "",
                    item["text"],
                    "",
                ]
            )
            for link in item["links"]:
                if isinstance(link, dict) and link.get("href"):
                    lines.append(f"- {link.get('label', '')}: {link['href']}")
            lines.append("")
        documents[paths["references_path"]] = "\n".join(lines)
    with FileLock(str(directory / ".epub-reading.lock")):
        for path, content in documents.items():
            # Content-addressed exports stay stable across retries, alongside the cache.
            temporary = path.with_suffix(path.suffix + ".tmp")
            temporary.write_text(content, encoding="utf-8")
            temporary.replace(path)
    return paths
