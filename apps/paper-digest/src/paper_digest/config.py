from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal


@dataclass(slots=True)
class DigestConfig:
    """Runtime configuration for the deterministic compiler.

    The compiler never loads generative models, calls model APIs, or sends paper
    content to an external inference service. Strict mode is fail-closed.
    """

    output_language: Literal["en"] = "en"
    category: str = "auto"
    profile: str = "auto"
    strict: bool = True
    source_collection: str = "publisher-pdf"
    pdf_path: str | None = None
    extracted_date: str | None = None
    max_authors_full: int = 50
    min_body_words: int = 1500
    target_body_words: tuple[int, int] = (2000, 4200)
    hard_max_body_words: int = 6000
    paragraph_soft_max_words: int = 220
    paragraph_hard_max_words: int = 350
    retrieval_top_k: int = 10
    work_dir: Path | None = None
    include_qa: bool = True
    fail_on_missing_supplement: bool = False
    profile_confidence_threshold: float = 0.55
    source_ready_threshold: float = 0.95
    repair_passes: int = 4
    enable_ocr: bool = True
    ocr_language: str = "eng"
    enable_doi_metadata: bool = True
    doi_metadata_timeout_seconds: float = 8.0
    keyword_limit: int = 12
    field_limit: int = 6
    max_archive_members: int = 200
    max_archive_member_bytes: int = 100 * 1024 * 1024
    max_archive_total_bytes: int = 500 * 1024 * 1024
    max_archive_ratio: float = 100.0
    extra: dict[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.output_language != "en":
            raise ValueError("Only English source Markdown is supported by the compatible contract.")
        if not 0.0 < self.source_ready_threshold <= 1.0:
            raise ValueError("source_ready_threshold must be in (0, 1].")
        if not 0.0 < self.profile_confidence_threshold <= 1.0:
            raise ValueError("profile_confidence_threshold must be in (0, 1].")
        if self.min_body_words < 500:
            raise ValueError("min_body_words is implausibly small.")
        if self.target_body_words[0] < self.min_body_words:
            raise ValueError("target_body_words lower bound must be >= min_body_words.")
        if self.target_body_words[1] < self.target_body_words[0]:
            raise ValueError("target_body_words upper bound must be >= lower bound.")
        if self.hard_max_body_words < self.target_body_words[1]:
            raise ValueError("hard_max_body_words must be >= target range upper bound.")
        if self.paragraph_hard_max_words < self.paragraph_soft_max_words:
            raise ValueError("paragraph_hard_max_words must be >= paragraph_soft_max_words.")
        if self.max_authors_full < 1:
            raise ValueError("max_authors_full must be positive.")
        if self.keyword_limit < 6 or self.keyword_limit > 15:
            raise ValueError("keyword_limit must be between 6 and 15.")
        if self.field_limit < 2 or self.field_limit > 6:
            raise ValueError("field_limit must be between 2 and 6.")
        if self.max_archive_members < 1 or self.max_archive_member_bytes < 1 or self.max_archive_total_bytes < 1:
            raise ValueError("archive limits must be positive.")
        if self.max_archive_ratio <= 1:
            raise ValueError("max_archive_ratio must be > 1.")
        if not 1 <= self.repair_passes <= 8:
            raise ValueError("repair_passes must be between 1 and 8.")
        if not 0.5 <= self.doi_metadata_timeout_seconds <= 30:
            raise ValueError("doi_metadata_timeout_seconds must be between 0.5 and 30.")
