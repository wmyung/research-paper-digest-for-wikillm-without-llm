"""Bibliographic resolution from a synthetic publisher PDF."""

from __future__ import annotations

import pytest
from paper_digest.metadata import extract_publication_metadata
from paper_digest.parsers.pdf import extract_pdf
from synthetic import SyntheticPaper, build_pdf


def _metadata(tmp_path, paper: SyntheticPaper | None = None):
    path = build_pdf(tmp_path / "paper.pdf", paper)
    extraction = extract_pdf(path, enable_ocr=False)
    return extract_publication_metadata(extraction, path)


@pytest.fixture(scope="module")
def plain(tmp_path_factory):
    return _metadata(tmp_path_factory.mktemp("meta"))


def test_title_excludes_the_article_type_label(plain):
    assert plain.title == "Deterministic extraction of structured records from publisher PDFs"
    assert plain.article_type == "Article"


def test_ordered_author_list_is_complete_and_marker_free(plain):
    assert plain.authorship.authors == [
        "Aisha N. Okonkwo",
        "Bjorn Halvorsen",
        "Mei-Ling Chen",
        "Rafael de Souza",
    ]
    assert plain.authorship.author_count == 4
    assert plain.authorship.corresponding == ["Aisha N. Okonkwo"]


def test_journal_and_doi_are_resolved_without_a_hardcoded_list(plain):
    assert plain.journal == "Journal of Reproducible Informatics"
    assert plain.doi == "10.1234/jri.2024.0042"


def test_publication_date_follows_the_published_over_accepted_priority(plain):
    assert plain.publication_date == "August 2, 2024"
    assert plain.publication_date_label == "published"
    assert plain.accepted_date == "June 19, 2024"
    assert plain.received_date == "March 4, 2024"
    assert plain.year == 2024


def test_keywords_and_abstract_are_captured_verbatim(plain):
    assert plain.author_keywords[:2] == ["Record linkage", "Extraction quality"]
    assert "412 articles" in plain.abstract


def test_every_core_field_records_its_source_and_page(plain):
    for field in ("title", "authors", "journal", "doi", "publication_date"):
        assert field in plain.evidence, field
        assert plain.evidence[field].source
        assert plain.evidence[field].source_excerpt


def test_cover_sheet_does_not_displace_the_article_metadata(tmp_path):
    covered = _metadata(tmp_path, SyntheticPaper(cover_sheet=True))
    assert covered.title == "Deterministic extraction of structured records from publisher PDFs"
    assert covered.authorship.authors[0] == "Aisha N. Okonkwo"
    assert "repository" not in covered.title.casefold()


def test_missing_publisher_fields_degrade_without_inventing_values(tmp_path):
    bare = SyntheticPaper(received="", accepted="", published="", keywords="")
    metadata = _metadata(tmp_path, bare)
    assert metadata.publication_date == ""
    assert metadata.author_keywords == []
    assert metadata.title  # the layout title still resolves


def test_a_byline_fused_with_its_affiliations_is_still_split(tmp_path):
    # Wiley-style front matter sets the byline and the affiliation in one block.
    fused = SyntheticPaper(
        authors="Aisha N. Okonkwo, Bjorn Halvorsen, Mei-Ling Chen",
        affiliations=("Department of Clinical Epidemiology, Northfield University, Northfield, United Kingdom",),
    )
    metadata = _metadata(tmp_path, fused)
    assert metadata.authorship.authors == ["Aisha N. Okonkwo", "Bjorn Halvorsen", "Mei-Ling Chen"]
    assert "Northfield University" not in " ".join(metadata.authorship.authors)
