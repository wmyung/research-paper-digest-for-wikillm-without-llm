from __future__ import annotations

from pathlib import Path

from paper_digest.models import AuthorMetadata, ParsedBundle, PublicationMetadata, Section


def bundle(tmp_path: Path, text: str = "") -> ParsedBundle:
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"%PDF-1.4\n%%EOF")
    return ParsedBundle(
        files=[],
        canonical_pdf=pdf,
        blocks=[],
        sections={"Front matter": Section("Front matter")},
        full_text=text,
        page_texts=[text],
        metadata=PublicationMetadata(
            title="A deterministic test paper",
            authorship=AuthorMetadata(authors=["A. Example", "B. Example"], author_count=2),
            year=2024,
            doi="10.1000/test.1",
            journal="Test Journal",
            online_date="January 2, 2024",
            article_type="Article",
            research_fields=["measurement science", "method development"],
            index_keywords=["measurement", "cohort", "association", "prediction", "replication", "methods"],
            category="method-development",
        ),
        workbooks=[],
        supplements_text={},
        parser_notes=["pymupdf-test"],
    )
