from __future__ import annotations

import math
import re
from collections.abc import Iterable
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from ..models import Paragraph, ParsedBundle, WorkbookSheet
from ..text import normalize_prose, oxford_join, unique_preserve


def paragraphs(bundle: ParsedBundle, names: Iterable[str] | None = None) -> list[Paragraph]:
    if names is None:
        return [paragraph for section in bundle.sections.values() for paragraph in section.paragraphs]
    wanted = {name.casefold() for name in names}
    return [
        paragraph
        for key, section in bundle.sections.items()
        if key.casefold() in wanted
        for paragraph in section.paragraphs
    ]


def find_paragraphs(
    bundle: ParsedBundle, patterns: Iterable[str], section_names: Iterable[str] | None = None
) -> list[Paragraph]:
    candidates = paragraphs(bundle, section_names)
    output: list[Paragraph] = []
    for paragraph in candidates:
        if any(re.search(pattern, paragraph.text, re.I | re.S) for pattern in patterns):
            output.append(paragraph)
    return output


def first_matching(
    bundle: ParsedBundle, patterns: Iterable[str], section_names: Iterable[str] | None = None
) -> Paragraph | None:
    found = find_paragraphs(bundle, patterns, section_names)
    return found[0] if found else None


def find_sheet(bundle: ParsedBundle, *needles: str) -> WorkbookSheet | None:
    wanted = [needle.casefold() for needle in needles if needle]
    for sheet in bundle.workbooks:
        haystack = f"{sheet.sheet_name} {sheet.title}".casefold()
        if all(needle in haystack for needle in wanted):
            return sheet
    if len(wanted) > 1:
        for sheet in bundle.workbooks:
            haystack = f"{sheet.sheet_name} {sheet.title}".casefold()
            if any(needle in haystack for needle in wanted):
                return sheet
    return None


def sheet_rows_by_first_cell(sheet: WorkbookSheet | None, values: Iterable[str]) -> dict[str, list[Any]]:
    if sheet is None:
        return {}
    wanted = {str(value).casefold(): str(value) for value in values}
    output: dict[str, list[Any]] = {}
    for row in sheet.rows:
        if not row or row[0] is None:
            continue
        key = str(row[0]).strip().casefold()
        if key in wanted:
            output[wanted[key]] = row
    return output


def numeric_head(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value) if math.isfinite(float(value)) else None
    if value is None:
        return None
    match = re.search(r"[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?", str(value).replace(",", ""))
    return float(match.group(0)) if match else None


def scientific(value: Any, digits: int = 2) -> str:
    number = numeric_head(value)
    if number is None:
        return "NA"
    if number == 0:
        return "0"
    if abs(number) < 0.001 or abs(number) >= 10000:
        exponent = int(math.floor(math.log10(abs(number))))
        mantissa = number / (10**exponent)
        return f"{mantissa:.{digits}f} × 10^{exponent}"
    return f"{number:.{digits + 1}g}"


def pct(value: Any, digits: int = 2) -> str:
    number = numeric_head(value)
    if number is None:
        return "NA"
    quantum = Decimal("1") if digits == 0 else Decimal("1").scaleb(-digits)
    rounded = (Decimal(str(number)) * Decimal("100")).quantize(quantum, rounding=ROUND_HALF_UP)
    return f"{rounded:.{digits}f}%"


def author_notes(bundle: ParsedBundle) -> str:
    authorship = bundle.metadata.authorship
    notes: list[str] = []
    if authorship.equal_contributors:
        notes.append(oxford_join(authorship.equal_contributors) + " contributed equally")
    joint_key = {name.casefold() for name in authorship.joint_supervisors}
    corr_key = {name.casefold() for name in authorship.corresponding}
    if authorship.joint_supervisors and joint_key == corr_key:
        verb = "is the corresponding author" if len(authorship.joint_supervisors) == 1 else "are corresponding authors"
        notes.append(oxford_join(authorship.joint_supervisors) + f" jointly supervised the study and {verb}")
    else:
        if authorship.joint_supervisors:
            notes.append(oxford_join(authorship.joint_supervisors) + " jointly supervised the study")
        if authorship.corresponding:
            role = "is the corresponding author" if len(authorship.corresponding) == 1 else "are corresponding authors"
            notes.append(oxford_join(authorship.corresponding) + " " + role)
    if authorship.group_authors:
        notes.append("group authorship: " + oxford_join(authorship.group_authors))
    if authorship.representation_note:
        notes.append(authorship.representation_note)
    return "; ".join(unique_preserve(notes)) or "No special authorship roles were stated in the supplied paper."


def classification_block(bundle: ParsedBundle) -> str:
    metadata = bundle.metadata
    journal_name = metadata.journal or "Not resolved from the supplied PDF"
    journal = f"*{journal_name}*"
    if metadata.volume:
        journal += f", volume {metadata.volume}"
    if metadata.pages_or_article:
        journal += f", pages {metadata.pages_or_article}"
    dates: list[str] = []
    if metadata.online_date:
        dates.append(f"Published online {metadata.online_date}")
    if metadata.issue_date:
        dates.append(f"{metadata.issue_date} issue")
    publication_date = "; ".join(dates) or str(metadata.year or "Not resolved")
    fields = "; ".join(metadata.research_fields)
    keywords = "; ".join(metadata.index_keywords)
    lines = [
        "### Classification metadata",
        "",
        f"- **Journal:** {journal}",
        f"- **Publication date:** {publication_date}",
        f"- **Article type:** {metadata.article_type}",
        f"- **Author count:** {metadata.authorship.author_count or len(metadata.authorship.authors)}",
        f"- **Author notes:** {author_notes(bundle)}",
        f"- **Research fields (editorial):** {fields}",
    ]
    if metadata.author_keywords:
        lines.append(f"- **Author keywords:** {'; '.join(metadata.author_keywords)}")
    lines.append(f"- **Index keywords (editorial):** {keywords}")
    return "\n".join(lines)


def all_text(bundle: ParsedBundle) -> str:
    supplement = "\n".join(bundle.supplements_text.values())
    workbook = "\n".join(
        "\n".join(" | ".join(str(value) for value in row if value is not None) for row in sheet.rows)
        for sheet in bundle.workbooks
    )
    return "\n".join([bundle.full_text, supplement, workbook])


def regex_value(text: str, patterns: Iterable[str], group: int = 1) -> str | None:
    for pattern in patterns:
        match = re.search(pattern, text, re.I | re.S)
        if match:
            return normalize_prose(match.group(group))
    return None
