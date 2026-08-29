"""Bibliographic metadata resolution.

Each field is resolved from ranked deterministic sources and recorded with the
page and verbatim excerpt it came from, so the digest can prove where every
frontmatter value originated. Only the DOI ever leaves the machine, and only
when registry repair is explicitly enabled.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from .authors import Author, looks_like_person, parse_byline, roles_from_notes
from .citation import journal_from_running_heads, parse_citation, plausible_journal
from .models import AuthorMetadata, FieldEvidence, PublicationMetadata
from .parsers.pdf import PDFExtraction
from .text import normalize_prose, unique_preserve, word_count

DOI_RE = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+", re.I)
MONTH = (
    r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|"
    r"Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
)
DATE_RE = re.compile(
    rf"(?:\d{{1,2}}\s+{MONTH}\s+\d{{4}}|{MONTH}\s+\d{{1,2}},?\s+\d{{4}}|{MONTH}\s+\d{{4}}|\d{{4}}-\d{{2}}-\d{{2}})",
    re.I,
)
# Publication-date labels in priority order: an online date is the first public
# appearance and is what a citation should carry.
DATE_PRIORITY = [
    ("published online", "online_published"),
    ("first published", "online_published"),
    ("online first", "online_published"),
    ("available online", "online_published"),
    ("published", "published"),
    ("issue date", "issue"),
    ("accepted", "accepted"),
    ("revised", "revised"),
    ("received", "received"),
]
ARTICLE_TYPE_NORMALISATION = [
    (re.compile(r"systematic review|meta-?analysis", re.I), "Systematic Review"),
    (re.compile(r"study protocol|protocol", re.I), "Protocol"),
    (re.compile(r"case report", re.I), "Case Report"),
    (re.compile(r"editorial", re.I), "Editorial"),
    (re.compile(r"commentary|viewpoint|perspective|opinion", re.I), "Commentary"),
    (re.compile(r"correspondence|letter|reply|response", re.I), "Correspondence"),
    (re.compile(r"guideline|consensus|statement|recommendation", re.I), "Guideline"),
    (re.compile(r"\breview\b", re.I), "Review"),
    (re.compile(r"brief|short (?:report|communication)|research letter", re.I), "Brief Report"),
    (re.compile(r"method|resource|software|tool", re.I), "Methods"),
    (re.compile(r"research article|original (?:article|research)|article|paper|research", re.I), "Article"),
]
LICENSE_PATTERNS = [
    (re.compile(r"CC[ -]BY[ -]NC[ -]ND(?:[ -]?4\.0)?", re.I), "CC BY-NC-ND 4.0"),
    (re.compile(r"CC[ -]BY[ -]NC(?:[ -]?4\.0)?", re.I), "CC BY-NC 4.0"),
    (re.compile(r"Creative Commons\s+Attribution\s+4\.0|CC[ -]BY[ -]?4\.0", re.I), "CC BY 4.0"),
    (re.compile(r"Creative Commons\s+Attribution|CC[ -]BY\b", re.I), "CC BY"),
    (re.compile(r"all rights reserved", re.I), "All rights reserved"),
]


def _excerpt(text: str, limit: int = 220) -> str:
    value = normalize_prose(text)
    return value if len(value) <= limit else value[: limit - 1].rstrip() + "…"


def _record(metadata: PublicationMetadata, field: str, value: str, source: str, page: int | None, excerpt: str) -> None:
    if value:
        metadata.evidence[field] = FieldEvidence(
            value=value, source=source, page=page, source_excerpt=_excerpt(excerpt or value)
        )


def _normalise_date(value: str) -> str:
    value = normalize_prose(value)
    match = DATE_RE.search(value)
    if not match:
        return ""
    raw = match.group(0)
    for fmt in ("%d %B %Y", "%d %b %Y", "%B %d, %Y", "%b %d, %Y", "%B %d %Y", "%b %d %Y", "%B %Y", "%b %Y", "%Y-%m-%d"):
        try:
            parsed = datetime.strptime(raw.replace("  ", " "), fmt)
        except ValueError:
            continue
        if fmt in {"%B %Y", "%b %Y"}:
            return f"{parsed.strftime('%B')} {parsed.year}"
        return f"{parsed.strftime('%B')} {parsed.day}, {parsed.year}"
    return raw


def _resolve_title(extraction: PDFExtraction, citation) -> tuple[str, str, int | None, str]:
    front = normalize_prose(extraction.front_matter.title)
    doc_title = normalize_prose(extraction.doc_info.get("title", ""))
    candidates: list[tuple[str, str, int | None, str]] = []
    if front:
        candidates.append((front, "layout title block", extraction.front_matter.opening_page, front))
    if citation.title and word_count(citation.title) >= 4:
        candidates.append((citation.title, "publisher citation string", None, citation.raw))
    if doc_title and word_count(doc_title) >= 4 and not re.search(r"\.(?:docx?|pdf|tex)$|untitled", doc_title, re.I):
        candidates.append((doc_title, "PDF document information", None, doc_title))
    if not candidates:
        return "", "", None, ""
    # A layout title that is clearly a fragment loses to a full citation title.
    best = candidates[0]
    if word_count(best[0]) < 4:
        for candidate in candidates[1:]:
            if word_count(candidate[0]) >= 4:
                return candidate
    return best


AUTHOR_NOTE_LINE_RE = re.compile(
    r"^\s*(?:[¹²³⁴⁵⁶⁷⁸⁹⁰†‡*☯¤§¶#∗]|these authors|current address|e-?mail address|correspondence|"
    r"corresponding author|\*\s*correspondence)",
    re.I,
)


def _author_notes(extraction: PDFExtraction) -> str:
    """Footnote lines that attach roles to byline markers."""
    limit = extraction.front_matter.opening_page + 2
    lines: list[str] = []
    for block in extraction.blocks:
        if block.page > limit:
            break
        for raw in normalize_prose(block.text).splitlines():
            if AUTHOR_NOTE_LINE_RE.match(raw) or block.kind in {"affiliation", "front-matter"}:
                lines.append(raw)
    return "\n".join(lines)


def _corresponding_from_email(notes: str, authors: list[str]) -> list[str]:
    """ "E-mail address: a@b (M.J. Page)" and "Correspondence: Jane Doe" forms."""
    found: list[str] = []
    for match in re.finditer(r"\(([^()]{3,60})\)\s*\.?\s*$|\(([^()]{3,60})\)", notes, re.M):
        label = normalize_prose(match.group(1) or match.group(2) or "")
        surname = label.split()[-1] if label.split() else ""
        if not surname:
            continue
        found.extend(author for author in authors if author.split()[-1].casefold() == surname.casefold())
    for match in re.finditer(r"(?:Correspondence|Corresponding author)\s*[::]\s*([^\n;.]{3,80})", notes, re.I):
        label = normalize_prose(match.group(1))
        found.extend(author for author in authors if author.casefold() in label.casefold())
    return unique_preserve(found)


def _resolve_authors(extraction: PDFExtraction, citation) -> tuple[AuthorMetadata, str, int | None, str, list[Author]]:
    byline = extraction.front_matter.author_text
    parsed, groups, truncated = parse_byline(byline) if byline else ([], [], False)
    people = [author.name for author in parsed]
    source, page, excerpt = "layout byline", extraction.front_matter.opening_page, byline
    if len(people) < 2 and citation.authors:
        people = [name for name in citation.authors if looks_like_person(name) or len(name.split()) >= 2]
        parsed = [Author(name=name) for name in people]
        truncated = citation.truncated_authors
        source, page, excerpt = "publisher citation string", None, citation.raw
    if len(people) < 1:
        raw = normalize_prose(extraction.doc_info.get("author", ""))
        if raw:
            parsed, groups, truncated = parse_byline(raw)
            people = [author.name for author in parsed]
            source, page, excerpt = "PDF document information", None, raw
    authorship = AuthorMetadata(
        authors=people,
        group_authors=groups,
        author_count=len(people) if people else None,
        representation_note=(
            "The source lists additional authors under 'et al.'; the ordered list above is truncated as printed."
            if truncated
            else ""
        ),
    )
    return authorship, source, page, excerpt, parsed


def _resolve_journal(extraction: PDFExtraction, citation) -> tuple[str, str, int | None, str]:
    if citation.journal and plausible_journal(citation.journal):
        return citation.journal, "publisher citation string", None, citation.raw
    heads = list(extraction.running_heads.get("header", [])) + list(extraction.running_heads.get("footer", []))
    from_heads = journal_from_running_heads(heads)
    if from_heads:
        return from_heads, "running head", None, "; ".join(heads[:2])
    subject = normalize_prose(extraction.doc_info.get("subject", ""))
    match = re.match(r"^([A-Z][A-Za-z&'’ .-]{3,70}?)(?:,|\s+\d|$)", subject)
    if match and plausible_journal(match.group(1)):
        return normalize_prose(match.group(1)), "PDF document information", None, subject
    match = re.search(
        r"(?:^|\n)((?:The\s+)?(?:[A-Z][A-Za-z&'’-]+\s+){0,4}Journal of [A-Z][A-Za-z&'’ -]{3,50})",
        extraction.full_text[:6000],
    )
    if match:
        return normalize_prose(match.group(1)), "opening-page masthead", 1, match.group(0)
    return "", "", None, ""


def _resolve_dates(extraction: PDFExtraction) -> dict[str, tuple[str, int | None, str]]:
    found: dict[str, tuple[str, int | None, str]] = {}
    for item in extraction.metadata_fields:
        for label, key in DATE_PRIORITY:
            if item.label != label:
                continue
            value = _normalise_date(item.value)
            if value and key not in found:
                found[key] = (value, item.page, f"{item.label}: {item.value}")
    # Elsevier-style "Received 3 January 2021 Revised 4 March 2021 Accepted ..."
    if not found:
        corpus = extraction.full_text[:6000] + "\n" + extraction.text_of("front-matter", "metadata-field")[:4000]
        for pattern, key in (
            (r"(?:Published online|Available online|First published)\s*:?\s*", "online_published"),
            (r"Accepted\s*:?\s*", "accepted"),
            (r"Revised\s*:?\s*", "revised"),
            (r"Received\s*:?\s*", "received"),
        ):
            match = re.search(pattern + f"({DATE_RE.pattern})", corpus, re.I)
            if match:
                found[key] = (_normalise_date(match.group(1)), 1, _excerpt(match.group(0)))
    return found


def _resolve_doi(extraction: PDFExtraction, citation) -> tuple[str, str, int | None, str]:
    item = extraction.field_value("doi")
    if item:
        match = DOI_RE.search(item.value)
        if match:
            return match.group(0).rstrip(".,);"), "publisher DOI field", item.page, item.value
    for block in extraction.blocks:
        if block.page > 3:
            break
        match = DOI_RE.search(normalize_prose(block.text))
        if match:
            return match.group(0).rstrip(".,);"), "opening-page DOI", block.page, normalize_prose(block.text)
    if citation.doi:
        return citation.doi, "publisher citation string", None, citation.raw
    match = DOI_RE.search(extraction.grounding_text)
    return (match.group(0).rstrip(".,);"), "document text", None, "") if match else ("", "", None, "")


def _resolve_article_type(extraction: PDFExtraction) -> tuple[str, str]:
    label = extraction.front_matter.article_type
    if label:
        for pattern, canonical in ARTICLE_TYPE_NORMALISATION:
            if pattern.search(label):
                return canonical, label
        return label.title(), label
    return "Article", ""


def _resolve_keywords(extraction: PDFExtraction) -> tuple[list[str], int | None, str]:
    item = extraction.field_value("keywords", "key words")
    if not item:
        return [], None, ""
    values = [
        part.strip(" .;,:-") for part in re.split(r"\s*[;|•·]\s*|,\s*(?=[A-Za-z])", item.value) if part.strip(" .;,:-")
    ]
    return unique_preserve(values)[:15], item.page, item.value


def _resolve_abstract(extraction: PDFExtraction) -> tuple[str, int | None]:
    parts = [
        normalize_prose(block.text) for block in extraction.blocks if block.kind == "abstract" and block.text.strip()
    ]
    if not parts:
        return "", None
    page = next((block.page for block in extraction.blocks if block.kind == "abstract"), None)
    return normalize_prose(" ".join(parts)), page


def _license(text: str) -> str:
    for pattern, name in LICENSE_PATTERNS:
        if pattern.search(text):
            return name
    return ""


def _role_names(extraction: PDFExtraction, authors: list[str], labels: list[str]) -> list[str]:
    corpus = "\n".join(
        [extraction.text_of("affiliation", "front-matter", "metadata-field"), extraction.full_text[:8000]]
    )
    for label in labels:
        match = re.search(label, corpus, re.I)
        if not match:
            continue
        tail = corpus[match.end() : match.end() + 500]
        tail = re.split(r"(?:\.\s|\n|\b(?:Received|Accepted|Correspondence|Author contributions)\b)", tail, maxsplit=1)[
            0
        ]
        found = [author for author in authors if re.search(rf"(?<!\w){re.escape(author)}(?!\w)", tail, re.I)]
        if found:
            return found
        surnames = [author for author in authors if re.search(rf"(?<!\w){re.escape(author.split()[-1])}(?!\w)", tail)]
        if surnames:
            return surnames
    return []


def _pick_citation(extraction: PDFExtraction):
    """Prefer the richest citation string available on the opening pages."""
    candidates = [
        item
        for item in extraction.metadata_fields
        if item.label
        in {"citation", "article", "how to cite this article", "cite this article as", "please cite this article as"}
    ]
    parsed = [parse_citation(item.value) for item in candidates]
    scored = [
        (
            bool(candidate.title) * 3 + bool(candidate.journal) * 2 + bool(candidate.year) + bool(candidate.doi),
            -index,
            candidate,
        )
        for index, candidate in enumerate(parsed)
    ]
    if not scored:
        return parse_citation("")
    return max(scored, key=lambda item: (item[0], item[1]))[2]


def extract_publication_metadata(extraction: PDFExtraction, path: Path) -> PublicationMetadata:
    citation = _pick_citation(extraction)
    metadata = PublicationMetadata()

    title, title_source, title_page, title_excerpt = _resolve_title(extraction, citation)
    metadata.title = title
    _record(metadata, "title", title, title_source, title_page, title_excerpt)

    authorship, author_source, author_page, author_excerpt, parsed_authors = _resolve_authors(extraction, citation)
    metadata.authorship = authorship
    _record(metadata, "authors", "; ".join(authorship.authors), author_source, author_page, author_excerpt)

    journal, journal_source, journal_page, journal_excerpt = _resolve_journal(extraction, citation)
    metadata.journal = journal
    _record(metadata, "journal", journal, journal_source, journal_page, journal_excerpt)

    doi, doi_source, doi_page, doi_excerpt = _resolve_doi(extraction, citation)
    metadata.doi = doi
    _record(metadata, "doi", doi, doi_source, doi_page, doi_excerpt)

    dates = _resolve_dates(extraction)
    metadata.online_date = dates.get("online_published", ("", None, ""))[0]
    metadata.issue_date = dates.get("issue", ("", None, ""))[0]
    metadata.received_date = dates.get("received", ("", None, ""))[0]
    metadata.accepted_date = dates.get("accepted", ("", None, ""))[0]
    metadata.revised_date = dates.get("revised", ("", None, ""))[0]
    for key, label in (
        ("online_published", "online_published"),
        ("published", "published"),
        ("issue", "issue"),
        ("accepted", "accepted"),
    ):
        if key in dates:
            value, page, excerpt = dates[key]
            metadata.publication_date = value
            metadata.publication_date_label = label
            _record(metadata, "publication_date", value, f"publisher '{label}' field", page, excerpt)
            break
    if not metadata.online_date and metadata.publication_date_label in {"published", "online_published"}:
        metadata.online_date = metadata.publication_date

    metadata.volume = citation.volume
    metadata.issue = citation.issue
    metadata.pages_or_article = citation.pages or citation.article_number
    metadata.article_number = citation.article_number
    metadata.issn = citation.issn

    year = None
    for value in (metadata.publication_date, metadata.online_date, metadata.issue_date):
        match = re.search(r"\b(?:19|20)\d{2}\b", value or "")
        if match:
            year = int(match.group(0))
            break
    if year is None and citation.year:
        year = citation.year
    if year is None:
        copyright_field = extraction.field_value("copyright")
        corpus = (copyright_field.value if copyright_field else "") + " " + extraction.full_text[:6000]
        match = re.search(r"©\s*(?:The Author\(s\)\s*)?((?:19|20)\d{2})", corpus)
        if match:
            year = int(match.group(1))
    metadata.year = year
    if year:
        _record(
            metadata,
            "year",
            str(year),
            metadata.evidence.get("publication_date", FieldEvidence("", "derived")).source or "publication year",
            None,
            metadata.publication_date or str(year),
        )

    article_type, type_excerpt = _resolve_article_type(extraction)
    metadata.article_type = article_type
    _record(
        metadata,
        "article_type",
        article_type,
        "layout article-type label",
        extraction.front_matter.opening_page,
        type_excerpt,
    )

    keywords, keyword_page, keyword_excerpt = _resolve_keywords(extraction)
    metadata.author_keywords = keywords
    _record(metadata, "author_keywords", "; ".join(keywords), "publisher keywords field", keyword_page, keyword_excerpt)

    abstract, abstract_page = _resolve_abstract(extraction)
    metadata.abstract = abstract
    _record(metadata, "abstract", abstract[:80], "layout abstract block", abstract_page, abstract)

    license_corpus = "\n".join(
        [extraction.text_of("metadata-field", "banner", "front-matter"), extraction.full_text[:6000]]
    )
    metadata.license = _license(license_corpus)
    notes = _author_notes(extraction)
    marker_roles = roles_from_notes(parsed_authors, notes)
    metadata.authorship.equal_contributors = unique_preserve(
        marker_roles["equal"]
        or _role_names(extraction, authorship.authors, [r"contributed\s+equally", r"joint first authors?"])
    )
    metadata.authorship.joint_supervisors = unique_preserve(
        marker_roles["supervisor"]
        or _role_names(extraction, authorship.authors, [r"jointly\s+supervised", r"joint senior authors?"])
    )
    metadata.authorship.corresponding = unique_preserve(
        marker_roles["corresponding"]
        or _corresponding_from_email(notes, authorship.authors)
        or _role_names(
            extraction,
            authorship.authors,
            [
                r"Corresponding author\(s\)?\s*:?",
                r"Correspondence and requests for materials should be addressed to",
                r"\*\s*Correspondence\s*:?",
                r"E-?mail address:",
            ],
        )
    )
    metadata.metadata_sources = ["publisher PDF"]
    return metadata


def _crossref_date(message: dict, *keys: str) -> tuple[str, int | None]:
    for key in keys:
        parts = ((message.get(key) or {}).get("date-parts") or [[]])[0]
        if not parts:
            continue
        year = int(parts[0])
        if len(parts) >= 3:
            parsed = datetime(year, int(parts[1]), int(parts[2]))
            return f"{parsed.strftime('%B')} {parsed.day}, {year}", year
        if len(parts) == 2:
            return datetime(year, int(parts[1]), 1).strftime("%B %Y"), year
        return str(year), year
    return "", None


def enrich_from_doi_registry(metadata: PublicationMetadata, timeout: float = 8.0) -> bool:
    """Fill bibliographic fields from the DOI registry; only the DOI leaves the machine."""
    if not metadata.doi:
        return False
    url = "https://api.crossref.org/works/" + quote(metadata.doi, safe="")
    request = Request(
        url,
        headers={"User-Agent": "paper-digest-deterministic/2.0 (+https://github.com/firecrawl/firecrawl)"},
    )
    try:
        with urlopen(request, timeout=timeout) as response:  # noqa: S310 - fixed HTTPS registry endpoint.
            payload = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, OSError):
        return False
    message = payload.get("message") if isinstance(payload, dict) else None
    if not isinstance(message, dict) or str(message.get("DOI", "")).casefold() != metadata.doi.casefold():
        return False

    titles = message.get("title") or []
    if titles:
        registry_title = normalize_prose(str(titles[0]))
        if registry_title:
            metadata.title = registry_title
            _record(metadata, "title", registry_title, "Crossref DOI registry", None, registry_title)
    authors: list[str] = []
    for item in message.get("author") or []:
        if not isinstance(item, dict):
            continue
        name = normalize_prose(" ".join(str(item.get(key, "")) for key in ("given", "family")).strip())
        if name:
            authors.append(name)
    if authors:
        metadata.authorship.authors = unique_preserve(authors)
        metadata.authorship.author_count = len(metadata.authorship.authors)
        metadata.authorship.representation_note = ""
        _record(metadata, "authors", "; ".join(authors), "Crossref DOI registry", None, "; ".join(authors))

    containers = message.get("container-title") or []
    if containers:
        metadata.journal = normalize_prose(str(containers[0]))
        _record(metadata, "journal", metadata.journal, "Crossref DOI registry", None, metadata.journal)
    metadata.volume = normalize_prose(str(message.get("volume") or metadata.volume))
    metadata.issue = normalize_prose(str(message.get("issue") or metadata.issue))
    metadata.pages_or_article = normalize_prose(
        str(message.get("page") or message.get("article-number") or metadata.pages_or_article)
    )
    online, online_year = _crossref_date(message, "published-online", "published")
    issue_date, issue_year = _crossref_date(message, "published-print", "issued")
    metadata.online_date = online or metadata.online_date
    metadata.issue_date = issue_date or metadata.issue_date
    if online:
        metadata.publication_date, metadata.publication_date_label = online, "online_published"
    elif issue_date and not metadata.publication_date:
        metadata.publication_date, metadata.publication_date_label = issue_date, "issue"
    metadata.year = online_year or issue_year or metadata.year
    registry_type = str(message.get("type") or "").replace("-", " ").strip()
    if registry_type:
        for pattern, canonical in ARTICLE_TYPE_NORMALISATION:
            if pattern.search(registry_type):
                metadata.article_type = canonical
                break
        else:
            metadata.article_type = registry_type.title()
    metadata.metadata_sources = unique_preserve(metadata.metadata_sources + ["Crossref DOI registry"])
    return True
