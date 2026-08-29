from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import pymupdf

from ..models import TextBlock
from ..text import normalize_prose
from . import layout as L


@dataclass(slots=True)
class LabelledField:
    """A publisher "Label: value" record with the page it was read from."""

    label: str
    value: str
    page: int


@dataclass(slots=True)
class PDFExtraction:
    path: Path
    blocks: list[TextBlock]
    page_texts: list[str]
    full_text: str
    page_count: int
    extractor: str
    ocr_pages: list[int]
    figure_caption_count: int
    table_caption_count: int
    # Structural detail used by metadata resolution, grounding and QA.
    grounding_text: str = ""
    metadata_fields: list[LabelledField] = field(default_factory=list)
    doc_info: dict[str, str] = field(default_factory=dict)
    cover_pages: list[int] = field(default_factory=list)
    running_heads: dict[str, list[str]] = field(default_factory=dict)
    front_matter: L.FrontMatter = field(default_factory=L.FrontMatter)
    body_font_size: float = 10.0

    def text_of(self, *kinds: str) -> str:
        wanted = set(kinds)
        return "\n".join(normalize_prose(b.text) for b in self.blocks if b.kind in wanted and b.text.strip())

    def fields(self, *labels: str) -> list[LabelledField]:
        wanted = {label.casefold() for label in labels}
        return [item for item in self.metadata_fields if item.label in wanted]

    def field_value(self, *labels: str) -> LabelledField | None:
        found = self.fields(*labels)
        return found[0] if found else None


def _page_tables(page: pymupdf.Page) -> list[L.BBox]:
    try:
        found = page.find_tables()
    except Exception:  # PyMuPDF raises assorted errors on malformed pages.
        return []
    boxes: list[L.BBox] = []
    for table in getattr(found, "tables", []):
        try:
            if table.row_count >= 3 and table.col_count >= 2:
                boxes.append(tuple(float(v) for v in table.bbox))
        except Exception:
            continue
    return boxes


def _collect_metadata_fields(pages: list[L.RawPage]) -> list[LabelledField]:
    """Harvest publisher "Label: value" blocks (Citation, Received, DOI, ...)."""
    fields: list[LabelledField] = []
    for page in pages:
        if page.number > 4:
            break
        for block in page.blocks:
            text = normalize_prose(block.text)
            labelled = L.METADATA_LABEL_RE.match(text)
            if labelled:
                label, value = labelled.group(1), labelled.group(2)
            elif L.BANNER_LABEL_RE.match(text) and ":" in text:
                label, value = text.split(":", 1)
            else:
                continue
            key = re.sub(r"\s+", " ", label).strip().casefold()
            value = normalize_prose(value).strip()
            if value:
                fields.append(LabelledField(label=key, value=value, page=page.number))
    return fields


# "Son H, Song S & Rhee J C (2007) Histopathology 51, 105-110" — a publisher
# self-citation printed on the opening page with no label in front of it.
UNLABELLED_CITATION_RE = re.compile(r"\((?:19|20)\d{2}\)")
CITATION_LOCATOR_RE = re.compile(r"\b\d{1,4}\s*[,:]\s*\d{1,5}\s*[-–]\s*\d{1,5}\b|\b\d{1,4}\s*\(\d{1,4}\)")


def _unlabelled_citations(blocks: list[TextBlock]) -> list[LabelledField]:
    """Front-page citation strings that carry no "Citation:" label."""
    found: list[LabelledField] = []
    for block in blocks:
        if block.page > 2:
            break
        if block.kind in {"body", "abstract", "heading", "reference", "title", "authors"}:
            continue
        text = normalize_prose(block.text)
        if not UNLABELLED_CITATION_RE.search(text) or not CITATION_LOCATOR_RE.search(text):
            continue
        if not 6 <= len(text.split()) <= 80:
            continue
        if re.search(r"^\s*(?:©|\(c\))", text) or re.search(r"\breferences?\b", text, re.I):
            continue
        found.append(LabelledField(label="citation", value=text, page=block.page))
    return found


def _reset_kinds(pages: list[L.RawPage]) -> None:
    for page in pages:
        for block in page.blocks:
            if block.kind not in {"header", "footer"}:
                block.kind = "body"


