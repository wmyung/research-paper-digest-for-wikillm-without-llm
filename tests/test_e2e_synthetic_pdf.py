"""End-to-end: a synthetic publisher PDF compiles to a certified source record."""

from __future__ import annotations

import json

import pytest
from paper_digest.artifacts import write_artifacts
from paper_digest.compiler import FRONTMATTER_KEYS, REQUIRED_HEADINGS
from paper_digest.config import DigestConfig
from paper_digest.pipeline import digest_files
from synthetic import SyntheticPaper, build_pdf


@pytest.fixture(scope="module")
def digest(tmp_path_factory):
    path = build_pdf(tmp_path_factory.mktemp("e2e") / "paper.pdf")
    return digest_files([path], DigestConfig(enable_doi_metadata=False))


def test_a_well_formed_paper_is_certified(digest):
    assert digest.qa["errors"] == []
    assert digest.status == "SOURCE_READY"
    assert digest.qa["quality_score"] >= digest.qa["threshold"]


def test_output_matches_the_wikillm_markdown_contract(digest):
    lines = digest.markdown.splitlines()
    assert [line for line in lines if line.startswith("## ")] == REQUIRED_HEADINGS
    keys = [line.split(":", 1)[0] for line in lines[1 : lines.index("---", 1)]]
    assert keys == FRONTMATTER_KEYS


def test_every_prose_sentence_is_grounded(digest):
    grounding = digest.qa["checks"]["grounding"]
    assert grounding["checked"] >= 15
    assert grounding["ungrounded_count"] == 0


def test_evidence_and_coverage_ledgers_are_emitted(digest):
    assert digest.qa["metadata_ledger"]
    coverage = digest.qa["coverage_ledger"]
    assert coverage["document_profile"] == "empirical_research"
    assert coverage["slots"]
    assert all(slot["status"] != "unchecked" for slot in coverage["slots"])
    assert any(item["target"] == "results" for item in digest.qa["evidence_ledger"])


def test_retrieval_regression_answers_every_generated_question(digest):
    regression = digest.qa["checks"]["retrieval_regression"]
    assert regression["total"] >= 10
    assert regression["passed"] == regression["total"]


def test_sections_carry_source_content_rather_than_absence_notes(digest):
    for heading in ("## 3. Methodology and Architecture", "## 4. Key Results and Benchmarks"):
        section = digest.markdown.split(heading, 1)[1].split("\n## ", 1)[0]
        assert "The source " not in section, heading


def test_a_cover_sheet_does_not_change_the_record(tmp_path):
    covered = digest_files(
        [build_pdf(tmp_path / "covered.pdf", SyntheticPaper(cover_sheet=True))],
        DigestConfig(enable_doi_metadata=False),
    )
    assert covered.status == "SOURCE_READY"
    assert covered.metadata.title == "Deterministic extraction of structured records from publisher PDFs"
    assert covered.metadata.journal == "Journal of Reproducible Informatics"


def test_artifacts_are_written_as_markdown_plus_a_qa_sidecar(digest, tmp_path):
    markdown_path, qa_path = write_artifacts(digest, tmp_path)
    assert markdown_path.read_text(encoding="utf-8").startswith("---\ntitle:")
    payload = json.loads(qa_path.read_text(encoding="utf-8"))
    assert payload["source_ready"] is True
    assert payload["coverage_ledger"]["slots"]
