from __future__ import annotations

import re

from .models import Paragraph, Section, TextBlock
from .text import normalize_prose, word_count

HEADING_ALIASES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"abstract|summary", re.I), "Abstract"),
    (re.compile(r"background|introduction|rationale", re.I), "Introduction"),
    (re.compile(r"objectives?|aims?|purpose", re.I), "Objectives"),
    (
        re.compile(
            r"methods?|materials(?: and methods)?|patients? and methods|participants?|"
            r"study design|experimental procedures?|statistical analysis|online methods",
            re.I,
        ),
        "Methods",
    ),
    (re.compile(r"results?|findings?|outcomes?", re.I), "Results"),
    (re.compile(r"discussion", re.I), "Discussion"),
    (re.compile(r"conclusions?|interpretation", re.I), "Conclusion"),
    (re.compile(r"limitations?|strengths and limitations", re.I), "Limitations"),
    (re.compile(r"data availability|availability of data", re.I), "Data availability"),
    (re.compile(r"code availability|availability of code", re.I), "Code availability"),
    (re.compile(r"references?|bibliography", re.I), "References"),
    (re.compile(r"acknowledgements?|funding", re.I), "Acknowledgements"),
    (re.compile(r"author contributions?|contributors?", re.I), "Author contributions"),
    (re.compile(r"competing interests?|conflicts? of interest", re.I), "Competing interests"),
]

HEADING_PREFIX_RE = re.compile(r"^(?:\d+(?:\.\d+)*[.)]?\s+)?([A-Za-z][A-Za-z &/-]{1,55}?)(?:\s*[:—.-]\s*|\s{2,})(.+)$")
INLINE_HEADING_RE = re.compile(
    r"^(Abstract|Summary|Background|Introduction|Rationale|Objectives?|Aims?|Purpose|Methods?|"
    r"Materials and Methods|Results?|Findings?|Discussion|Conclusions?|Interpretation|Limitations?)"
    r"\s*[:—.-]?\s+(.+)$",
    re.I,
)


def _canonical_heading(text: str) -> str | None:
    value = normalize_prose(text).strip(" :.–—")
    value = re.sub(r"^\d+(?:\.\d+)*[.)]?\s+", "", value)
    for pattern, canonical in HEADING_ALIASES:
        if pattern.fullmatch(value):
            return canonical
    return None


def _split_heading_prefix(text: str) -> tuple[str | None, str]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return None, ""
    first = normalize_prose(lines[0])
    direct = _canonical_heading(first)
    if direct:
        return direct, normalize_prose("\n".join(lines[1:]))
    inline = INLINE_HEADING_RE.match(first)
    if inline:
        separator = first[inline.end(1) : inline.start(2)]
        heading = _canonical_heading(inline.group(1))
        explicit_separator = any(mark in separator for mark in ":—.-")
        if heading and (explicit_separator or inline.group(2)[:1].isupper()):
            remainder = " ".join([inline.group(2), *lines[1:]])
            return heading, normalize_prose(remainder)
    match = HEADING_PREFIX_RE.match(first)
    if match:
        heading = _canonical_heading(match.group(1))
        if heading:
            remainder = " ".join([match.group(2), *lines[1:]])
            return heading, normalize_prose(remainder)
    # Structured abstracts commonly use a single space after a short label.
    for pattern, canonical in HEADING_ALIASES:
        prefix = re.match(r"^([A-Za-z][A-Za-z &/-]{1,30})\s+(.+)$", first)
        if prefix and pattern.fullmatch(prefix.group(1)) and prefix.group(2)[:1].isupper():
            remainder = " ".join([prefix.group(2), *lines[1:]])
            return canonical, normalize_prose(remainder)
    return None, normalize_prose(text)


def segment_sections(blocks: list[TextBlock], source_file: str) -> dict[str, Section]:
    sections: dict[str, Section] = {"Front matter": Section("Front matter")}
    current = "Front matter"
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
                )
            )
        buffer = []

    for block in blocks:
        if block.kind in {"header", "footer"}:
            continue
        heading, remainder = _split_heading_prefix(block.text)
        if heading:
            flush()
            current = heading
            sections.setdefault(current, Section(current))
            page_start = block.page
            page_end = block.page
            if remainder:
                buffer.append(remainder)
            continue
        text = remainder.strip()
        if not text:
            continue
        if not buffer:
            page_start = block.page
        page_end = block.page
        if buffer and word_count(" ".join(buffer)) >= 150:
            flush()
            page_start = block.page
        buffer.append(text)
    flush()
    return sections
