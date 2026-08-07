from pathlib import Path

from paper_digest.models import Paragraph, ParsedBundle, PublicationMetadata, Section
from paper_digest.profiles.universal import _sentences
from paper_digest.text import clean_line, normalize_prose


def _bundle_with_results(*paragraphs: str) -> ParsedBundle:
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
    assert normalize_prose("psychiatric dis\u00ad orders and low-to moderate effects") == (
        "psychiatric disorders and low-to-moderate effects"
    )
    first = clean_line("occu\u00ad")
    second = clean_line("pations were classified")
    assert normalize_prose(first + "\n" + second) == "occupations were classified"


def test_caption_and_incomplete_pdf_fragments_are_not_candidates():
    bundle = _bundle_with_results(
        "The GWAS identified 25 lead variants across 18 loci.",
        "The dashed line indicates the significance threshold at P < 0.05. c.",
        "The threshold for significance is indicated by the red horizontal line.",
        "The adjusted model showed concordance with the initial model (rg = 0.948 and rho",
        "It was interesting to find that the estimate was not significant at FDR < Interestingly, another result differed.",
        "Polygenic overlap between both traits In MiXeR analysis (Figure S5), MD.",
        "Two traits were not significant but are included in this figure.",
        "showed the most genetic overlap with the outcome (DC = 96%).",
        "Our results are clinically relevant, as patients CRediT authorship contribution statement Author: Writing.",
        "Venn diagrams depicting the shared variants between the two traits are shown.",
    )
    assert [candidate.text for candidate in _sentences(bundle)] == [
        "The GWAS identified 25 lead variants across 18 loci."
    ]


def test_fused_publisher_subheading_is_removed():
    bundle = _bundle_with_results(
        "Genome-wide significant association signals and candidate causal genes "
        "The GWAS identified 25 lead variants across 18 significant loci."
    )
    assert [candidate.text for candidate in _sentences(bundle)] == [
        "The GWAS identified 25 lead variants across 18 significant loci."
    ]


def test_embedded_and_repeated_publisher_subheadings_are_removed():
    bundle = _bundle_with_results(
        "There was no strong enrichment among the tested tissue categories. "
        "Genetic correlation with psychiatric disorders "
        "Seven psychiatric disorders were significantly correlated with the outcome.",
        "PRSs for psychiatric disorders and associations with OC "
        "PRSs for seven disorders were significantly associated with the outcome.",
        "CondFDR for psychiatric disorders and OC "
        "The results identified several additional loci across psychiatric disorders.",
    )
    assert [candidate.text for candidate in _sentences(bundle)] == [
        "There was no strong enrichment among the tested tissue categories.",
        "Seven psychiatric disorders were significantly correlated with the outcome.",
        "PRSs for seven disorders were significantly associated with the outcome.",
        "The results identified several additional loci across psychiatric disorders.",
    ]
