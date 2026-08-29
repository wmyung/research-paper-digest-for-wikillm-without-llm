"""Feature probes and evidence selection."""

from __future__ import annotations

from pathlib import Path

from paper_digest import features as F
from paper_digest.models import Paragraph, ParsedBundle, PublicationMetadata, Section
from paper_digest.selection import build_candidates, clean_sentence, score_for, select


def _bundle(**sections: tuple[str, ...]) -> ParsedBundle:
    built: dict[str, Section] = {}
    page = 1
    for name, paragraphs in sections.items():
        name = name.replace("_", " ")
        built[name] = Section(
            name,
            [
                Paragraph(text=text, section=name, page_start=page, page_end=page, source_file="synthetic.pdf")
                for text in paragraphs
            ],
        )
        page += 1
    return ParsedBundle(
        files=[],
        canonical_pdf=Path("synthetic.pdf"),
        blocks=[],
        sections=built,
        full_text="\n".join(text for paragraphs in sections.values() for text in paragraphs),
        page_texts=[],
        metadata=PublicationMetadata(),
        workbooks=[],
        supplements_text={},
    )


def test_relational_score_counts_the_five_retrieval_components():
    strong = (
        "PRS-CSx explained more variance in EduYears than PRS-CS among 12,000 participants, "
        "3.96% versus 2.19% (P < 0.001)."
    )
    weak = "Performance was better in the combined analysis."
    assert F.relational_components(strong) >= 4
    assert F.relational_components(weak) <= 2


def test_checklist_instructions_and_glossary_definitions_are_rejected():
    for text in (
        "Specify the inclusion and exclusion criteria for the review and how studies were grouped.",
        "Record — The title or abstract of a report indexed in a database such as Medline.",
        "Systematic review is defined as a review that uses explicit methods to collate findings.",
    ):
        assert F.extract(text).is_structural_noise, text


def test_interview_quotations_and_split_quotations_are_rejected():
    assert F.extract('MTA PHS1: "When you evaluate the health questionnaire you need more detail."').is_quotation
    assert F.extract(
        'Therefore I would like to discuss duration of stay." The guideline states that.'
    ).is_quote_fragment


def test_column_splices_are_rejected():
    assert F.extract("However, of We encourage readers to submit evidence informing the recommendations.").is_spliced


def test_limitation_requires_an_explicit_cue_or_a_first_person_inability():
    assert F.extract("We could not calculate acceptance rates because screening was mandatory.").has_limitation
    assert not F.extract("Staff said that some clients could not believe the diagnosis.").has_limitation


def test_clean_sentence_strips_citation_markers_and_display_references():
    assert clean_sentence("[10] In this pilot study, we addressed the identified barriers.") == (
        "In this pilot study, we addressed the identified barriers."
    )
    assert clean_sentence("Treatment initiation declined with age (Table 1) across all services.") == (
        "Treatment initiation declined with age across all services."
    )


def test_candidates_come_only_from_scientific_sections():
    bundle = _bundle(
        Results=("Accuracy was 94.1% versus 71.8% in the two arms, a difference of 22.3 points.",),
        References=("1. Chen M-L. Table detection without supervision. Proc Doc Anal 2023;7:44-57.",),
        Acknowledgements=("We thank the reviewers for their comments on an earlier draft of this paper.",),
    )
    texts = [candidate.text for candidate in build_candidates(bundle)]
    assert texts == ["Accuracy was 94.1% versus 71.8% in the two arms, a difference of 22.3 points."]


def test_results_outrank_methods_for_an_effect_sentence():
    bundle = _bundle(
        Results=("Accuracy was 94.1% versus 71.8%, a difference of 22.3 percentage points (P < 0.001).",),
    )
    candidate = build_candidates(bundle)[0]
    assert score_for(candidate, "results") > score_for(candidate, "methods")


def test_selection_suppresses_near_duplicates_across_sections():
    sentence = "Field accuracy was 94.1% for the layout-aware pipeline and 71.8% for the baseline overall."
    bundle = _bundle(Results=(sentence, sentence.replace("overall", "in every stratum")))
    candidates = build_candidates(bundle)
    chosen = select(candidates, "results", budget=400, limit=5, taken=[])
    assert len(chosen) == 1
