from __future__ import annotations

import re

from .models import Paragraph, Section, TextBlock
from .parsers.layout import PROSE_KINDS
from .text import normalize_prose, word_count

HEADING_ALIASES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"abstract|summary|plain language summary", re.I), "Abstract"),
    (re.compile(r"background|introduction|rationale", re.I), "Introduction"),
    (re.compile(r"objectives?|aims?|purpose|research questions?", re.I), "Objectives"),
    (
        re.compile(
            r"methods?|materials(?: and methods)?|methods? and materials|patients? and methods|participants?|"
            r"study design|study population|experimental procedures?|statistical analys[ei]s|online methods|"
            r"data collection|data analys[ei]s|search strategy|eligibility criteria|procedures?|"
            r"development(?: of .{1,60})?|guideline development|consensus (?:process|procedure)|"
            r"development and (?:validation|consensus)",
            re.I,
        ),
        "Methods",
    ),
    (
        re.compile(
            r"results?|findings?|outcomes?|recommendations?|checklist items?|"
            r"the .{1,50} (?:statement|checklist|guideline)|how to use .{1,50}",
            re.I,
        ),
        "Results",
    ),
    (re.compile(r"discussion|comment", re.I), "Discussion"),
    (re.compile(r"conclusions?|interpretation", re.I), "Conclusion"),
    (re.compile(r"limitations?|strengths and limitations", re.I), "Limitations"),
    (re.compile(r"data availability|availability of data", re.I), "Data availability"),
    (re.compile(r"code availability|availability of code|software availability", re.I), "Code availability"),
    (re.compile(r"references?|bibliography", re.I), "References"),
    (re.compile(r"acknowledge?ments?|funding|financial support", re.I), "Acknowledgements"),
    (re.compile(r"author contributions?|contributors?", re.I), "Author contributions"),
    (re.compile(r"competing interests?|conflicts? of interest|declaration of interests?", re.I), "Competing interests"),
    (re.compile(r"ethics(?: statement| approval| and consent)?|consent", re.I), "Ethics"),
    (re.compile(r"supporting information|supplementary (?:material|information|data)", re.I), "Supplementary"),
]
# Sections that never contribute scientific claims to a digest.
NON_SCIENTIFIC = frozenset({"References", "Acknowledgements", "Author contributions", "Competing interests", "Ethics"})

INLINE_HEADING_RE = re.compile(
    r"^(Abstract|Summary|Background|Introduction|Rationale|Objectives?|Aims?|Purpose|Methods?|"
    r"Materials and Methods|Results?|Findings?|Discussion|Conclusions?|Interpretation|Limitations?)"
    r"\s*[:.]?\s+(?![a-z])(.+)$",
    re.I,
)
NUMBERED_PREFIX_RE = re.compile(r"^\s*(?:\d+(?:\.\d+)*[.)]?|[IVXivx]+\.)\s+")


def _canonical_heading(text: str) -> str | None:
    value = NUMBERED_PREFIX_RE.sub("", normalize_prose(text).strip(" :.–—"))
    for pattern, canonical in HEADING_ALIASES:
        if pattern.fullmatch(value):
            return canonical
    return None


def _split_inline_heading(text: str) -> tuple[str | None, str]:
    """Structured abstracts fuse the label into the first sentence."""
    first = normalize_prose(text)
    direct = _canonical_heading(first)
    if direct:
        return direct, ""
    inline = INLINE_HEADING_RE.match(first)
    if inline:
        separator = first[inline.end(1) : inline.start(2)]
        heading = _canonical_heading(inline.group(1))
        if heading and (":" in separator or inline.group(2)[:1].isupper()):
            return heading, normalize_prose(inline.group(2))
    return None, first


def segment_sections(blocks: list[TextBlock], source_file: str) -> dict[str, Section]:
    sections: dict[str, Section] = {"Front matter": Section("Front matter")}
    current = "Front matter"
    subsection: str | None = None
    buffer: list[str] = []
    page_start = 1
    page_end = 1

    def flush() -> None:
        nonlocal buffer
        text = normalize_prose("\n".join(buffer))
        if word_count(text) >= 5:
            sections.setdefault(current, Section(current)).paragraphs.append(
                Paragraph(
                    text=text,
                    section=current,
                    page_start=page_start,
                    page_end=page_end,
                    source_file=source_file,
                    subsection=subsection,
                )
            )
        buffer = []

    for block in blocks:
        if block.kind not in PROSE_KINDS:
            continue
        if block.kind == "heading":
            flush()
            canonical = _canonical_heading(block.text)
            if canonical:
                current = canonical
                subsection = None
            else:
                subsection = normalize_prose(block.text)
            page_start = page_end = block.page
            continue
        if block.kind == "abstract":
            heading, remainder = _split_inline_heading(block.text)
            if current != "Abstract":
                flush()
                current = "Abstract"
                subsection = None
                page_start = block.page
            if heading and heading != "Abstract":
                subsection = heading
            text = remainder or normalize_prose(block.text)
            if text:
                page_end = block.page
                buffer.append(text)
            continue
        heading, remainder = _split_inline_heading(block.text)
        if heading:
            flush()
            current = heading
            subsection = None
            page_start = page_end = block.page
            if remainder:
                buffer.append(remainder)
            continue
        if not remainder:
            continue
        if not buffer:
            page_start = block.page
        page_end = block.page
        if buffer and word_count(" ".join(buffer)) >= 150:
            flush()
            page_start = block.page
        buffer.append(remainder)
    flush()
    return sections