def extract_pdf(path: Path, *, enable_ocr: bool = True, ocr_language: str = "eng") -> PDFExtraction:
    document = pymupdf.open(path)
    pages: list[L.RawPage] = []
    ocr_pages: list[int] = []
    doc_info = {
        key: normalize_prose(str(value))
        for key, value in (document.metadata or {}).items()
        if value and isinstance(value, str)
    }
    try:
        for page_index, page in enumerate(document, start=1):
            raw_text = page.get_text("text")
            text_page = None
            method = "text-layer"
            if enable_ocr and len(normalize_prose(raw_text).split()) < 20:
                try:
                    text_page = page.get_textpage_ocr(language=ocr_language, dpi=220, full=True)
                    ocr_pages.append(page_index)
                    method = "tesseract-ocr"
                except RuntimeError:
                    text_page = None
            raw = page.get_text("dict", textpage=text_page)
            raw_page = L.build_raw_page(raw, page_index, page.rect.width, page.rect.height, method)
            raw_page.table_boxes = _page_tables(page)
            pages.append(raw_page)
    finally:
        document.close()

    running = L.mark_running_heads(pages)
    cover_pages = L.detect_cover_pages(pages)
    metadata_fields = _collect_metadata_fields(pages)

    # Two passes: the first modal size is skewed by dense reference and table
    # text, so re-estimate from blocks the first pass called body and re-classify.
    L.classify_blocks(pages, L.body_font_size(pages), cover_pages)
    body_size = L.body_font_size(pages, only_body=True)
    _reset_kinds(pages)
    L.classify_blocks(pages, body_size, cover_pages)
    L.assign_columns(pages)
    front_matter = L.mark_front_matter(pages, body_size, cover_pages)
    L.mark_abstract(pages, cover_pages)

    all_blocks: list[TextBlock] = []
    page_texts: list[str] = []
    grounding_parts: list[str] = []
    figure_caption_count = 0
    table_caption_count = 0
    for page in pages:
        page_lines: list[str] = []
        for block in L.order_page(page):
            all_blocks.append(
                TextBlock(
                    text=block.text,
                    page=block.page,
                    bbox=block.bbox,
                    font_size=block.size,
                    font_name=block.font,
                    kind=block.kind,
                    source_file=path.name,
                    extraction_method=block.extraction_method,
                )
            )
            normalized = normalize_prose(block.text)
            if not normalized:
                continue
            if block.kind == "caption":
                if re.match(r"^\s*(?:supplementary\s+|extended data\s+)?fig", normalized, re.I):
                    figure_caption_count += 1
                elif re.match(r"^\s*(?:supplementary\s+|extended data\s+)?table", normalized, re.I):
                    table_caption_count += 1
            if block.kind in L.PROSE_KINDS:
                page_lines.append(block.text)
        page_texts.append("\n".join(page_lines))

    # The grounding index has two parts: the prose stream in the exact order
    # section segmentation walks it, so a sentence that continues across a
    # dropped chart label stays contiguous; then everything else, so a quoted
    # caption or table cell can still be verified.
    prose_stream = normalize_prose(
        "\n".join(block.text for block in all_blocks if block.kind in L.PROSE_KINDS and block.text.strip())
    )
    other_text = "\n".join(
        normalize_prose(block.text) for block in all_blocks if block.kind not in L.PROSE_KINDS and block.text.strip()
    )
    grounding_parts = [prose_stream, other_text]
    full_text = "\n\n".join(
        normalize_prose(block.text) for block in all_blocks if block.kind in L.PROSE_KINDS and block.text.strip()
    )
    if not full_text.strip():
        # Structural classification claimed everything. Fall back to all
        # readable text so a degenerate document still produces a record.
        full_text = "\n\n".join(
            normalize_prose(block.text)
            for block in all_blocks
            if block.kind not in {"header", "footer", "decoration"} and block.text.strip()
        )
    metadata_fields.extend(_unlabelled_citations(all_blocks))
    version = pymupdf.VersionBind
    return PDFExtraction(
        path=path,
        blocks=all_blocks,
        page_texts=page_texts,
        full_text=full_text,
        page_count=len(pages),
        extractor=(f"pymupdf-{version}+tesseract-ocr" if ocr_pages else f"pymupdf-{version}"),
        ocr_pages=ocr_pages,
        figure_caption_count=figure_caption_count,
        table_caption_count=table_caption_count,
        grounding_text="\n".join(grounding_parts),
        metadata_fields=metadata_fields,
        cover_pages=sorted(cover_pages),
        running_heads=running,
        front_matter=front_matter,
        body_font_size=body_size,
        doc_info=doc_info,
    )
