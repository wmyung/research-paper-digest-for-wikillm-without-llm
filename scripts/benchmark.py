#!/usr/bin/env python3
"""Measure digest quality over a corpus, optionally against reference records.

Usage:
    python scripts/benchmark.py PAPERS_DIR [--reference REF_DIR] [--out report.json]
                                [--offline] [--markdown]

``PAPERS_DIR`` holds PDFs. ``REF_DIR`` optionally holds reference Markdown
records (for example ones written with an LLM) named by the same stem or
carrying the same DOI; where a reference is found the report adds agreement
metrics. Nothing here calls a model: the comparison is string and token
arithmetic over two Markdown files.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "paper-digest" / "src"))

from paper_digest.config import DigestConfig  # noqa: E402
from paper_digest.pipeline import digest_files  # noqa: E402

H2_RE = re.compile(r"^## (.+)$", re.M)
NUMBER_RE = re.compile(r"(?<![A-Za-z0-9.-])\d{1,6}(?:\.\d+)?%?(?![A-Za-z0-9])")
TOKEN_RE = re.compile(r"[a-z0-9]+")
STOP = frozenset(
    """a an and are as at be by for from has have in is it its of on or that the their this to was were with""".split()
)


def frontmatter(markdown: str) -> dict[str, str]:
    if not markdown.startswith("---\n"):
        return {}
    end = markdown.find("\n---\n", 4)
    if end < 0:
        return {}
    data: dict[str, str] = {}
    for line in markdown[4:end].splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            data[key.strip()] = value.strip().strip('"')
    return data


def sections(markdown: str) -> dict[str, str]:
    body = markdown.split("\n---\n", 1)[-1]
    parts = H2_RE.split(body)
    return {parts[index].strip(): parts[index + 1].strip() for index in range(1, len(parts) - 1, 2)}


def tokens(text: str) -> set[str]:
    return {token for token in TOKEN_RE.findall(text.casefold()) if token not in STOP and len(token) > 2}


def f1(candidate: set[str], reference: set[str]) -> float:
    if not candidate or not reference:
        return 0.0
    shared = len(candidate & reference)
    if not shared:
        return 0.0
    precision = shared / len(candidate)
    recall = shared / len(reference)
    return 2 * precision * recall / (precision + recall)


def numbers(text: str) -> set[str]:
    return {value for value in NUMBER_RE.findall(text) if not re.fullmatch(r"(?:19|20)\d{2}", value)}


def author_set(value: str) -> set[str]:
    return {part.strip().casefold() for part in value.split(",") if part.strip()}


@dataclass
class PaperReport:
    pdf: str
    status: str = ""
    quality_score: float = 0.0
    document_profile: str = ""
    category: str = ""
    body_words: int = 0
    source_words: int = 0
    digest_to_source_ratio: float = 0.0
    grounded_ratio: float = 0.0
    ungrounded_sentences: int = 0
    coverage_ratio: float = 0.0
    absent_slots: list[str] = field(default_factory=list)
    statistical_anchors: int = 0
    retrieval_passed: int = 0
    retrieval_total: int = 0
    self_contained_units: int = 0
    relational_units: int = 0
    errors: list[str] = field(default_factory=list)
    warnings: int = 0
    reference: str | None = None
    title_exact: bool | None = None
    doi_exact: bool | None = None
    year_exact: bool | None = None
    author_jaccard: float | None = None
    numeric_recall: float | None = None
    section_f1: dict[str, float] | None = None
    mean_section_f1: float | None = None
    failure: str | None = None


def find_reference(pdf: Path, reference_dir: Path | None, doi: str) -> Path | None:
    if reference_dir is None:
        return None
    candidates = sorted(reference_dir.glob("*.md")) + sorted(reference_dir.glob("*.markdown"))
    stem = pdf.stem.casefold()
    for candidate in candidates:
        if candidate.stem.casefold() == stem:
            return candidate
    if doi:
        for candidate in candidates:
            if doi.casefold() in candidate.read_text(encoding="utf-8", errors="replace").casefold():
                return candidate
    return None


def compare(report: PaperReport, produced: str, reference_path: Path) -> None:
    reference = reference_path.read_text(encoding="utf-8", errors="replace")
    ours, theirs = frontmatter(produced), frontmatter(reference)
    report.reference = reference_path.name
    report.title_exact = ours.get("title", "").casefold() == theirs.get("title", "").casefold()
    report.doi_exact = ours.get("doi", "").casefold() == theirs.get("doi", "").casefold()
    report.year_exact = ours.get("year", "") == theirs.get("year", "")
    mine, yours = author_set(ours.get("authors", "")), author_set(theirs.get("authors", ""))
    report.author_jaccard = round(len(mine & yours) / len(mine | yours), 4) if (mine or yours) else None

    reference_numbers = numbers(reference.split("\n---\n", 1)[-1])
    produced_numbers = numbers(produced.split("\n---\n", 1)[-1])
    report.numeric_recall = (
        round(len(reference_numbers & produced_numbers) / len(reference_numbers), 4) if reference_numbers else None
    )

    ours_sections, theirs_sections = sections(produced), sections(reference)
    scores = {
        name: round(f1(tokens(ours_sections.get(name, "")), tokens(body)), 4) for name, body in theirs_sections.items()
    }
    report.section_f1 = scores
    report.mean_section_f1 = round(sum(scores.values()) / len(scores), 4) if scores else None


def run(pdf: Path, config: DigestConfig, reference_dir: Path | None) -> PaperReport:
    report = PaperReport(pdf=pdf.name)
    try:
        result = digest_files([pdf], config)
    except Exception as exc:  # A crash is a benchmark result, not a stop.
        report.failure = f"{type(exc).__name__}: {exc}"
        return report
    qa = result.qa
    checks = qa.get("checks", {})
    grounding = checks.get("grounding", {})
    retrieval = checks.get("retrieval_regression", {})
    report.status = result.status
    report.quality_score = qa.get("quality_score", 0.0)
    report.document_profile = qa.get("document_profile", "")
    report.category = result.metadata.category
    report.body_words = checks.get("body_words", 0)
    report.source_words = checks.get("source_words", 0)
    report.digest_to_source_ratio = checks.get("digest_to_source_ratio", 0.0)
    report.grounded_ratio = grounding.get("ratio", 0.0)
    report.ungrounded_sentences = grounding.get("ungrounded_count", 0)
    report.coverage_ratio = qa.get("coverage_ledger", {}).get("coverage_ratio", 0.0)
    report.absent_slots = qa.get("coverage_ledger", {}).get("absent_required_slots", [])
    report.statistical_anchors = checks.get("statistical_anchor_count", 0)
    report.retrieval_passed = retrieval.get("passed", 0)
    report.retrieval_total = retrieval.get("total", 0)
    report.self_contained_units = checks.get("self_contained_units", 0)
    report.relational_units = checks.get("relational_units", 0)
    report.errors = qa.get("errors", [])
    report.warnings = len(qa.get("warnings", []))
    reference_path = find_reference(pdf, reference_dir, result.metadata.doi)
    if reference_path is not None:
        compare(report, result.markdown, reference_path)
    return report


def summarise(reports: list[PaperReport]) -> dict[str, object]:
    scored = [report for report in reports if report.failure is None]
    compared = [report for report in scored if report.mean_section_f1 is not None]

    def mean(values: list[float]) -> float | None:
        return round(sum(values) / len(values), 4) if values else None

    return {
        "papers": len(reports),
        "failed_to_run": sum(1 for report in reports if report.failure),
        "source_ready": sum(1 for report in scored if report.status == "SOURCE_READY"),
        "mean_quality_score": mean([report.quality_score for report in scored]),
        "mean_grounded_ratio": mean([report.grounded_ratio for report in scored]),
        "papers_with_ungrounded_prose": sum(1 for report in scored if report.ungrounded_sentences),
        "mean_coverage_ratio": mean([report.coverage_ratio for report in scored]),
        "mean_digest_to_source_ratio": mean([report.digest_to_source_ratio for report in scored]),
        "retrieval_full_pass": sum(
            1 for report in scored if report.retrieval_total and report.retrieval_passed == report.retrieval_total
        ),
        "compared_against_reference": len(compared),
        "title_exact_match": sum(1 for report in compared if report.title_exact),
        "doi_exact_match": sum(1 for report in compared if report.doi_exact),
        "mean_author_jaccard": mean(
            [report.author_jaccard for report in compared if report.author_jaccard is not None]
        ),
        "mean_numeric_recall": mean(
            [report.numeric_recall for report in compared if report.numeric_recall is not None]
        ),
        "mean_section_f1": mean([report.mean_section_f1 for report in compared]),
    }


def as_markdown(reports: list[PaperReport], summary: dict[str, object]) -> str:
    lines = [
        "| paper | status | score | grounded | coverage | body words | retrieval | section F1 |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for report in reports:
        retrieval = f"{report.retrieval_passed}/{report.retrieval_total}" if report.retrieval_total else "-"
        section = f"{report.mean_section_f1:.3f}" if report.mean_section_f1 is not None else "-"
        lines.append(
            f"| {report.pdf} | {report.status or 'ERROR'} | {report.quality_score:.2f} | "
            f"{report.grounded_ratio:.3f} | {report.coverage_ratio:.2f} | {report.body_words} | "
            f"{retrieval} | {section} |"
        )
    lines.append("")
    for key, value in summary.items():
        lines.append(f"- **{key}**: {value}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("papers", type=Path, help="Directory of PDFs, or a single PDF.")
    parser.add_argument("--reference", type=Path, default=None, help="Directory of reference Markdown records.")
    parser.add_argument("--out", type=Path, default=None, help="Write the JSON report here.")
    parser.add_argument("--offline", action="store_true", help="Disable the DOI-registry metadata lookup.")
    parser.add_argument("--markdown", action="store_true", help="Print a Markdown table instead of JSON.")
    args = parser.parse_args(argv)

    pdfs = [args.papers] if args.papers.is_file() else sorted(args.papers.glob("*.pdf"))
    if not pdfs:
        parser.error(f"No PDFs found under {args.papers}")
    config = DigestConfig(enable_doi_metadata=not args.offline)
    reports = [run(pdf, config, args.reference) for pdf in pdfs]
    summary = summarise(reports)
    payload = {"summary": summary, "papers": [asdict(report) for report in reports]}
    if args.out:
        args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(as_markdown(reports, summary) if args.markdown else json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if summary["failed_to_run"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
