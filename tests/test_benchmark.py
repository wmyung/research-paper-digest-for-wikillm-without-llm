"""The benchmark harness: reference comparison and artifact schemas."""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
from pathlib import Path

import pytest
from paper_digest.artifacts import write_artifacts
from paper_digest.config import DigestConfig
from paper_digest.pipeline import digest_files
from synthetic import build_pdf

ROOT = Path(__file__).resolve().parents[1]


def _benchmark_module():
    spec = importlib.util.spec_from_file_location("paper_digest_benchmark", ROOT / "scripts" / "benchmark.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # dataclasses resolves annotations through sys.modules, so register first.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def benchmark():
    return _benchmark_module()


@pytest.fixture(scope="module")
def digest(tmp_path_factory):
    path = build_pdf(tmp_path_factory.mktemp("bench") / "paper.pdf")
    return digest_files([path], DigestConfig(enable_doi_metadata=False))


def test_a_record_compared_against_itself_agrees_completely(benchmark, digest):
    report = benchmark.PaperReport(pdf="paper.pdf")
    directory = Path(tempfile.mkdtemp())
    reference_path = directory / "reference.md"
    reference_path.write_text(digest.markdown, encoding="utf-8")
    benchmark.compare(report, digest.markdown, reference_path)
    assert report.title_exact is True
    assert report.doi_exact is True
    assert report.year_exact is True
    assert report.author_jaccard == 1.0
    assert report.numeric_recall == 1.0
    assert report.mean_section_f1 == 1.0


def test_a_different_record_does_not_agree(benchmark, digest):
    directory = Path(tempfile.mkdtemp())
    reference_path = directory / "reference.md"
    reference_path.write_text(
        '---\ntitle: "A completely different paper"\nauthors: Someone Else\n'
        "year: 1999\ndoi: 10.9999/other\n---\n\n"
        "## 4. Key Results and Benchmarks\n\nAn unrelated claim about 12345 unrelated units.\n",
        encoding="utf-8",
    )
    report = benchmark.PaperReport(pdf="paper.pdf")
    benchmark.compare(report, digest.markdown, reference_path)
    assert report.title_exact is False
    assert report.doi_exact is False
    assert report.author_jaccard == 0.0
    assert report.mean_section_f1 is not None and report.mean_section_f1 < 0.2


def test_summary_reports_grounding_and_certification(benchmark, digest):
    report = benchmark.PaperReport(
        pdf="paper.pdf",
        status="SOURCE_READY",
        quality_score=1.0,
        grounded_ratio=1.0,
        coverage_ratio=1.0,
        retrieval_passed=10,
        retrieval_total=10,
    )
    summary = benchmark.summarise([report])
    assert summary["source_ready"] == 1
    assert summary["papers_with_ungrounded_prose"] == 0
    assert summary["retrieval_full_pass"] == 1
    assert "| paper | status |" in benchmark.as_markdown([report], summary)


def test_written_ledgers_match_their_schemas(digest, tmp_path):
    paths = write_artifacts(digest, tmp_path)
    metadata = json.loads(paths.metadata_evidence.read_text(encoding="utf-8"))
    coverage = json.loads(paths.evidence_coverage.read_text(encoding="utf-8"))

    assert metadata["schema_version"] == "2.0"
    assert metadata["pdf_filename"].endswith(".pdf")
    for entry in metadata["fields"]:
        assert set(entry) == {"field", "value", "source", "page", "source_excerpt"}
        assert entry["value"] and entry["source"]

    assert coverage["schema_version"] == "2.0"
    assert coverage["unchecked_slots"] == []
    assert coverage["covered_slots"] <= coverage["applicable_slots"]
    assert 0.0 <= coverage["coverage_ratio"] <= 1.0
    for slot in coverage["slots"]:
        assert slot["status"] in {"covered", "absent_in_source", "not_applicable"}
        if slot["status"] == "covered":
            assert slot["evidence_locations"]
