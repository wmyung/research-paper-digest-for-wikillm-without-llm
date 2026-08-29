"""Deterministic page-layout analysis for publisher PDFs.

Raw PyMuPDF blocks are turned into reading-ordered, kind-tagged blocks. Every
decision is geometric or lexical: column gutters come from an x-coverage
histogram, running heads from cross-page recurrence, tables from short-line and
numeric density, and the front matter from the zone above the abstract. No
model is loaded and no text leaves the process.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from ..text import clean_line, has_finite_verb, normalize_prose, word_count

BBox = tuple[float, float, float, float]

# Kinds that carry scientific prose. Everything else is structural furniture and
# is skipped by section segmentation.
PROSE_KINDS = frozenset({"body", "heading", "abstract"})
FRONT_MATTER_KINDS = frozenset({"title", "authors", "affiliation", "front-matter"})

DEPOSIT_BANNER_RE = re.compile(
    r"white rose research online|this is a repository copy|deposited via|eprints?@|"
    r"research online url for this paper|downloaded from https?://|"
    r"this article is protected by copyright\. all rights reserved|"
    r"is the author'?s? version of a work that was accepted for publication",
    re.I,
)
BANNER_LABEL_RE = re.compile(r"^(?:version|reuse|takedown|citation for published version|article)\s*:", re.I)
ARTICLE_TYPE_RE = re.compile(
    r"^\s*(?:(?:original|research|review|short|brief|full[- ]length|systematic|clinical|special|open|invited|"
    r"regular|technical|rapid|original research)\s+)?"
    r"(?:article|research|paper|report|communication|review|letter|editorial|commentary|perspective|"
    r"correspondence|note|methods?|resource|protocol|case report|viewpoint|study protocol|"
    r"systematic review|meta-analysis|guideline|consensus statement|research article|original article)"
    r"(?:\s+(?:article|paper|in press))?\s*$",
    re.I,
)
DISPLAY_CAPTION_RE = re.compile(
    r"^\s*(?:supplementary\s+|extended\s+data\s+|appendix\s+|online\s+)?"
    r"(?:table|box|scheme|exhibit|panel|chart)\s*(?:s\s*)?\d+",
    re.I,
)
CAPTION_RE = re.compile(
    r"^\s*(?:supplementary\s+|extended\s+data\s+|appendix\s+|online\s+|s)?"
    r"(?:fig(?:ure)?|table|scheme|box|chart|panel|exhibit)\s*"
    r"(?:s\s*)?\d+[a-z]?\s*[.:|)–—-]?\s",
    re.I,
)
SECTION_HEADING_RE = re.compile(
    r"^\s*(?:\d+(?:\.\d+)*\.?\s+|[IVX]+\.\s+)?"
    r"(?:abstract|summary|background|introduction|rationale|objectives?|aims?|purpose|"
    r"methods?|materials and methods|patients and methods|study design|participants|"
    r"statistical analysis(?:es)?|results?|findings?|discussion|conclusions?|interpretation|"
    r"limitations?|strengths and limitations|data availability|code availability|"
    r"references?|acknowledge?ments?|funding|author contributions?|competing interests?|"
    r"conflicts? of interest|supporting information|ethics(?: statement| approval)?)"
    r"\s*[.:]?\s*$",
    re.I,
)
REFERENCE_HEADING_RE = re.compile(
    r"^\s*(?:\d+\.?\s*)?(?:references?|bibliography|literature cited|works cited|reference list)\s*$",
    re.I,
)
POST_REFERENCE_HEADING_RE = re.compile(
    r"^\s*(?:\d+\.?\s*)?(?:appendix|appendices|supporting information|supplementary (?:material|information|data)|"
    r"supplemental (?:material|information)|author information|about the authors?)\b",
    re.I,
)
# Prefix alternatives on purpose: "universit" covers university/université/
# universiteit. No trailing word boundary, or the prefixes could never match.
AFFILIATION_RE = re.compile(
    r"\b(?:universit|universid|institut|departmen|departamento|dipartimento|facult|school of|colleg|"
    r"hospital|clinic|centre|center|laborator|academy|foundation|ministry|agency|research group|"
    r"division of|unit of|inc\.|ltd\b|gmbh|medical cent|health service|nhs |cnrs|inserm|max planck|"
    r"national institute|consortium|corporation)",
    re.I,
)
AUTHOR_NOTE_RE = re.compile(
    r"^\s*(?:[☯‡†¶§*¤#]|these authors|current address|equal contribution|joint (?:first|senior)|e-?mail(?: address)?\b|corresponding author\b)",
    re.I,
)
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
METADATA_LABEL_RE = re.compile(
    r"^\s*(citation|editor|received|revised|accepted|published(?:\s+online)?|"
    r"available online|first published|online first|copyright|funding|competing interests?|"
    r"conflicts? of interest|data availability(?: statement)?|code availability|"
    r"correspondence|corresponding author|keywords?|key words|abbreviations|"
    r"how to cite(?: this article)?|cite this article as|please cite this article as|"
    r"article history|doi|issn|open access|licen[cs]e|peer review|"
    r"author contributions?|acknowledge?ments?|orcid|trial registration|registration)\s*[::]\s*(.+)$",
    re.I | re.S,
)
DECORATION_RE = re.compile(
    r"^(?:open access|check for updates|updates|open|access|free|"
    r"([a-z0-9])\1{4,}|[\W\d_]+|[a-z]?\d{6,}[a-z]?)$",
    re.I,
)
NAME_TOKEN_RE = re.compile(r"\b[A-ZÀ-ÖØ-Þ][a-zà-öø-ÿ'’-]{1,}\b")
INITIAL_TOKEN_RE = re.compile(r"\b[A-ZÀ-ÖØ-Þ]\.")
CITATION_DENSITY_RE = re.compile(r"\(\d{4}[a-z]?\)|\b\d{4};\s*\d|\bet al\.|\bdoi\s*:|\bpp?\.\s*\d+[-–]\d+")


@dataclass(slots=True)
class RawLine:
    text: str
    bbox: BBox
    size: float
    font: str


@dataclass(slots=True)
class RawBlock:
    text: str
    lines: list[RawLine]
    bbox: BBox
    size: float
    font: str
    page: int
    kind: str = "body"
    column: int = 0
    extraction_method: str = "text-layer"

    @property
    def width(self) -> float:
        return self.bbox[2] - self.bbox[0]

    @property
    def height(self) -> float:
        return self.bbox[3] - self.bbox[1]


@dataclass(slots=True)
class RawPage:
    number: int
    width: float
    height: float
    blocks: list[RawBlock] = field(default_factory=list)
    table_boxes: list[BBox] = field(default_factory=list)
    columns: list[tuple[float, float]] = field(default_factory=list)
    extraction_method: str = "text-layer"


@dataclass(slots=True)
class FrontMatter:
    title: str = ""
    article_type: str = ""
    author_text: str = ""
    affiliation_text: str = ""
    opening_page: int = 1


# --------------------------------------------------------------------------
# Raw block construction
# --------------------------------------------------------------------------


def _span_text(line: dict) -> tuple[str, float, str]:
    parts: list[str] = []
    sizes: list[float] = []
    fonts: list[str] = []
    previous: dict | None = None
    for span in line.get("spans", []):
        value = str(span.get("text", ""))
        if not value:
            continue
        if parts and parts[-1][-1:].isalnum() and value[:1].isalnum():
            previous_box = (previous or {}).get("bbox", (0, 0, 0, 0))
            current_box = span.get("bbox", (0, 0, 0, 0))
            gap = float(current_box[0]) - float(previous_box[2])
            size = max(float(span.get("size", 0.0)), float((previous or {}).get("size", 0.0)))
            if gap > max(0.8, size * 0.12):
                parts.append(" ")
        parts.append(value)
        if value.strip():
            sizes.append(float(span.get("size", 0.0)))
            fonts.append(str(span.get("font", "")))
        previous = span
    text = clean_line("".join(parts))
    return text, max(sizes, default=0.0), (Counter(fonts).most_common(1)[0][0] if fonts else "")


def build_raw_page(page_dict: dict, number: int, width: float, height: float, method: str) -> RawPage:
    page = RawPage(number=number, width=width, height=height, extraction_method=method)
    for block in page_dict.get("blocks", []):
        if block.get("type") != 0:
            continue
        lines: list[RawLine] = []
        for line in block.get("lines", []):
            text, size, font = _span_text(line)
            if not text:
                continue
            lines.append(
                RawLine(text=text, bbox=tuple(float(v) for v in line.get("bbox", (0, 0, 0, 0))), size=size, font=font)
            )
        if not lines:
            continue
        sizes = [line.size for line in lines]
        fonts = [line.font for line in lines]
        page.blocks.append(
            RawBlock(
                text="\n".join(line.text for line in lines),
                lines=lines,
                bbox=tuple(float(v) for v in block.get("bbox", (0, 0, 0, 0))),
                size=max(sizes, default=0.0),
                font=Counter(fonts).most_common(1)[0][0] if fonts else "",
                page=number,
                extraction_method=method,
            )
        )
    return page


# --------------------------------------------------------------------------
# Text shape probes
# --------------------------------------------------------------------------


def _short_line_ratio(block: RawBlock) -> float:
    if not block.lines:
        return 0.0
    return sum(1 for line in block.lines if word_count(line.text) <= 4) / len(block.lines)


def _numeric_ratio(text: str) -> float:
    words = re.findall(r"\S+", text)
    if not words:
        return 0.0
    return sum(1 for word in words if re.search(r"\d", word)) / len(words)


def is_reference_like(text: str) -> bool:
    hits = len(CITATION_DENSITY_RE.findall(text))
    words = max(1, word_count(text))
    return hits >= 2 and hits / words * 100 >= 2.0


def _looks_like_names(text: str) -> bool:
    """A byline: several capitalised name tokens, no finite verb, comma-separated."""
    value = normalize_prose(text)
    if word_count(value) > 260 or has_finite_verb(value):
        return False
    names = NAME_TOKEN_RE.findall(value)
    initials = INITIAL_TOKEN_RE.findall(value)
    if len(names) + len(initials) < 3:
        return False
    if AFFILIATION_RE.search(value):
        return False
    letters = sum(character.isalpha() for character in value)
    if not letters:
        return False
    capitals = sum(character.isupper() for character in value)
    separators = value.count(",") + value.count("&") + len(re.findall(r"\band\b", value, re.I))
    return separators >= 1 and capitals / letters >= 0.10


def _is_affiliation(text: str) -> bool:
    if AUTHOR_NOTE_RE.match(text):
        return True
    if EMAIL_RE.search(text) and word_count(text) < 40:
        return True
    if not AFFILIATION_RE.search(text):
        return False
    # An affiliation is a place, not a claim: a finite verb rules it out.
    if has_finite_verb(text):
        return False
    commas = text.count(",")
    return commas >= 1 and word_count(text) / max(1, commas) < 16


def _is_table_like(block: RawBlock, text: str) -> bool:
    words = word_count(text)
    numeric = _numeric_ratio(text)
    if words <= 2:
        return not re.fullmatch(r"[A-Za-z][A-Za-z -]{2,}", text.strip())
    if len(block.lines) >= 3 and _short_line_ratio(block) >= 0.65:
        return True
    if numeric >= 0.32 and words >= 6:
        return True
    if words >= 10 and not has_finite_verb(text) and numeric >= 0.10:
        return True
    return False


def _is_heading(block: RawBlock, text: str, body_size: float) -> bool:
    words = word_count(text)
    if words == 0 or words > 16:
        return False
    if SECTION_HEADING_RE.match(text):
        return True
    # Bold table-header cells are set below the running-text size; a section
    # heading never is.
    if block.size < body_size * 0.98:
        return False
    if text.rstrip().endswith((".", ";", ",", ":")) and words > 6:
        return False
    bold = "bold" in block.font.casefold() or "black" in block.font.casefold()
    larger = block.size >= body_size * 1.06
    if not (bold or larger):
        return False
    if len(block.lines) > 2:
        return False
    # A heading is a label, not a clause: reject anything sentence-shaped.
    return not (words > 8 and has_finite_verb(text))


# --------------------------------------------------------------------------
# Page geometry
# --------------------------------------------------------------------------


def body_font_size(pages: list[RawPage], only_body: bool = False) -> float:
    """Char-weighted modal size of running prose."""
    weights: Counter[float] = Counter()
    for page in pages:
        for block in page.blocks:
            if only_body and block.kind not in {"body", "abstract"}:
                continue
            if word_count(block.text) < 25:
                continue
            for line in block.lines:
                if line.size:
                    weights[round(line.size, 1)] += len(line.text)
    if not weights:
        return 10.0
    return weights.most_common(1)[0][0]


def detect_columns(blocks: list[RawBlock], width: float, height: float) -> list[tuple[float, float]]:
    """Find column bands from vertical whitespace gutters in the x projection."""
    usable = [b for b in blocks if b.width > 4 and b.height > 4]
    if len(usable) < 4:
        return [(0.0, width)]
    bin_size = 4.0
    bins = max(8, int(width / bin_size) + 1)
    coverage = [0.0] * bins
    for block in usable:
        start = max(0, int(block.bbox[0] / bin_size))
        end = min(bins - 1, int(block.bbox[2] / bin_size))
        for index in range(start, end + 1):
            coverage[index] += block.height
    threshold = height * 0.06
    gutters: list[tuple[int, int]] = []
    run_start: int | None = None
    for index, value in enumerate(coverage):
        if value <= threshold:
            run_start = index if run_start is None else run_start
        elif run_start is not None:
            gutters.append((run_start, index - 1))
            run_start = None
    if run_start is not None:
        gutters.append((run_start, bins - 1))
    interior = [
        (start * bin_size, (end + 1) * bin_size)
        for start, end in gutters
        if start > 0 and end < bins - 1 and (end - start + 1) * bin_size >= 10.0
    ]
    if not interior:
        return [(0.0, width)]
    bounds: list[tuple[float, float]] = []
    cursor = 0.0
    for gutter_start, gutter_end in interior:
        if gutter_start - cursor >= width * 0.08:
            bounds.append((cursor, gutter_start))
        cursor = gutter_end
    if width - cursor >= width * 0.08:
        bounds.append((cursor, width))
    return bounds or [(0.0, width)]


def _column_of(block: RawBlock, columns: list[tuple[float, float]]) -> int:
    """Column index, or -1 for a block spanning several columns."""
    if len(columns) == 1:
        return 0
    block_width = max(1.0, block.bbox[2] - block.bbox[0])
    overlaps = [
        (index, max(0.0, min(block.bbox[2], right) - max(block.bbox[0], left)))
        for index, (left, right) in enumerate(columns)
    ]
    # Spanning means covering most of two or more column bands.
    spanning = [index for index, overlap in overlaps if overlap >= (columns[index][1] - columns[index][0]) * 0.5]
    if len(spanning) >= 2:
        return -1
    # Otherwise the block belongs wherever most of its own width sits. A narrow
    # heading inside a wide column must not be pulled into a neighbouring one.
    inside = [index for index, overlap in overlaps if overlap / block_width >= 0.6]
    if inside:
        return max(inside, key=lambda index: dict(overlaps)[index])
    centre = (block.bbox[0] + block.bbox[2]) / 2
    return min(range(len(columns)), key=lambda i: abs(centre - (columns[i][0] + columns[i][1]) / 2))


def order_page(page: RawPage) -> list[RawBlock]:
    """Reading order: a full-width block is a barrier that flushes the columns."""
    columns = page.columns or [(0.0, page.width)]
    for block in page.blocks:
        block.column = _column_of(block, columns)
    ordered: list[RawBlock] = []
    buffers: dict[int, list[RawBlock]] = defaultdict(list)

    def flush() -> None:
        for index in range(len(columns)):
            ordered.extend(sorted(buffers.pop(index, []), key=lambda b: (round(b.bbox[1], 1), b.bbox[0])))
        buffers.clear()

    for block in sorted(page.blocks, key=lambda b: (round(b.bbox[1], 1), b.bbox[0])):
        if block.column == -1:
            flush()
            ordered.append(block)
        else:
            buffers[block.column].append(block)
    flush()
    return ordered


def assign_columns(pages: list[RawPage]) -> None:
    for page in pages:
        page.columns = detect_columns(
            [b for b in page.blocks if b.kind not in {"header", "footer"}], page.width, page.height
        )


# --------------------------------------------------------------------------
# Document-level structure
# --------------------------------------------------------------------------


def _running_key(text: str) -> str:
    value = re.sub(r"\d+", "#", normalize_prose(text).casefold())
    return re.sub(r"\s+", " ", value).strip()


def mark_running_heads(pages: list[RawPage]) -> dict[str, list[str]]:
    """Tag repeated top/bottom-of-page blocks as header/footer.

    Recurrence, not position alone, makes a running head; digits are masked
    first so page numbers and dates do not defeat the match.
    """
    total = len(pages)
    captured: dict[str, list[str]] = {"header": [], "footer": []}
    if total >= 2:
        occurrences: dict[tuple[str, str], list[RawBlock]] = defaultdict(list)
        for page in pages:
            for block in page.blocks:
                if block.bbox[1] <= page.height * 0.09:
                    band = "header"
                elif block.bbox[3] >= page.height * 0.91:
                    band = "footer"
                else:
                    continue
                key = _running_key(block.text)
                if key and len(key) > 2:
                    occurrences[(band, key)].append(block)
        needed = max(2, round(total * 0.4))
        for (band, _key), blocks in occurrences.items():
            pages_seen = {block.page for block in blocks}
            if len(pages_seen) < needed:
                continue
            for block in blocks:
                block.kind = band
            captured[band].append(normalize_prose(blocks[0].text))
    for page in pages:
        for block in page.blocks:
            if block.kind in {"header", "footer"}:
                continue
            value = normalize_prose(block.text)
            if re.fullmatch(r"[\divxlcIVXLC]{1,6}(?:\s*(?:/|of)\s*\d{1,4})?", value):
                if block.bbox[1] <= page.height * 0.09:
                    block.kind = "header"
                elif block.bbox[3] >= page.height * 0.91:
                    block.kind = "footer"
    return captured


def detect_cover_pages(pages: list[RawPage]) -> set[int]:
    """Repository / accepted-manuscript cover sheets preceding the article."""
    covers: set[int] = set()
    for page in pages[: min(3, len(pages))]:
        text = normalize_prose(" ".join(block.text for block in page.blocks))
        if not text or not DEPOSIT_BANNER_RE.search(text):
            continue
        # A genuine opening page carries a long abstract; a cover sheet is short
        # link-heavy boilerplate.
        if re.search(r"\babstract\b", text, re.I) and word_count(text) > 400:
            continue
        covers.add(page.number)
    return covers


def _page_opens_small(page: RawPage, body_size: float) -> bool:
    """True when a page continues a table that started on the previous page."""
    for block in sorted(page.blocks, key=lambda b: b.bbox[1]):
        if block.kind in {"header", "footer"} or not normalize_prose(block.text):
            continue
        return block.size < body_size * 0.98
    return False


def _overlaps(inner: BBox, outer: BBox, ratio: float = 0.5) -> bool:
    width = min(inner[2], outer[2]) - max(inner[0], outer[0])
    height = min(inner[3], outer[3]) - max(inner[1], outer[1])
    if width <= 0 or height <= 0:
        return False
    area = max(1e-6, (inner[2] - inner[0]) * (inner[3] - inner[1]))
    return (width * height) / area >= ratio


def classify_blocks(pages: list[RawPage], body_size: float, cover_pages: set[int]) -> None:
    """Assign a structural kind to every block without a running-head tag."""
    reference_zone = False
    # Affiliations only ever appear in the front matter, before the abstract or
    # the introduction; after that a "University of ..." line is ordinary prose.
    front_zone = True
    table_zone = False
    for page in pages:
        table_zone = table_zone and _page_opens_small(page, body_size)
        for block in page.blocks:
            if block.kind in {"header", "footer"}:
                continue
            text = normalize_prose(block.text)
            if not text:
                block.kind = "decoration"
                continue
            if page.number in cover_pages:
                block.kind = "banner"
                continue
            if REFERENCE_HEADING_RE.match(text):
                reference_zone = True
                block.kind = "reference"
                continue
            if reference_zone and POST_REFERENCE_HEADING_RE.match(text):
                reference_zone = False
            # Tables and boxes are often typeset after the reference list.
            if reference_zone and DISPLAY_CAPTION_RE.match(text):
                reference_zone = False
            if reference_zone:
                block.kind = "reference"
                continue
            if METADATA_LABEL_RE.match(text) or BANNER_LABEL_RE.match(text):
                block.kind = "metadata-field"
                continue
            if CAPTION_RE.match(text):
                block.kind = "caption"
                table_zone = DISPLAY_CAPTION_RE.match(text) is not None
                continue
            small_print = block.size < body_size * 0.98
            # Everything set below the running-text size after a table or box
            # caption is display matter: cells, column heads and footnotes.
            if table_zone and small_print:
                block.kind = "table"
                continue
            if table_zone and not small_print and word_count(text) >= 20:
                table_zone = False
            if DECORATION_RE.match(text):
                block.kind = "decoration"
                continue
            if _is_heading(block, text, body_size):
                block.kind = "heading"
                if front_zone and re.match(
                    r"^\s*(?:\d+\.?\s*)?(?:introduction|background|abstract|summary)\b", text, re.I
                ):
                    front_zone = False
                continue
            if front_zone and page.number <= 4 and _is_affiliation(text):
                block.kind = "affiliation"
                continue
            if any(_overlaps(block.bbox, box) for box in page.table_boxes):
                block.kind = "table"
                continue
            if is_reference_like(text) and word_count(text) >= 15:
                block.kind = "reference"
                continue
            if _is_table_like(block, text):
                block.kind = "table"
                continue
            # A standalone one-to-three word block that is not a heading is a
            # chart axis label or a legend key, and must not fuse into prose.
            if word_count(text) <= 3 and not text.rstrip().endswith((".", "!", "?")):
                block.kind = "decoration"
                continue
            block.kind = "body"


def _strip_article_type(text: str) -> tuple[str, str]:
    """Split a leading "RESEARCH ARTICLE" style label off a title block."""
    lines = [line for line in text.splitlines() if line.strip()]
    label = ""
    while lines and ARTICLE_TYPE_RE.match(normalize_prose(lines[0])):
        label = normalize_prose(lines[0]).title()
        lines = lines[1:]
    remainder = normalize_prose("\n".join(lines))
    if not label:
        # Some publishers set the label inline: "RESEARCH ARTICLE The PRISMA ..."
        inline = re.match(
            r"^\s*((?:ORIGINAL|RESEARCH|REVIEW|SHORT|BRIEF|SYSTEMATIC|CLINICAL|SPECIAL|INVITED|TECHNICAL)?\s*"
            r"(?:ARTICLE|RESEARCH|PAPER|REPORT|COMMUNICATION|REVIEW|LETTER|EDITORIAL|COMMENTARY|PROTOCOL))\s+"
            r"(?=[A-Z])",
            remainder,
        )
        if inline and len(remainder) - inline.end() > 20:
            label = inline.group(1).title()
            remainder = remainder[inline.end() :].strip()
    return remainder, label


def mark_front_matter(pages: list[RawPage], body_size: float, cover_pages: set[int]) -> FrontMatter:
    """Resolve title, byline and affiliations from the zone above the abstract."""
    opening = next((page for page in pages if page.number not in cover_pages), None)
    if opening is None:
        return FrontMatter()
    ordered = order_page(opening)
    main_column = _main_column(opening)
    zone_end = _abstract_top(ordered, opening)
    zone = [
        block
        for block in ordered
        if block.kind not in {"header", "footer", "banner", "metadata-field", "caption", "decoration", "reference"}
        and block.bbox[1] < zone_end
        and (main_column is None or block.column in {main_column, -1})
    ]
    front = FrontMatter(opening_page=opening.number)
    title_block = _score_title(zone, body_size, opening)
    if title_block is None:
        return front
    members = [title_block] + _title_continuations(zone, title_block)
    for block in members:
        block.kind = "title"
    raw_title = normalize_prose(" ".join(block.text for block in members))
    front.title, front.article_type = _strip_article_type("\n".join(block.text for block in members))
    front.title = front.title or raw_title
    if not front.article_type:
        # Some publishers set the label in its own block above the title.
        above = [block for block in zone if block.bbox[3] <= title_block.bbox[1] + 2]
        for block in sorted(above, key=lambda b: -b.bbox[1])[:2]:
            label = normalize_prose(block.text)
            if ARTICLE_TYPE_RE.match(label):
                front.article_type = label.title()
                block.kind = "front-matter"
                break

    # Everything above the title on the opening page is masthead furniture.
    for block in zone:
        if block.kind == "body" and block.bbox[3] <= title_block.bbox[1] + 1:
            block.kind = "front-matter"

    after = [block for block in zone if block.bbox[1] >= members[-1].bbox[3] - 1 and block not in members]
    author_blocks: list[RawBlock] = []
    affiliation_blocks: list[RawBlock] = []
    byline_parts: list[str] = []
    for block in after:
        text = normalize_prose(block.text)
        # Several publishers set the byline and the affiliations in one block.
        byline, remainder = _split_byline_block(block)
        if byline and not author_blocks and not affiliation_blocks:
            block.kind = "authors" if not remainder else "affiliation"
            byline_parts.append(byline)
            (author_blocks if not remainder else affiliation_blocks).append(block)
            continue
        if _is_affiliation(text):
            block.kind = "affiliation"
            affiliation_blocks.append(block)
            continue
        if not affiliation_blocks and (_looks_like_names(text) or _byline_continuation(text, author_blocks)):
            block.kind = "authors"
            author_blocks.append(block)
            byline_parts.append(text)
            continue
        block.kind = "front-matter"
    front.author_text = normalize_prose(" ".join(byline_parts))
    front.affiliation_text = normalize_prose("\n".join(block.text for block in affiliation_blocks))
    # A degenerate document (a one-page scan, a notice) can have nothing but the
    # block we just called a title. Give it back rather than emptying the body.
    remaining = sum(
        1 for page in pages for block in page.blocks if block.kind in PROSE_KINDS and word_count(block.text) >= 12
    )
    if remaining == 0:
        for block in members:
            block.kind = "body"
    return front


def _split_byline_block(block: RawBlock) -> tuple[str, str]:
    """Split a block that opens with the byline and continues into affiliations.

    Returns (byline, remainder). An empty byline means the block is not of this
    shape and should be classified normally.
    """
    lines = [normalize_prose(line.text) for line in block.lines if line.text.strip()]
    if len(lines) < 2:
        return "", ""
    taken: list[str] = []
    for line in lines:
        if AFFILIATION_RE.search(line) or not _looks_like_names(line):
            break
        taken.append(line)
    if not taken or len(taken) == len(lines):
        return "", ""
    remainder = " ".join(lines[len(taken) :])
    if not _is_affiliation(remainder):
        return "", ""
    return " ".join(taken), remainder


def _byline_continuation(text: str, author_blocks: list[RawBlock]) -> bool:
    """A byline that wraps often ends on a short line with only one name left."""
    if not author_blocks:
        return False
    if word_count(text) > 40 or has_finite_verb(text) or AFFILIATION_RE.search(text):
        return False
    return bool(NAME_TOKEN_RE.findall(text) or INITIAL_TOKEN_RE.findall(text))


def _main_column(page: RawPage) -> int | None:
    columns = page.columns or [(0.0, page.width)]
    if len(columns) <= 1:
        return None
    weights: Counter[int] = Counter()
    for block in page.blocks:
        column = _column_of(block, columns)
        if column >= 0:
            weights[column] += word_count(block.text)
    return weights.most_common(1)[0][0] if weights else None


def _abstract_top(ordered: list[RawBlock], page: RawPage) -> float:
    for block in ordered:
        text = normalize_prose(block.text)
        if re.match(r"^(?:abstract|summary|a\s?b\s?s\s?t\s?r\s?a\s?c\s?t)\b", text, re.I):
            return block.bbox[1]
    for block in ordered:
        text = normalize_prose(block.text)
        if block.kind != "body" or word_count(text) < 60:
            continue
        # Affiliation runs are long but are not the start of the article body.
        if _is_affiliation(text) or not has_finite_verb(text):
            continue
        return block.bbox[1]
    return page.height * 0.75


def _score_title(zone: list[RawBlock], body_size: float, page: RawPage) -> RawBlock | None:
    best: tuple[float, RawBlock] | None = None
    for block in zone:
        text = normalize_prose(block.text)
        words = word_count(text)
        if not 3 <= words <= 60:
            continue
        if re.search(r"https?://|\bdoi\b|\bissn\b|@|\bvol(?:ume)?\.?\s*\d|\bpp\.\s*\d", text, re.I):
            continue
        if AFFILIATION_RE.search(text) or _looks_like_names(text):
            continue
        stripped, _label = _strip_article_type(block.text)
        if word_count(stripped) < 3:
            continue
        relative = block.size / max(1.0, body_size)
        if relative < 1.12:
            continue
        vertical = 1.0 - min(1.0, block.bbox[1] / max(1.0, page.height))
        score = relative * 2.0 + vertical * 1.5
        if 6 <= words <= 30:
            score += 0.8
        if text.isupper():
            score -= 0.6
        if best is None or score > best[0]:
            best = (score, block)
    return best[1] if best else None


def _title_continuations(zone: list[RawBlock], title: RawBlock) -> list[RawBlock]:
    """Publishers split long titles across blocks; rejoin same-size neighbours."""
    following = sorted(
        (block for block in zone if block is not title and block.bbox[1] >= title.bbox[1]),
        key=lambda b: (b.bbox[1], b.bbox[0]),
    )
    members: list[RawBlock] = []
    bottom = title.bbox[3]
    for block in following:
        if abs(block.size - title.size) > max(0.6, title.size * 0.08):
            break
        if block.bbox[1] - bottom > title.size * 1.6:
            break
        text = normalize_prose(block.text)
        if _looks_like_names(text) or AFFILIATION_RE.search(text) or word_count(text) > 40:
            break
        members.append(block)
        bottom = block.bbox[3]
    return members


def mark_abstract(pages: list[RawPage], cover_pages: set[int]) -> None:
    """Tag the abstract body so it can be preserved verbatim downstream."""
    opening = next((page for page in pages if page.number not in cover_pages), None)
    if opening is None:
        return
    started = False
    anchor_size = 0.0
    for page in pages:
        if page.number in cover_pages or page.number < opening.number:
            continue
        if page.number > opening.number + 1:
            break
        for block in order_page(page):
            text = normalize_prose(block.text)
            if not started:
                if re.match(r"^(?:abstract|summary)\b", text, re.I) and word_count(text) <= 400:
                    started = True
                    anchor_size = block.size
                    if word_count(text) > 8:
                        block.kind = "abstract"
                continue
            # Structured abstracts carry sub-headings set smaller than the
            # "Abstract" label itself; a same-size heading ends the abstract.
            if block.kind == "heading":
                if block.size >= anchor_size * 0.95 or re.match(r"^keywords?\b", text, re.I):
                    return
                continue
            if block.kind == "body":
                block.kind = "abstract"
            elif block.kind not in {"decoration", "metadata-field", "caption", "table"}:
                return
