"""Deterministic parsing of publisher citation strings.

Most publishers stamp a self-citation somewhere on the opening page or in the
running foot: PLOS "Citation: ...", Elsevier "Please cite this article as: ...",
repository cover sheets "Article: ...". Each one contains the authoritative
title, journal, year and often the volume/pages. Parsing it is far more
reliable than guessing those fields from page geometry.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .text import normalize_prose, unique_preserve

YEAR_RE = re.compile(r"\((19|20)\d{2}[a-z]?\)")
BARE_YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")
DOI_RE = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+", re.I)
VOLUME_ISSUE_RE = re.compile(r"\b(\d{1,4})\s*\((\d{1,4}(?:[-–]\d{1,4})?)\)")
PAGES_RE = re.compile(r"\bpp?\.\s*(\d+\s*[-–]\s*\d+)|\b(\d+)\s*[-–]\s*(\d+)\s*\.?\s*$")
ARTICLE_NUMBER_RE = re.compile(r"\b(e\d{4,}|[a-z]{1,4}\d{5,})\b", re.I)
ISSN_RE = re.compile(r"\bISSN:?\s*([\dX-]{8,9})", re.I)
JOURNAL_HINT_RE = re.compile(
    r"\b(journal|review|letters?|reports?|proceedings|annals|archives|bulletin|transactions|"
    r"medicine|medicine|lancet|bmj|jama|nature|science|plos|cell|neuron|psychiatry|epidemiology|"
    r"genetics|genomics|research|studies|quarterly|advances|frontiers|open|communications)\b",
    re.I,
)


# Publisher boilerplate that shares a line with the citation but is not part of
# the journal name.
COPYRIGHT_RE = re.compile(
    r"©|\(c\)|\bthe authors?\b|\bjournal compilation\b|\ball rights reserved\b|"
    r"\bpublish(?:ed|ing)\b|\breprints?\b|\blicen[cs]e[ds]?\b",
    re.I,
)
PUBLISHER_SUFFIX_RE = re.compile(
    r"\b(?:Ltd|Inc|LLC|B\.?V|GmbH|Press|Publishing|Publishers?|Media|Group|Wiley|Elsevier|Springer|"
    r"Blackwell|Sage|Taylor|Francis)\b\.?",
    re.I,
)


def plausible_journal(name: str) -> bool:
    """A journal title, not a copyright line or a publisher imprint."""
    value = normalize_prose(name).strip(" .,;:")
    words = value.split()
    if not 1 <= len(words) <= 9 or len(value) < 3:
        return False
    if COPYRIGHT_RE.search(value) or PUBLISHER_SUFFIX_RE.search(value):
        return False
    return any(character.isalpha() for character in value)


@dataclass(slots=True)
class ParsedCitation:
    raw: str = ""
    authors: list[str] = field(default_factory=list)
    year: int | None = None
    title: str = ""
    journal: str = ""
    volume: str = ""
    issue: str = ""
    pages: str = ""
    article_number: str = ""
    doi: str = ""
    issn: str = ""
    truncated_authors: bool = False


def _clean_segment(value: str) -> str:
    value = normalize_prose(value)
    return value.strip(" ,.;:–-")


def _split_author_names(chunk: str) -> tuple[list[str], bool]:
    """Split the pre-year part of a citation into ordered author names."""
    truncated = bool(re.search(r"\bet\s+al\b", chunk, re.I))
    chunk = re.sub(r"\bet\s+al\.?", "", chunk, flags=re.I)
    chunk = re.sub(r"\s*&\s*|\s+\band\b\s+", ", ", chunk)
    parts = [_clean_segment(part) for part in chunk.split(",")]
    parts = [part for part in parts if part]
    if not parts:
        return [], truncated
    # "Surname, Given" style alternates a multi-word given-name chunk after a
    # bare surname; "Given Surname" style does not.
    single = sum(1 for part in parts if len(part.split()) == 1)
    names: list[str] = []
    if single >= max(2, len(parts) * 0.4) and len(parts) >= 2:
        index = 0
        while index < len(parts):
            surname = parts[index]
            given = parts[index + 1] if index + 1 < len(parts) else ""
            if given and len(surname.split()) == 1 and len(given.split()) <= 3:
                names.append(f"{given} {surname}")
                index += 2
            else:
                names.append(surname)
                index += 1
    else:
        names = parts
    cleaned = [name for name in names if _plausible_name(name)]
    return unique_preserve(cleaned), truncated


def _plausible_name(value: str) -> bool:
    tokens = re.findall(r"[A-Za-zÀ-ÖØ-öø-ÿ'’.-]+", value)
    if not 1 <= len(tokens) <= 6:
        return False
    if re.search(r"\d|@|https?://", value):
        return False
    return sum(token[:1].isupper() for token in tokens) >= 1 and len(value) >= 3


def parse_citation(raw: str) -> ParsedCitation:
    """Parse "authors (year) title. journal volume(issue): pages" and variants."""
    text = normalize_prose(raw)
    parsed = ParsedCitation(raw=text)
    if not text:
        return parsed
    # Strip a leading copyright clause so it cannot be read as the byline.
    copyright_clause = re.match(r"^.{0,120}?(?:©|\(c\))\s*(?:19|20)\d{2}[^.]{0,90}\.\s*", text, re.I)
    if copyright_clause:
        text = text[copyright_clause.end() :]
        parsed.raw = text
    doi = DOI_RE.search(text)
    if doi:
        parsed.doi = doi.group(0).rstrip(".,);")
    issn = ISSN_RE.search(text)
    if issn:
        parsed.issn = issn.group(1)

    match = YEAR_RE.search(text)
    if match:
        parsed.year = int(match.group(0)[1:5])
        head, tail = text[: match.start()], text[match.end() :]
    else:
        # Elsevier style: "M.J. Page et al., Title, Journal, https://doi.org/..."
        # There is no parenthesised year here, and a bare year in the text is
        # far more likely to belong to the title, so no year is inferred.
        head, tail = "", text
        author_end = re.search(r"\bet\s+al\.?,", text, re.I)
        if author_end:
            head, tail = text[: author_end.end()], text[author_end.end() :]
            parsed.authors, parsed.truncated_authors = _split_author_names(head)
            return _finish_comma_style(parsed, tail)
    parsed.authors, parsed.truncated_authors = _split_author_names(head)

    tail = re.sub(r"https?://\S+", " ", tail)
    tail = DOI_RE.sub(" ", tail)
    tail = ISSN_RE.sub(" ", tail)
    segments = [_clean_segment(part) for part in re.split(r"(?<!\bet al)\.\s+|\.\s*$|,\s*(?=[A-Z][a-z]+ [A-Z])", tail)]
    segments = [segment for segment in segments if segment]
    if not segments:
        return parsed

    volume_issue = VOLUME_ISSUE_RE.search(tail)
    if volume_issue:
        parsed.volume, parsed.issue = volume_issue.group(1), volume_issue.group(2)
    article = ARTICLE_NUMBER_RE.search(tail)
    if article:
        parsed.article_number = article.group(1)
    pages = PAGES_RE.search(tail)
    if pages:
        parsed.pages = re.sub(r"\s*[-–]\s*", "-", pages.group(1) or f"{pages.group(2)}-{pages.group(3)}")

    # The title is the first substantial segment; the journal is the segment
    # that carries the volume marker, or the last named segment before it.
    parsed.title = _clean_segment(re.sub(r"\s*\d+\s*\(\d+\)\s*:?.*$", "", segments[0]))
    journal = ""
    for segment in segments[1:]:
        stripped = _clean_segment(re.sub(r"\d.*$", "", segment))
        if not stripped or len(stripped.split()) > 12:
            continue
        if not plausible_journal(stripped):
            continue
        if JOURNAL_HINT_RE.search(stripped) or stripped.istitle() or stripped.isupper():
            journal = stripped
            break
    if not journal and len(segments) > 1:
        candidate = _clean_segment(re.sub(r"\d.*$", "", segments[1]))
        journal = candidate if plausible_journal(candidate) else ""
    if not journal:
        journal = _journal_before_locator(tail)
        if journal and parsed.title.startswith(journal):
            # "Histopathology 51, 105-110 Prognostic indicators of …" carries the
            # locator inside what looked like the title.
            parsed.title = _clean_segment(re.sub(rf"^{re.escape(journal)}\s+[\d,:()\s–-]+", "", parsed.title))
    parsed.journal = journal
    if parsed.title and len(parsed.title.split()) < 3 and len(segments) > 1:
        parsed.title = _clean_segment(segments[1])
    return parsed


# A journal name is the run of capitalised words immediately before the volume:
# "… PLoS ONE 14(7): e0219252", "… Histopathology 51, 105-110".
JOURNAL_BEFORE_LOCATOR_RE = re.compile(
    r"(?P<lead>(?:[A-Z][A-Za-z&'’.-]*\s+){0,7}[A-Z][A-Za-z&'’.-]*)\s+\d{1,4}\s*[,:(]"
)


def _journal_before_locator(tail: str) -> str:
    for match in JOURNAL_BEFORE_LOCATOR_RE.finditer(tail):
        candidate = _clean_segment(match.group("lead"))
        if plausible_journal(candidate) and not candidate.isupper():
            return candidate
    return ""


def _finish_comma_style(parsed: ParsedCitation, tail: str) -> ParsedCitation:
    """Comma-delimited "Title, Journal, doi" citations carry no period breaks."""
    tail = ISSN_RE.sub(" ", DOI_RE.sub(" ", re.sub(r"https?://\S+", " ", tail)))
    segments = [_clean_segment(part) for part in tail.split(",")]
    segments = [segment for segment in segments if segment]
    if not segments:
        return parsed
    journal_index = None
    for index in range(len(segments) - 1, 0, -1):
        if JOURNAL_HINT_RE.search(segments[index]) and len(segments[index].split()) <= 9:
            journal_index = index
            break
    if journal_index is None:
        journal_index = len(segments) - 1 if len(segments) > 1 else None
    if journal_index and plausible_journal(segments[journal_index]):
        parsed.journal = segments[journal_index]
        parsed.title = _clean_segment(", ".join(segments[:journal_index]))
    else:
        parsed.title = _clean_segment(", ".join(segments))
    return parsed


RUNNING_SPLIT_RE = re.compile(r"\s*[|/·•]\s*")


def journal_from_running_heads(lines: list[str]) -> str:
    """Recover the journal name from a running head or foot.

    Running heads are formatted as "Authors / Journal vol (year) pages" or
    "JOURNAL | https://doi.org/... date page". Split on the separator and keep
    the part that reads like a journal title.
    """
    best = ""
    for line in lines:
        value = normalize_prose(line)
        if not value:
            continue
        for part in RUNNING_SPLIT_RE.split(value):
            candidate = re.sub(r"https?://\S+", " ", part)
            candidate = DOI_RE.sub(" ", candidate)
            candidate = re.sub(
                r"\b(?:19|20)\d{2}\b|\bxxx\b|\(.*?\)|\bvol(?:ume)?\.?\s*\d+|\bpp?\.\s*[\d-]+",
                " ",
                candidate,
                flags=re.I,
            )
            candidate = re.sub(r"[\d,;:]+", " ", candidate)
            candidate = _clean_segment(candidate)
            words = candidate.split()
            if not 1 <= len(words) <= 9:
                continue
            if re.search(r"\bet al\b|\barticle in press\b|\bdownloaded\b|\bpage\b$", candidate, re.I):
                continue
            letters = sum(character.isalpha() for character in candidate)
            if letters < 4:
                continue
            capitalised = sum(1 for word in words if word[:1].isupper())
            if capitalised / len(words) < 0.6:
                continue
            if not (JOURNAL_HINT_RE.search(candidate) or candidate.isupper() or len(words) >= 2):
                continue
            if not plausible_journal(candidate):
                continue
            if len(candidate) > len(best):
                best = candidate
    return best
