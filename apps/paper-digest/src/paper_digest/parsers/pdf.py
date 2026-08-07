from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import pymupdf

from ..models import TextBlock
from ..text import clean_line, normalize_prose


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


def _block_font(block: dict) -> tuple[float, str]:
    sizes: list[float] = []
    names: list[str] = []
    for line in block.get("lines", []):
        for span in line.get("spans", []):
            text = span.get("text", "").strip()
            if text:
                sizes.append(float(span.get("size", 0.0)))
                names.append(str(span.get("font", "")))
    return (max(sizes, default=0.0), Counter(names).most_common(1)[0][0] if names else "")


def _text_from_block(block: dict) -> str:
    lines: list[str] = []
    for line in block.get("lines", []):
        parts: list[str] = []
        previous_span: dict | None = None
        for span in line.get("spans", []):
            value = str(span.get("text", ""))
            if parts and parts[-1][-1:].isalnum() and value[:1].isalnum():
                previous_box = (previous_span or {}).get("bbox", (0, 0, 0, 0))
                current_box = span.get("bbox", (0, 0, 0, 0))
                gap = float(current_box[0]) - float(previous_box[2])
                size = max(float(span.get("size", 0.0)), float((previous_span or {}).get("size", 0.0)))
                if gap > max(0.8, size * 0.12):
                    parts.append(" ")
            parts.append(value)
            previous_span = span
        text = "".join(parts)
        text = clean_line(text)
        if text:
            lines.append(text)
    return "\n".join(lines)


def _column_order(items: list[dict], width: float) -> list[dict]:
    # Publisher PDFs often have two columns. Preserve top-spanning blocks first,
    # then left and right columns in reading order. Do not apply to title pages.
    spanning: list[dict] = []
    left: list[dict] = []
    right: list[dict] = []
    middle = width / 2
    for item in items:
        x0, y0, x1, y1 = item["bbox"]
        if x0 < width * 0.22 and x1 > width * 0.78:
            spanning.append(item)
        elif (x0 + x1) / 2 <= middle:
            left.append(item)
        else:
            right.append(item)

    def key(item: dict) -> tuple[float, float]:
        return (round(item["bbox"][1], 1), item["bbox"][0])

    spanning.sort(key=key)
    left.sort(key=key)
    right.sort(key=key)
    # Keep true page-top spanning items before columns; later full-width figures
    # and captions are appended after text to avoid interleaving columns.
    top = [item for item in spanning if item["bbox"][1] < 110]
    rest = [item for item in spanning if item not in top]
    return top + left + right + sorted(rest, key=key)


def _kind(text: str, size: float, median_size: float, y0: float, height: float, page: int) -> str:
    stripped = text.strip()
    if page == 1 and size >= max(15.0, median_size * 1.35) and y0 < height * 0.42:
        return "title"
    if y0 < height * 0.07 or y0 > height * 0.93:
        return "header" if y0 < height * 0.07 else "footer"
    if size >= median_size * 1.20 and len(stripped) < 180:
        return "heading"
    if re.match(
        r"^(?:Abstract|Introduction|Results|Discussion|Methods|References|Data availability|Code availability|Limitations)\b",
        stripped,
        re.I,
    ):
        return "heading"
    return "body"


def extract_pdf(path: Path, *, enable_ocr: bool = True, ocr_language: str = "eng") -> PDFExtraction:
    document = pymupdf.open(path)
    all_blocks: list[TextBlock] = []
    page_texts: list[str] = []
    ocr_pages: list[int] = []
    figure_caption_count = 0
    table_caption_count = 0
    for page_index, page in enumerate(document, start=1):
        raw_text = page.get_text("text")
        text_page = None
        extraction_method = "text-layer"
        if enable_ocr and len(normalize_prose(raw_text).split()) < 20:
            try:
                text_page = page.get_textpage_ocr(language=ocr_language, dpi=220, full=True)
                ocr_pages.append(page_index)
                extraction_method = "tesseract-ocr"
            except RuntimeError:
                text_page = None
        raw = page.get_text("dict", textpage=text_page)
        items: list[dict] = []
        sizes: list[float] = []
        for block in raw.get("blocks", []):
            if block.get("type") != 0:
                continue
            text = _text_from_block(block)
            if not text:
                continue
            size, font = _block_font(block)
            bbox = tuple(float(v) for v in block.get("bbox", (0, 0, 0, 0)))
            items.append({"text": text, "size": size, "font": font, "bbox": bbox})
            if size:
                sizes.append(size)
        median_size = sorted(sizes)[len(sizes) // 2] if sizes else 10.0
        ordered = (
            sorted(items, key=lambda item: (item["bbox"][1], item["bbox"][0]))
            if page_index == 1
            else _column_order(items, page.rect.width)
        )
        page_lines: list[str] = []
        for item in ordered:
            kind = _kind(item["text"], item["size"], median_size, item["bbox"][1], page.rect.height, page_index)
            block = TextBlock(
                text=item["text"],
                page=page_index,
                bbox=item["bbox"],
                font_size=item["size"],
                font_name=item["font"],
                kind=kind,
                source_file=path.name,
                extraction_method=extraction_method,
            )
            all_blocks.append(block)
            normalized_item = normalize_prose(item["text"])
            if re.match(r"^(?:Fig(?:ure)?\.?\s*\d+|Extended Data Fig(?:ure)?\.?\s*\d+)", normalized_item, re.I):
                figure_caption_count += 1
            if re.match(r"^(?:Table|Extended Data Table)\s*\d+", normalized_item, re.I):
                table_caption_count += 1
            if kind not in {"header", "footer"}:
                page_lines.append(item["text"])
        page_texts.append("\n".join(page_lines))
    document.close()

    # Remove recurring headers/footers and isolated page numbers from full text.
    recurrence = Counter(normalize_prose(b.text) for b in all_blocks if b.kind in {"header", "footer"})
    usable: list[str] = []
    for block in all_blocks:
        text = normalize_prose(block.text)
        if not text:
            continue
        if block.kind in {"header", "footer"} and (recurrence[text] >= 2 or re.fullmatch(r"\d+", text)):
            continue
        usable.append(block.text)
    full_text = "\n\n".join(usable)
    return PDFExtraction(
        path=path,
        blocks=all_blocks,
        page_texts=page_texts,
        full_text=full_text,
        page_count=len(page_texts),
        extractor=(f"pymupdf-{pymupdf.VersionBind}+tesseract-ocr" if ocr_pages else f"pymupdf-{pymupdf.VersionBind}"),
        ocr_pages=ocr_pages,
        figure_caption_count=figure_caption_count,
        table_caption_count=table_caption_count,
    )
