"""QA is fail-closed: any error demotes the record regardless of the score."""

from __future__ import annotations

from helpers import bundle
from paper_digest.compiler import compile_markdown
from paper_digest.config import DigestConfig
from paper_digest.profiles.base import ProfileContent, ProfileScore
from paper_digest.qa import evaluate_digest

CLASSIFICATION = """### Classification metadata

- **Journal:** *Test Journal*
- **Publication date:** Published online January 2, 2024
- **Article type:** Article
- **Author count:** 2
- **Author notes:** No special authorship roles were stated in the supplied paper.
- **Research fields (editorial):** measurement science; method development
- **Index keywords (editorial):** measurement; cohort; association; prediction; replication; methods
"""
FILLER = " ".join(["N = 100 and P = 0.01 was not significant. Limitations Related Work Glossary evidence"] * 220)


def _evaluate(tmp_path, *, content: ProfileContent, source: str = "", **kwargs):
    b = bundle(tmp_path)
    if source:
        b.grounding_text = source
        b.full_text = source
    markdown, _ = compile_markdown(b, content, DigestConfig(extracted_date="2026-08-07"))
    return evaluate_digest(
        markdown,
        b,
        "universal",
        [ProfileScore("universal", "other", 0.75)],
        [],
        DigestConfig(),
        **kwargs,
    )


def _content(summary: str = FILLER) -> ProfileContent:
    return ProfileContent(summary, CLASSIFICATION + "\n\n" + FILLER, FILLER, FILLER, FILLER, FILLER, FILLER, FILLER)


def test_digest_without_page_grounded_evidence_is_not_certified(tmp_path):
    qa = _evaluate(tmp_path, content=_content())
    assert qa["source_ready"] is False
    assert qa["quality_score"] < qa["threshold"]
    assert any("page-grounded evidence" in error for error in qa["errors"])


def test_prose_that_is_not_a_verbatim_source_span_is_a_hard_failure(tmp_path):
    evidence = [
        {"statement": f"Grounded evidence statement number {index} was retained.", "page_start": 1}
        for index in range(12)
    ]
    qa = _evaluate(
        tmp_path,
        content=_content(),
        source="An unrelated source document that shares no sentence with the digest body.",
        evidence=evidence,
    )
    assert qa["source_ready"] is False
    assert any("not verbatim spans" in error for error in qa["errors"])
    assert qa["checks"]["grounding"]["ungrounded_count"] > 0


def test_declared_authored_notes_are_exempt_from_the_grounding_check(tmp_path):
    note = "The source states no limitation, caveat or boundary condition."
    evidence = [
        {"statement": f"Grounded evidence statement number {index} was retained.", "page_start": 1}
        for index in range(12)
    ]
    grounded = _evaluate(
        tmp_path,
        content=ProfileContent(note, CLASSIFICATION + "\n\n" + note, note, note, note, note, note, note),
        source=" ",
        evidence=evidence,
        authored=[note],
    )
    assert grounded["checks"]["grounding"]["ungrounded_count"] == 0
    assert grounded["checks"]["grounding"]["authored_sentences"] == 1


def test_soft_hyphen_artifacts_are_a_hard_failure(tmp_path):
    qa = _evaluate(tmp_path, content=_content(FILLER + " dis­ order."))
    assert qa["source_ready"] is False
    assert qa["checks"]["soft_hyphen_count"] == 1
    assert any("Soft-hyphen" in error for error in qa["errors"])


def test_checklist_rows_in_the_prose_are_a_hard_failure(tmp_path):
    leaked = "Specify the inclusion and exclusion criteria for the review. " + FILLER
    qa = _evaluate(tmp_path, content=_content(leaked))
    assert any("checklist or table row" in error for error in qa["errors"])


def test_a_sentence_repeated_across_sections_is_a_hard_failure(tmp_path):
    repeated = "Accuracy improved from 71.8 percent to 94.1 percent across the nine publishers studied here."
    content = ProfileContent(
        repeated,
        CLASSIFICATION + "\n\n" + FILLER,
        FILLER,
        FILLER,
        repeated + " " + FILLER,
        FILLER,
        FILLER,
        FILLER,
    )
    qa = _evaluate(tmp_path, content=content)
    assert any("repeated across digest sections" in error for error in qa["errors"])


def test_check_registry_reports_a_status_for_every_check(tmp_path):
    qa = _evaluate(tmp_path, content=_content())
    statuses = qa["checks"]["check_status"]
    assert {"schema", "metadata", "authors", "density", "grounding", "coverage", "evidence"} <= set(statuses)
    assert set(statuses.values()) <= {"pass", "fail"}


def test_glossary_source_exhaustion_is_a_warning_not_an_invention_prompt(tmp_path):
    note = "The source states no further defined terms."
    content = _content()
    content.glossary = "\n".join(
        [
            "- **RCT** — randomized controlled trial.",
            "- **CI** — confidence interval.",
            "- **SD** — standard deviation.",
            "- **ITT** — intention to treat.",
            note,
        ]
    )
    qa = _evaluate(tmp_path, content=content, authored=[note])

    assert qa["checks"]["glossary_source_exhausted"] is True
    assert not [error for error in qa["errors"] if "Glossary" in error]
    assert not [error for error in qa["errors"] if "## 7. Glossary" in error]
    assert any("source defines no additional terms" in warning for warning in qa["warnings"])


def test_untrusted_glossary_exhaustion_text_does_not_bypass_the_gate(tmp_path):
    content = _content()
    content.glossary = "- **RCT** — randomized controlled trial.\nThe source states no further defined terms."
    qa = _evaluate(tmp_path, content=content)

    assert qa["checks"]["glossary_source_exhausted"] is False
    assert any("Glossary must contain" in error for error in qa["errors"])


def test_numbered_glossary_placeholder_is_a_hard_failure(tmp_path):
    content = _content()
    content.glossary = "\n".join(
        f"- **Term {index}:** This is extracted prose rather than a semantic glossary term." for index in range(1, 7)
    )
    qa = _evaluate(tmp_path, content=content)

    assert qa["source_ready"] is False
    assert qa["checks"]["glossary_placeholder_labels"] == 6
    assert any("numbered placeholder labels" in error for error in qa["errors"])
