from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

FileRole = Literal[
    "canonical-paper",
    "supplement",
    "format-reference",
    "external-context",
    "duplicate",
    "unrelated",
]


@dataclass(slots=True)
class InputFile:
    path: Path
    role: FileRole
    media_type: str
    size_bytes: int
    sha256: str
    page_count: int | None = None
    sheet_count: int | None = None
    note: str | None = None


@dataclass(slots=True)
class TextBlock:
    text: str
    page: int
    bbox: tuple[float, float, float, float] | None = None
    font_size: float | None = None
    font_name: str | None = None
    kind: str = "body"
    source_file: str | None = None
    extraction_method: str = "text-layer"


@dataclass(slots=True)
class Paragraph:
    text: str
    section: str
    page_start: int
    page_end: int
    source_file: str
    subsection: str | None = None
    score: float = 0.0
    tags: set[str] = field(default_factory=set)


@dataclass(slots=True)
class Section:
    name: str
    paragraphs: list[Paragraph] = field(default_factory=list)


@dataclass(slots=True)
class AuthorMetadata:
    authors: list[str] = field(default_factory=list)
    group_authors: list[str] = field(default_factory=list)
    corresponding: list[str] = field(default_factory=list)
    equal_contributors: list[str] = field(default_factory=list)
    joint_supervisors: list[str] = field(default_factory=list)
    author_count: int | None = None
    representation_note: str = ""


@dataclass(slots=True)
class FieldEvidence:
    """Where a bibliographic value came from, for the grounding ledger."""

    value: str
    source: str
    page: int | None = None
    source_excerpt: str = ""


@dataclass(slots=True)
class PublicationMetadata:
    title: str = ""
    authorship: AuthorMetadata = field(default_factory=AuthorMetadata)
    year: int | None = None
    doi: str = ""
    journal: str = ""
    volume: str = ""
    issue: str = ""
    pages_or_article: str = ""
    online_date: str = ""
    issue_date: str = ""
    received_date: str = ""
    accepted_date: str = ""
    article_type: str = "Article"
    license: str = ""
    author_keywords: list[str] = field(default_factory=list)
    research_fields: list[str] = field(default_factory=list)
    index_keywords: list[str] = field(default_factory=list)
    category: str = "other"
    article_number: str = ""
    issn: str = ""
    revised_date: str = ""
    publication_date: str = ""
    publication_date_label: str = ""
    abstract: str = ""
    document_profile: str = "empirical_research"
    metadata_sources: list[str] = field(default_factory=list)
    evidence: dict[str, FieldEvidence] = field(default_factory=dict)


@dataclass(slots=True)
class WorkbookSheet:
    file_name: str
    sheet_name: str
    state: str
    max_row: int
    max_column: int
    title: str
    rows: list[list[Any]] = field(default_factory=list)
    nonempty_cells: int = 0


@dataclass(slots=True)
class ParsedBundle:
    files: list[InputFile]
    canonical_pdf: Path
    blocks: list[TextBlock]
    sections: dict[str, Section]
    full_text: str
    page_texts: list[str]
    metadata: PublicationMetadata
    workbooks: list[WorkbookSheet]
    supplements_text: dict[str, str]
    parser_notes: list[str] = field(default_factory=list)
    ocr_pages: list[int] = field(default_factory=list)
    figure_caption_count: int = 0
    table_caption_count: int = 0
    grounding_text: str = ""
    labelled_fields: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class CompiledDigest:
    status: Literal["SOURCE_READY", "NOT_SOURCE_READY"]
    markdown: str
    filename: str
    metadata: PublicationMetadata
    qa: dict[str, Any]
    bundle: ParsedBundle | None = None

    def to_dict(self, include_markdown: bool = True) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "success": self.status == "SOURCE_READY",
            "status": self.status,
            "filename": self.filename,
            "metadata": asdict(self.metadata),
            "qa": self.qa,
        }
        if include_markdown:
            payload["markdown"] = self.markdown
        return payload
