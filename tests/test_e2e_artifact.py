from helpers import bundle
from paper_digest.compiler import REQUIRED_HEADINGS, compile_markdown
from paper_digest.config import DigestConfig
from paper_digest.models import Paragraph, Section
from paper_digest.profiles.universal import UniversalProfile


def test_synthetic_universal_digest_has_contract_and_retrieval_questions(tmp_path):
    b = bundle(tmp_path)
    section_text = {
        "Abstract": "The objective was to evaluate a deterministic measurement pipeline using a synthetic validation dataset.",
        "Introduction": "Previous document methods reported inconsistent structure, and this study compared a reproducible alternative.",
        "Methods": "The analysis included 240 synthetic records, measured three outcomes, adjusted for two covariates, and used a prespecified regression model.",
        "Results": "The primary result showed 92.4% agreement, while the secondary contrast was not significant at P = 0.18.",
        "Discussion": "The findings were consistent with prior benchmark reports but showed improved retrieval precision in the current evaluation.",
        "Limitations": "A limitation is that synthetic inputs may not generalize to every publisher layout, so further validation is required.",
    }
    b.sections = {}
    texts: list[str] = []
    details = [
        "manual annotation established the reference labels before analysis",
        "a frozen protocol defined exclusions and missing-value handling",
        "two independent checks reconciled discordant structured fields",
        "bootstrap intervals quantified sampling uncertainty around each estimate",
        "held-out records measured transport without parameter refitting",
        "sensitivity analysis changed the threshold under a fixed rule",
        "error categories separated omissions substitutions and ordering defects",
        "the archived configuration preserved exact reproducibility metadata",
    ]
    page = 1
    for name, sentence in section_text.items():
        paragraphs = []
        for index, detail in enumerate(details, start=1):
            text = f"{sentence.rstrip('.')} In evaluation unit {index}, {detail}, with source-grounded evidence retained for audit."
            texts.append(text)
            paragraphs.append(Paragraph(text, name, page, page, "synthetic.pdf"))
            page += 1
        b.sections[name] = Section(name, paragraphs)
    b.full_text = "\n".join(texts)
    profile = UniversalProfile(DigestConfig(enable_doi_metadata=False))
    profile.classify(b)
    content = profile.compile(b)
    markdown, filename = compile_markdown(b, content, DigestConfig(extracted_date="2026-08-07"))

    assert filename.endswith(".md")
    assert [line for line in markdown.splitlines() if line.startswith("## ")] == REQUIRED_HEADINGS
    assert len(content.evidence) >= 12
    assert len(content.retrieval_queries) >= 10
    assert content.warnings == []
