from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from .models import AuthorMetadata, PublicationMetadata, TextBlock
from .parsers.pdf import PDFExtraction
from .text import normalize_prose, unique_preserve

DOI_RE = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+", re.I)
MONTH = r"(?:January|February|March|April|May|June|July|August|September|October|November|December)"
DATE_RE = re.compile(rf"(?:\d{{1,2}}\s+)?{MONTH}\s+\d{{4}}", re.I)
NAME_TOKEN = r"[A-ZÀ-ÖØ-Þ][A-Za-zÀ-ÖØ-öø-ÿ'’.-]*"


def _title(blocks: list[TextBlock]) -> str:
    page1 = [b for b in blocks if b.page == 1 and b.kind == "title"]
    if not page1:
        page1 = sorted([b for b in blocks if b.page == 1], key=lambda b: b.font_size or 0, reverse=True)[:5]
    lines: list[str] = []
    for block in sorted(page1, key=lambda b: ((b.bbox or (0, 0, 0, 0))[1], (b.bbox or (0, 0, 0, 0))[0])):
        for raw in block.text.splitlines():
            line = normalize_prose(raw)
            if not line:
                continue
            if re.fullmatch(r"(?:Article|Review|Methods|Brief Communication|Letter|Resource)", line, re.I):
                continue
            if DOI_RE.search(line) or re.search(r"nature human behaviour|reporting summary|volume\s+\d+", line, re.I):
                continue
            lines.append(line)
    title = " ".join(lines)
    title = re.sub(r"\s+", " ", title).strip(" -")
    return title


def _first_page_lines(extraction: PDFExtraction) -> list[str]:
    return [normalize_prose(line) for line in extraction.page_texts[0].splitlines() if normalize_prose(line)]


def _looks_like_name(value: str) -> bool:
    value = normalize_prose(value).strip(" ,.;")
    if not (2 <= len(value.split()) <= 8):
        return False
    if re.search(
        r"\d|@|doi|received|accepted|published|article|journal|volume|university|institute|department|hospital|centre|center|school|college|laboratory|biobank|consortium|group$",
        value,
        re.I,
    ):
        return False
    tokens = re.findall(r"[A-Za-zÀ-ÖØ-öø-ÿ'’.-]+", value)
    return len(tokens) >= 2 and sum(token[:1].isupper() for token in tokens) >= 2


def _strip_affiliation_markers(text: str) -> str:
    # Publisher title pages mix author names with attached and standalone
    # superscript affiliation numbers. Remove only numeric affiliation syntax.
    text = re.sub(r"[¹²³⁴⁵⁶⁷⁸⁹⁰†‡*]+", "", text)
    text = re.sub(r"(?<=[A-Za-zÀ-ÖØ-öø-ÿ)])\d+(?:,\d+)*", "", text)
    text = re.sub(r"\b\d+(?:,\d+)*\b", "", text)
    text = re.sub(r"\s+,", ",", text)
    return text


def _split_author_line(text: str) -> list[str]:
    text = _strip_affiliation_markers(text)
    text = re.sub(r"\s+", " ", text)
    text = text.replace(" & ", ", ").replace(" and ", ", ")
    parts = [part.strip(" ,.;") for part in text.split(",")]
    return [part for part in parts if _looks_like_name(part)]


def _authors(extraction: PDFExtraction, title: str) -> list[str]:
    lines = _first_page_lines(extraction)
    title_index = 0
    for index, line in enumerate(lines):
        # The title is usually split across several lines; use the last title line.
        if len(line) >= 4 and line.casefold() in title.casefold():
            title_index = index
    author_lines: list[str] = []
    for line in lines[title_index + 1 :]:
        if re.search(r"^(?:Received|Accepted|Published online)\s*:", line, re.I):
            break
        if re.search(r"^(?:Abstract|Summary)\b", line, re.I):
            break
        author_lines.append(line)
    candidates = unique_preserve(_split_author_line(" ".join(author_lines)))

    # Layout fallback: use the largest first-page body block between title and dates.
    if len(candidates) < 2:
        body_blocks = [
            b for b in extraction.blocks if b.page == 1 and b.kind == "body" and (b.bbox or (0, 0, 0, 0))[1] < 350
        ]
        candidates = unique_preserve(_split_author_line(" ".join(b.text for b in body_blocks)))
    return candidates


def _date(text: str, label: str) -> str:
    match = re.search(rf"{re.escape(label)}\s*:?[ ]*({DATE_RE.pattern})", text, re.I)
    return normalize_prose(match.group(1)) if match else ""


