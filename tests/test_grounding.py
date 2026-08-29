"""Verbatim grounding verification."""

from __future__ import annotations

from paper_digest.grounding import (
    audit,
    build_index,
    is_grounded,
    prose_sentences,
    skeleton,
)

SOURCE = (
    "Field accuracy was 94.1% for the layout-aware pipeline and 71.8% for the baseline, "
    "a difference of 22.3 percentage points (95% CI 19.4 to 25.2, P < 0.001). "
    "Accuracy did not differ between two-column and single-column layouts (P = 0.41)."
)


def test_skeleton_ignores_punctuation_and_case():
    assert skeleton("P < 0.001, 94.1%!") == "p 0 001 94 1"


def test_a_quoted_sentence_is_grounded_even_after_marker_removal():
    index = build_index(SOURCE)
    assert is_grounded("Accuracy did not differ between two-column and single-column layouts.", index)
    assert is_grounded("Field accuracy was 94.1% for the layout-aware pipeline and 71.8% for the baseline", index)


def test_a_paraphrase_is_not_grounded():
    index = build_index(SOURCE)
    assert not is_grounded("The layout-aware pipeline was considerably more accurate than the baseline.", index)


def test_a_swapped_number_is_not_grounded():
    index = build_index(SOURCE)
    assert not is_grounded("Field accuracy was 49.1% for the layout-aware pipeline and 71.8%.", index)


def test_audit_reports_the_offending_sentences():
    report = audit(
        [
            "Accuracy did not differ between two-column and single-column layouts.",
            "The pipeline is the best available anywhere.",
        ],
        SOURCE,
    )
    assert report["checked"] == 2
    assert report["ungrounded_count"] == 1
    assert report["ungrounded"] == ["The pipeline is the best available anywhere."]


def test_prose_sentences_skips_headings_frontmatter_and_glossary_entries():
    markdown = (
        '---\ntitle: "A"\nauthors: B\n---\n\n'
        "## 4. Key Results and Benchmarks\n\n"
        "### Primary findings\n\n"
        "Accuracy was 94.1% versus 71.8% across the nine publishers evaluated here.\n\n"
        "## 7. Glossary\n\n"
        "- **CI** — confidence interval.\n"
    )
    assert prose_sentences(markdown) == ["Accuracy was 94.1% versus 71.8% across the nine publishers evaluated here."]
