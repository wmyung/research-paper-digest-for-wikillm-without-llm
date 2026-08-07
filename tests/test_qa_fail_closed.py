from helpers import bundle
from paper_digest.compiler import compile_markdown
from paper_digest.config import DigestConfig
from paper_digest.profiles.base import ProfileContent, ProfileScore
from paper_digest.qa import evaluate_digest


def test_digest_without_page_grounded_evidence_is_not_certified(tmp_path):
    b = bundle(tmp_path)
    classification = """### Classification metadata

- **Journal:** *Test Journal*
- **Publication date:** Published online January 2, 2024
- **Article type:** Article
- **Author count:** 2
- **Author notes:** No special authorship roles were stated in the supplied paper.
- **Research fields (editorial):** statistical genetics; population genomics
- **Index keywords (editorial):** genetics; cohort; association; prediction; replication; methods
"""
    long = " ".join(["N = 100 and P = 0.01 was not significant. Limitations Related Work Glossary evidence"] * 220)
    content = ProfileContent(long, classification + "\n\n" + long, long, long, long, long, long, long)
    markdown, _ = compile_markdown(b, content, DigestConfig(extracted_date="2026-08-07"))
    qa = evaluate_digest(markdown, b, "universal", [ProfileScore("universal", "other", 0.75)], [], DigestConfig())
    assert qa["source_ready"] is False
    assert qa["quality_score"] < qa["threshold"]
    assert any("page-grounded evidence" in error for error in qa["errors"])
