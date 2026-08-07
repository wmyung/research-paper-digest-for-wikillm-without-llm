from __future__ import annotations

import re
import unicodedata
from datetime import date

from .config import DigestConfig
from .models import ParsedBundle, PublicationMetadata
from .profiles.base import ProfileContent
from .text import markdown_escape_yaml

REQUIRED_HEADINGS = [
    "## One-line Summary",
    "## 1. Document Information",
    "## 2. Key Contributions",
    "## 3. Methodology and Architecture",
    "## 4. Key Results and Benchmarks",
    "## 5. Limitations and Future Work",
    "## 6. Related Work",
    "## 7. Glossary",
]
FRONTMATTER_KEYS = [
    "title",
    "authors",
    "year",
    "doi",
    "category",
    "pdf_path",
    "pdf_filename",
    "source_collection",
    "source_format",
    "text_extractor",
    "text_extracted_date",
]


def ascii_tokens(text: str) -> list[str]:
    normalized = unicodedata.normalize("NFKD", text)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii").lower()
    return re.findall(r"[a-z0-9]+", ascii_text)


def surname_from_author(author: str) -> str:
    author = author.strip()
    if not author:
        raise ValueError("First-author name is empty.")
    candidate = author.split(",", 1)[0] if "," in author else author.split()[-1]
    tokens = ascii_tokens(candidate)
    if not tokens:
        raise ValueError(f"Could not derive a filename surname from {author!r}.")
    return "-".join(tokens)


def make_stem(metadata: PublicationMetadata, title_token_count: int = 5) -> str:
    surname = surname_from_author(metadata.authorship.authors[0]) if metadata.authorship.authors else "paper"
    year = (
        str(metadata.year)
        if metadata.year is not None and re.fullmatch(r"(?:19|20)\d{2}", str(metadata.year))
        else "undated"
    )
    title_tokens = ascii_tokens(metadata.title)
    title_tokens = title_tokens or ["source-record"]
    return "-".join([surname, year, *title_tokens[:title_token_count]])


def _yaml_string(value: str) -> str:
    return f'"{markdown_escape_yaml(value)}"'


def compile_markdown(
    bundle: ParsedBundle, content: ProfileContent, config: DigestConfig, stem: str | None = None
) -> tuple[str, str]:
    metadata = bundle.metadata
    stem = stem or make_stem(metadata)
    pdf_filename = f"{stem}.pdf"
    pdf_path = config.pdf_path or f"/papers/{pdf_filename}"
    extracted_date = config.extracted_date or date.today().isoformat()
    authors = ", ".join(metadata.authorship.authors)
    frontmatter = [
        "---",
        f"title: {_yaml_string(metadata.title)}",
        f"authors: {authors}",
        f"year: {metadata.year or ''}",
        f"doi: {metadata.doi}",
        f"category: {metadata.category}",
        f"pdf_path: {pdf_path}",
        f"pdf_filename: {pdf_filename}",
        f"source_collection: {config.source_collection}",
        "source_format: pdf",
        f"text_extractor: {bundle.parser_notes[0] if bundle.parser_notes else 'pymupdf-layout'}",
        f"text_extracted_date: {extracted_date}",
        "---",
    ]
    values = [
        content.one_line_summary,
        content.document_information,
        content.key_contributions,
        content.methodology,
        content.results,
        content.limitations,
        content.related_work,
        content.glossary,
    ]
    body: list[str] = []
    for heading, value in zip(REQUIRED_HEADINGS, values, strict=True):
        body.extend([heading, "", re.sub(r"\n{3,}", "\n\n", value.strip()), ""])
    return "\n".join(frontmatter + [""] + body).rstrip() + "\n", f"{stem}.md"
