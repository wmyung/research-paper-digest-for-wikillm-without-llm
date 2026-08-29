"""Text normalisation and candidate hygiene."""

from __future__ import annotations

from pathlib import Path

from paper_digest.models import Paragraph, ParsedBundle, PublicationMetadata, Section
from paper_digest.selection import build_candidates
from paper_digest.text import (
    clean_line,
    has_finite_verb,
    normalize_prose,
    split_sentences,
)


def _results_bundle(*paragraphs: str) -> ParsedBundle:
    return ParsedBundle(
        files=[],
        canonical_pdf=Path("synthetic.pdf"),
        blocks=[],
        sections={
            "Results": Section(
                "Results",
                [
                    Paragraph(text=text, section="Results", page_start=1, page_end=1, source_file="synthetic.pdf")
                    for text in paragraphs
                ],
            )
        },
        full_text=" ".join(paragraphs),
        page_texts=list(paragraphs),
        metadata=PublicationMetadata(),
        workbooks=[],
        supplements_text={},
    )


def test_soft_hyphens_are_removed_without_joining_to_compounds():
    assert normalize_prose("psychiatric dis­ orders and low-to moderate effects") == (
        "psychiatric disorders and low-to-moderate effects"
    )
    first = clean_line("occu­")
    second = clean_line("pations were classified")
    assert normalize_prose(first + "\n" + second) == "occupations were classified"


def test_suspended_hyphens_survive_de_hyphenation():
    assert normalize_prose("author- and index-level terms") == "author- and index-level terms"
    assert normalize_prose("sys-\ntematic reviews") == "systematic reviews"


def test_finite_verb_probe_separates_clauses_from_table_cells():
    assert has_finite_verb("Accuracy was higher in the layout-aware pipeline.")
    assert not has_finite_verb("Publisher Layout Records Baseline")


def test_sentence_splitting_protects_abbreviations_and_decimals():
    assert split_sentences("Accuracy was 94.1% (e.g. Fig. 2). The baseline lagged.") == [
        "Accuracy was 94.1% (e.g. Fig. 2).",
        "The baseline lagged.",
    ]


def test_captions_fragments_and_publisher_noise_are_not_candidates():
    bundle = _results_bundle(
        "The GWAS identified 25 lead variants across 18 loci.",
        "Figure 3. The dashed line indicates the significance threshold at P < 0.05.",
        "Specify the methods used to assess risk of bias in the included studies.",
        "Record — The title or abstract of a report indexed in a database such as Medline.",
        "This article is distributed under the terms of the Creative Commons Attribution licence.",
        "Publisher Layout Records Baseline Layout-aware",
        "showed the most genetic overlap with the outcome (DC = 96%).",
        "However, of We encourage readers to submit further evidence about the recommendations.",
    )
    assert [candidate.text for candidate in build_candidates(bundle)] == [
        "The GWAS identified 25 lead variants across 18 loci."
    ]


def test_leading_citation_markers_are_removed_from_retained_sentences():
    bundle = _results_bundle("[12] Accuracy improved from 71.8% to 94.1% across the nine publishers studied.")
    assert build_candidates(bundle)[0].text == (
        "Accuracy improved from 71.8% to 94.1% across the nine publishers studied."
    )