def _normalize_date(value: str) -> str:
    if not value:
        return ""
    for fmt in ("%d %B %Y", "%B %d, %Y", "%B %Y"):
        try:
            parsed = datetime.strptime(value.replace("  ", " "), fmt)
            # Portable day formatting; avoid %-d on Windows.
            return f"{parsed.strftime('%B')} {parsed.day}, {parsed.year}"
        except ValueError:
            continue
    return value


def _journal_metadata(first_text: str, full_text: str, path: Path) -> tuple[str, str, str, str, str]:
    journal = ""
    volume = ""
    pages = ""
    issue_date = ""
    article_type = "Article"
    normalized = normalize_prose(first_text.replace("\n", " "))
    match = re.search(
        r"([A-Z][A-Za-z&' -]{2,80})\s*\|\s*Volume\s*(\d+)\s*\|\s*([^|]+?)\s*\|\s*([0-9–-]+)",
        normalized,
        re.I,
    )
    if match:
        journal = normalize_prose(match.group(1))
        volume = match.group(2)
        issue_date = normalize_prose(match.group(3))
        pages = match.group(4).replace("–", "-")
    if not journal:
        visible = re.search(r"^((?:The\s+)?Journal of [A-Za-z&' -]{3,70})$", first_text, re.I | re.M)
        if visible:
            journal = normalize_prose(visible.group(1)).title()
    if not journal:
        citation = re.search(
            r"(?:^|\n)[^\n]{0,120}?\b([A-Z][A-Za-z&' -]{2,70})\s+\((?:19|20)\d{2}\)\s+"
            r"(\d+)(?::([A-Za-z0-9-]+))?",
            first_text,
        )
        if citation:
            candidate = normalize_prose(citation.group(1))
            candidate = re.sub(r"^.*?\bet al\.\s+", "", candidate, flags=re.I)
            journal = candidate
            volume = citation.group(2)
            pages = citation.group(3) or ""
    if not journal:
        candidates = [
            "BMC Psychiatry",
            "Cell Genomics",
            "Nature Genetics",
            "Nature Human Behaviour",
            "Molecular Psychiatry",
            "JAMA Psychiatry",
            "The Lancet Psychiatry",
            "Nature Communications",
            "The New England Journal of Medicine",
            "The BMJ",
        ]
        for candidate in candidates:
            if re.search(rf"(?<![A-Za-z]){re.escape(candidate)}(?![A-Za-z])", first_text[:12000], re.I):
                journal = candidate
                break
    type_match = re.search(r"^(Article|Review|Methods|Brief Communication|Letter|Resource)$", first_text, re.I | re.M)
    if type_match:
        article_type = type_match.group(1).title()
    return journal, volume, pages, issue_date, article_type


def _crossref_date(message: dict, *keys: str) -> tuple[str, int | None]:
    for key in keys:
        parts = ((message.get(key) or {}).get("date-parts") or [[]])[0]
        if not parts:
            continue
        year = int(parts[0])
        if len(parts) >= 3:
            return datetime(year, int(parts[1]), int(parts[2])).strftime("%B %d, %Y").replace(" 0", " "), year
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
        headers={"User-Agent": "paper-digest-deterministic/1.2 (+https://github.com/firecrawl/firecrawl)"},
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
    authors: list[str] = []
    for item in message.get("author") or []:
        if not isinstance(item, dict):
            continue
        name = normalize_prose(" ".join(str(item.get(key, "")) for key in ("given", "family")))
        if name:
            authors.append(name)
    if authors:
        metadata.authorship.authors = unique_preserve(authors)
        metadata.authorship.author_count = len(metadata.authorship.authors)

    containers = message.get("container-title") or []
    if containers:
        metadata.journal = normalize_prose(str(containers[0]))
    metadata.volume = normalize_prose(str(message.get("volume") or metadata.volume))
    metadata.issue = normalize_prose(str(message.get("issue") or metadata.issue))
    metadata.pages_or_article = normalize_prose(
        str(message.get("page") or message.get("article-number") or metadata.pages_or_article)
    )
    online, online_year = _crossref_date(message, "published-online", "published")
    issue_date, issue_year = _crossref_date(message, "published-print", "issued")
    metadata.online_date = online or metadata.online_date
    metadata.issue_date = issue_date or metadata.issue_date
    metadata.year = online_year or issue_year or metadata.year
    registry_type = str(message.get("type") or "").replace("-", " ").strip()
    if registry_type:
        metadata.article_type = registry_type.title()
    metadata.metadata_sources = unique_preserve(metadata.metadata_sources + ["Crossref DOI registry"])
    return True


