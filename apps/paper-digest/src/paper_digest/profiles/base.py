from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from ..models import ParsedBundle


@dataclass(slots=True)
class ProfileScore:
    name: str
    category: str
    score: float
    matched: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ProfileContent:
    one_line_summary: str
    document_information: str
    key_contributions: str
    methodology: str
    results: str
    limitations: str
    related_work: str
    glossary: str
    warnings: list[str] = field(default_factory=list)
    evidence: list[dict[str, object]] = field(default_factory=list)
    retrieval_queries: list[dict[str, object]] = field(default_factory=list)
    # Sentences the compiler wrote itself (absence notes, glossary fallbacks).
    # Everything else in the body must be a verbatim source span.
    authored: list[str] = field(default_factory=list)


class PaperProfile(Protocol):
    name: str
    category: str

    def score(self, bundle: ParsedBundle) -> ProfileScore: ...
    def classify(self, bundle: ParsedBundle) -> None: ...
    def compile(self, bundle: ParsedBundle) -> ProfileContent: ...
