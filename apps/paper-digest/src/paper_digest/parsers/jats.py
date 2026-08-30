"""Fail-closed JATS full-text extraction aligned back to the canonical PDF."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

from ..grounding import build_index, is_grounded
from ..models import TextBlock
from ..text import normalize_prose, split_sentences, word_count

MAX_XML_BYTES = 20 * 1024 * 1024
FORBIDDEN_DECLARATIONS = (b"<!ENTITY",)


@dataclass(slots=True)
class JATSExtraction:
    path: Path
    blocks: list[TextBlock]
    full_text: str
    total_sentences: int
    aligned_sentences: int
    alignment_ratio: float
    aligned_words: int
    section_titles: list[str]
    article_type: str = ""


def _local(element: ET.Element) -> str:
    return element.tag.rsplit("}", 1)[-1].casefold()


def _direct(element: ET.Element, name: str) -> list[ET.Element]:
    wanted = name.casefold()
    return [child for child in element if _local(child) == wanted]


def _first(root: ET.Element, name: str) -> ET.Element | None:
    wanted = name.casefold()
    return next((element for element in root.iter() if _local(element) == wanted), None)


def _text(element: ET.Element | None) -> str:
    if element is None:
        return ""
    return normalize_prose(" ".join(element.itertext()))


def extract_jats(path: Path, page_texts: list[str], source_file: str) -> JATSExtraction:
    """Read JATS prose, retaining only sentences verifiable on a PDF page."""
    payload = path.read_bytes()
    if not payload or len(payload) > MAX_XML_BYTES:
        raise ValueError("JATS XML is empty or exceeds the 20 MiB safety limit.")
    upper = payload.upper()
    if any(marker in upper for marker in FORBIDDEN_DECLARATIONS):
        raise ValueError("Entity declarations are not accepted in JATS XML.")
    root = ET.fromstring(payload)
    if _local(root) != "article" or _first(root, "body") is None:
        raise ValueError("XML is not a JATS article with a body element.")

    page_indexes = [build_index(text) for text in page_texts]
    blocks: list[TextBlock] = []
    section_titles: list[str] = []
    total = 0
    aligned = 0

    def aligned_paragraphs(paragraphs: list[ET.Element]) -> list[tuple[int, str]]:
        nonlocal total, aligned
        output: list[tuple[int, str]] = []
        for paragraph in paragraphs:
            for sentence in split_sentences(_text(paragraph)):
                sentence = normalize_prose(sentence)
                if word_count(sentence) < 8:
                    continue
                total += 1
                page = next(
                    (index for index, source in enumerate(page_indexes, start=1) if is_grounded(sentence, source)),
                    None,
                )
                if page is None:
                    continue
                aligned += 1
                output.append((page, sentence))
        return output

    def append_section(title: str, paragraphs: list[ET.Element]) -> None:
        matched = aligned_paragraphs(paragraphs)
        if not matched:
            return
        cleaned_title = normalize_prose(title)
        if cleaned_title:
            section_titles.append(cleaned_title)
            blocks.append(
                TextBlock(
                    text=cleaned_title,
                    page=matched[0][0],
                    kind="heading",
                    source_file=source_file,
                    extraction_method="jats-xml-aligned",
                )
            )
        blocks.extend(
            TextBlock(
                text=sentence,
                page=page,
                kind="body",
                source_file=source_file,
                extraction_method="jats-xml-aligned",
            )
            for page, sentence in matched
        )

    abstract = _first(root, "abstract")
    if abstract is not None:
        append_section("Abstract", [element for element in abstract.iter() if _local(element) == "p"])

    body = _first(root, "body")

    def walk(container: ET.Element) -> None:
        direct_paragraphs = _direct(container, "p")
        if direct_paragraphs and _local(container) == "body":
            append_section("Body", direct_paragraphs)
        for section in _direct(container, "sec"):
            title = _text(next(iter(_direct(section, "title")), None))
            append_section(title or "Body", _direct(section, "p"))
            walk(section)

    assert body is not None
    walk(body)
    prose = [block.text for block in blocks if block.kind == "body"]
    return JATSExtraction(
        path=path,
        blocks=blocks,
        full_text="\n\n".join(prose),
        total_sentences=total,
        aligned_sentences=aligned,
        alignment_ratio=round(aligned / total, 4) if total else 0.0,
        aligned_words=sum(word_count(text) for text in prose),
        section_titles=list(dict.fromkeys(section_titles)),
        article_type=normalize_prose(root.attrib.get("article-type", "")).replace("-", " ").title(),
    )


__all__ = ["JATSExtraction", "extract_jats"]