def _role_segment(full_text: str, labels: list[str]) -> str:
    for label in labels:
        match = re.search(label, full_text, re.I)
        if not match:
            continue
        tail = full_text[match.end() : match.end() + 700]
        tail = re.split(
            r"(?:\.\s|\n\s*\n|\b(?:Received|Accepted|Correspondence|Author contributions)\b)", tail, maxsplit=1
        )[0]
        return normalize_prose(_strip_affiliation_markers(tail))
    return ""


def _role_names(full_text: str, authors: list[str], labels: list[str]) -> list[str]:
    segment = _role_segment(full_text, labels)
    if not segment:
        return []
    found = [author for author in authors if re.search(rf"(?<!\w){re.escape(author)}(?!\w)", segment, re.I)]
    if found:
        return found
    return unique_preserve(_split_author_line(segment))


def _license(full_text: str) -> str:
    if re.search(r"Creative Commons\s+Attribution\s+4\.0|CC BY 4\.0", full_text, re.I):
        return "CC BY 4.0"
    if re.search(r"CC BY", full_text, re.I):
        return "CC BY"
    return ""


def _author_keywords(full_text: str) -> list[str]:
    match = re.search(r"(?:Keywords?|Key words)\s*(?::|—|-)?\s+([^\n]{10,500})", full_text, re.I)
    if not match:
        return []
    values = [
        item.strip(" .;,:-") for item in re.split(r"\s*[;|•]\s*|\s+\.\s+|,\s*", match.group(1)) if item.strip(" .;,:-")
    ]
    return unique_preserve(values)[:15]


def extract_publication_metadata(extraction: PDFExtraction, path: Path) -> PublicationMetadata:
    full = extraction.full_text
    first_raw = "\n".join(b.text for b in extraction.blocks if b.page == 1)
    title = _title(extraction.blocks)
    authors = _authors(extraction, title)
    doi_match = DOI_RE.search(first_raw + " " + full[:5000])
    doi = doi_match.group(0).rstrip(".,)") if doi_match else ""
    journal, volume, pages, issue_date, article_type = _journal_metadata(first_raw, full, path)

    date_corpus = first_raw + "\n" + full[:5000]
    online = _normalize_date(_date(date_corpus, "Published online"))
    received = _normalize_date(_date(date_corpus, "Received"))
    accepted = _normalize_date(_date(date_corpus, "Accepted"))
    year: int | None = None
    for value in (online, issue_date, received):
        match = re.search(r"\b(?:19|20)\d{2}\b", value)
        if match:
            year = int(match.group(0))
            break
    if year is None:
        year_match = re.search(
            r"(?:©\s*(?:The Author\(s\)\s*)?|\()((?:19|20)\d{2})(?:\)|\.)",
            first_raw + "\n" + full[:8000],
            re.I,
        )
        if year_match:
            year = int(year_match.group(1))
    if year is None:
        plausible = [int(value) for value in re.findall(r"\b(?:19|20)\d{2}\b", first_raw[:10000])]
        if plausible:
            year = max(plausible)

    equal = _role_names(
        full, authors, [r"These authors contributed\s+equally\s*:", r"contributed\s+equally to this work"]
    )
    supervisors = _role_names(
        full, authors, [r"These authors jointly\s+supervised this work\s*:", r"jointly\s+supervised this work"]
    )
    corresponding = _role_names(
        full,
        authors,
        [
            r"Corresponding author\(s\)\s*:",
            r"Correspondence and requests for materials should be addressed to",
            r"\*Correspondence\s*:",
        ],
    )

    return PublicationMetadata(
        title=title,
        authorship=AuthorMetadata(
            authors=authors,
            corresponding=unique_preserve(corresponding),
            equal_contributors=unique_preserve(equal),
            joint_supervisors=unique_preserve(supervisors),
            author_count=len(authors) if authors else None,
        ),
        year=year,
        doi=doi,
        journal=journal,
        volume=volume,
        pages_or_article=pages,
        online_date=online,
        issue_date=issue_date,
        received_date=received,
        accepted_date=accepted,
        article_type=article_type,
        license=_license(full),
        author_keywords=_author_keywords(full),
        metadata_sources=["publisher PDF"],
    )
