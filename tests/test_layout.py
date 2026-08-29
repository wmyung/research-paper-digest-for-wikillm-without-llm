"""Layout analysis: columns, running heads, cover sheets, tables, front matter."""

from __future__ import annotations

from collections import Counter

import pymupdf
import pytest
from paper_digest.parsers import layout as L
from paper_digest.parsers.pdf import extract_pdf
from synthetic import SyntheticPaper, build_pdf


@pytest.fixture(scope="module")
def plain(tmp_path_factory):
    path = build_pdf(tmp_path_factory.mktemp("plain") / "paper.pdf")
    return extract_pdf(path, enable_ocr=False)


@pytest.fixture(scope="module")
def with_cover(tmp_path_factory):
    path = build_pdf(tmp_path_factory.mktemp("cover") / "paper.pdf", SyntheticPaper(cover_sheet=True))
    return extract_pdf(path, enable_ocr=False)


def test_body_font_size_is_the_running_text_size(plain):
    assert plain.body_font_size == pytest.approx(10.0, abs=0.6)


def test_running_head_and_foot_are_tagged_by_recurrence(plain):
    kinds = Counter(block.kind for block in plain.blocks)
    assert kinds["header"] >= 3
    assert kinds["footer"] >= 3
    assert any("Journal of Reproducible Informatics" in line for line in plain.running_heads["header"])
    assert any("doi.org" in line for line in plain.running_heads["footer"])


def test_repository_cover_sheet_is_excluded_and_does_not_change_the_title(plain, with_cover):
    assert with_cover.cover_pages == [1]
    assert plain.cover_pages == []
    assert with_cover.front_matter.title == plain.front_matter.title
    assert "repository copy" not in with_cover.full_text.casefold()


def test_front_matter_separates_title_byline_and_affiliations(plain):
    assert plain.front_matter.title == "Deterministic extraction of structured records from publisher PDFs"
    assert plain.front_matter.article_type == "Research Article"
    assert "Okonkwo" in plain.front_matter.author_text
    assert "Northfield University" in plain.front_matter.affiliation_text
    assert not any("Northfield University" in block.text for block in plain.blocks if block.kind in L.PROSE_KINDS)


def test_table_rows_under_a_caption_never_reach_the_prose(plain):
    captions = [block for block in plain.blocks if block.kind == "caption"]
    assert any(block.text.startswith("Table 1.") for block in captions)
    assert "Alpha Press two-column" not in plain.full_text
    assert any(block.kind == "table" and "Alpha Press" in block.text for block in plain.blocks)


def test_reference_list_is_excluded_from_prose(plain):
    assert "Layout analysis for scholarly documents" not in plain.full_text
    assert any(block.kind == "reference" for block in plain.blocks)


def test_structured_abstract_is_tagged(plain):
    abstract = " ".join(block.text for block in plain.blocks if block.kind == "abstract")
    assert "412 articles" in abstract or "nine publishers" in abstract


def test_labelled_publisher_fields_are_harvested(plain):
    labels = {item.label for item in plain.metadata_fields}
    assert {"received", "accepted", "published", "keywords"} <= labels


def test_column_detection_finds_two_bands_on_a_two_column_page():
    document = pymupdf.open()
    page = document.new_page(width=595, height=842)
    for x0 in (48, 320):
        for y in range(80, 700, 24):
            page.insert_text((x0, y), "deterministic layout analysis text", fontsize=10)
    raw = L.build_raw_page(page.get_text("dict"), 1, 595, 842, "text-layer")
    document.close()
    columns = L.detect_columns(raw.blocks, 595, 842)
    assert len(columns) == 2
    assert columns[0][1] < columns[1][0]


def test_reading_order_follows_columns_not_the_content_stream():
    document = pymupdf.open()
    page = document.new_page(width=595, height=842)
    # Draw the right column first so stream order disagrees with reading order.
    for index, y in enumerate(range(100, 400, 30)):
        page.insert_text((320, y), f"right {index}", fontsize=10)
    for index, y in enumerate(range(100, 400, 30)):
        page.insert_text((48, y), f"left {index}", fontsize=10)
    raw = L.build_raw_page(page.get_text("dict"), 1, 595, 842, "text-layer")
    document.close()
    raw.columns = L.detect_columns(raw.blocks, 595, 842)
    ordered = [block.text for block in L.order_page(raw)]
    assert ordered.index("left 0") < ordered.index("right 0")
