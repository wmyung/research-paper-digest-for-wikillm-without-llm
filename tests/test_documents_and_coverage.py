"""Document-profile routing and the evidence coverage ledger."""

from __future__ import annotations

from pathlib import Path

from paper_digest.documents import PROFILES_BY_KEY, classify_document
from paper_digest.evidence import coverage_ledger, metadata_ledger
from paper_digest.models import (
    FieldEvidence,
    Paragraph,
    ParsedBundle,
    PublicationMetadata,
    Section,
)
from paper_digest.taxonomy import classify_design


def _bundle(sections: dict[str, list[str]], metadata: PublicationMetadata | None = None) -> ParsedBundle:
    built = {
        name: Section(
            name,
            [Paragraph(text=text, section=name, page_start=1, page_end=1, source_file="s.pdf") for text in paragraphs],
        )
        for name, paragraphs in sections.items()
    }
    return ParsedBundle(
        files=[],
        canonical_pdf=Path("s.pdf"),
        blocks=[],
        sections=built,
        full_text="\n".join(text for paragraphs in sections.values() for text in paragraphs),
        page_texts=[],
        metadata=metadata or PublicationMetadata(),
        workbooks=[],
        supplements_text={},
    )


def test_reporting_guideline_is_not_mistaken_for_a_systematic_review():
    profile, ranking = classify_document(
        "The PRISMA 2020 statement: An updated guideline for reporting systematic reviews",
        "The PRISMA 2020 statement replaces the 2009 statement and includes a 27-item checklist.",
        "We recommend authors report their review in accordance with the recommendations. "
        "The panel reached consensus at an in-person meeting.",
        "Article",
    )
    assert profile.key == "guideline_consensus"
    assert ranking[0][0] == "guideline_consensus"


def test_systematic_review_is_recognised_from_its_own_methods():
    profile, _ = classify_document(
        "Effect of screening on tuberculosis incidence: a systematic review and meta-analysis",
        "We systematically searched MEDLINE and Embase and pooled estimates using random effects.",
        "Records were screened in duplicate. Risk of bias was assessed with ROBINS-I. "
        "The pooled estimate was 0.72 (95% CI 0.61 to 0.85).",
        "Article",
    )
    assert profile.key == "systematic_review_meta_analysis"


def test_protocol_declares_results_not_applicable():
    profile, _ = classify_document(
        "Effect of a screening intervention: study protocol for a randomised trial",
        "This protocol describes a trial in which participants will be randomised to two arms.",
        "Outcomes will be collected at twelve months and analysed by intention to treat.",
        "Protocol",
    )
    assert profile.key == "study_protocol"
    assert "results" not in profile.applicable_targets


def test_correction_notices_are_routed_out_of_the_research_profiles():
    profile, _ = classify_document(
        "Correction: Implementation of latent tuberculosis screening",
        "",
        "This is a correction notice for the article published in volume 14.",
        "Correction",
    )
    assert profile.key == "excluded_non_paper"


def test_publisher_article_type_routes_short_correspondence_before_empirical_gates():
    profile, ranking = classify_document(
        "Response to the report on deterministic extraction",
        "We read the report and clarify how the proposed boundary should be interpreted.",
        "The authors reply to a point raised in the original publication.",
        "Correspondence",
        section_names={"Introduction", "Discussion"},
        page_count=2,
    )
    assert profile.key == "letter_response_correspondence"
    assert ranking[0][0] == "letter_response_correspondence"


def test_real_methods_and_results_sections_resist_a_weak_short_document_prior():
    profile, _ = classify_document(
        "A brief evaluation of deterministic extraction",
        "We measured accuracy in 412 records and report the comparison.",
        "Participants were analysed using regression. Accuracy increased to 94.1%.",
        "Article",
        section_names={"Methods", "Results"},
        page_count=3,
    )
    assert profile.key == "empirical_research"


def test_design_taxonomy_prefers_title_evidence():
    category, fields = classify_design(
        "A randomised controlled trial of screening", "Participants were randomised to two arms.", "", "Article"
    )
    assert category == "randomized-trial"
    assert "clinical research" in fields


def test_coverage_ledger_marks_covered_absent_and_optional_slots():
    bundle = _bundle(
        {
            "Abstract": ["We aimed to estimate the accuracy of a deterministic extraction pipeline."],
            "Methods": [
                "We recruited 412 records, measured field accuracy, and fitted a logistic regression model. "
                "The cohort was analysed with a prespecified protocol."
            ],
            "Results": ["Accuracy was 94.1% versus 71.8% (95% CI 19.4 to 25.2, P < 0.001)."],
        }
    )
    ledger = coverage_ledger(bundle, PROFILES_BY_KEY["empirical_research"], {"results": ["x"]})
    statuses = {slot["id"]: slot["status"] for slot in ledger["slots"]}
    assert statuses["objective_or_question"] == "covered"
    assert statuses["primary_result_with_effect_size"] == "covered"
    assert statuses["limitations_or_boundaries"] == "absent_in_source"
    assert statuses["subgroup_or_sensitivity_analysis"] == "not_applicable"
    assert 0.0 <= ledger["coverage_ratio"] <= 1.0
    assert ledger["unchecked_slots"] == []


def test_covered_slots_record_their_page_and_excerpt():
    bundle = _bundle({"Abstract": ["We aimed to estimate the accuracy of a deterministic pipeline."]})
    ledger = coverage_ledger(bundle, PROFILES_BY_KEY["empirical_research"], {})
    objective = next(slot for slot in ledger["slots"] if slot["id"] == "objective_or_question")
    assert objective["evidence_locations"][0]["page"] == 1
    assert "accuracy" in objective["evidence_locations"][0]["source_excerpt"]


def test_metadata_ledger_exposes_value_source_and_excerpt():
    metadata = PublicationMetadata()
    metadata.evidence["title"] = FieldEvidence(
        value="A title", source="layout title block", page=2, source_excerpt="A title"
    )
    bundle = _bundle({"Abstract": ["Text."]}, metadata)
    entries = metadata_ledger(bundle)
    assert entries == [
        {
            "field": "title",
            "value": "A title",
            "source": "layout title block",
            "page": 2,
            "source_excerpt": "A title",
        }
    ]
