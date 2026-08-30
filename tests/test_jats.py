"""JATS structure recovery remains verbatim-grounded in the canonical PDF."""

from __future__ import annotations

from xml.sax.saxutils import escape

import pytest
from paper_digest.config import DigestConfig
from paper_digest.parsers.jats import extract_jats
from paper_digest.pipeline import build_bundle
from synthetic import SyntheticPaper, build_pdf


def _jats(paper: SyntheticPaper) -> str:
    abstract = "".join(
        f"<sec><title>{escape(label)}</title><p>{escape(text)}</p></sec>" for label, text in paper.abstract
    )
    sections = "".join(
        f"<sec><title>{escape(title)}</title>{''.join(f'<p>{escape(text)}</p>' for text in paragraphs)}</sec>"
        for title, paragraphs in paper.sections
    )
    return f'<article article-type="research-article"><front><abstract>{abstract}</abstract></front><body>{sections}</body></article>'


def test_jats_keeps_only_sentences_that_are_verifiable_on_a_pdf_page(tmp_path):
    sentence = "Field accuracy increased from 71.8% to 94.1% after layout recovery was applied."
    invented = "The intervention reduced mortality by exactly 63.4% in every participating hospital."
    path = tmp_path / "fulltext.xml"
    path.write_text(
        f"<article><body><sec><title>Results</title><p>{sentence} {invented}</p></sec></body></article>",
        encoding="utf-8",
    )

    extraction = extract_jats(path, [sentence], "paper.pdf")

    assert extraction.aligned_sentences == 1
    assert extraction.total_sentences == 2
    assert sentence in extraction.full_text
    assert invented not in extraction.full_text
    assert all(block.source_file == "paper.pdf" for block in extraction.blocks)


def test_jats_rejects_dtd_and_entity_declarations(tmp_path):
    path = tmp_path / "unsafe.xml"
    path.write_text(
        '<!DOCTYPE article [<!ENTITY xxe SYSTEM "file:///etc/passwd">]><article><body><p>&xxe;</p></body></article>',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="Entity declarations"):
        extract_jats(path, ["source"], "paper.pdf")


def test_standard_external_jats_doctype_is_safe_without_entity_declarations(tmp_path):
    sentence = "The study measured reproducible extraction accuracy in four hundred records."
    path = tmp_path / "doctype.xml"
    path.write_text(
        '<!DOCTYPE article PUBLIC "-//NLM//DTD JATS 1.3//EN" "JATS-journalpublishing1-3.dtd">'
        f"<article><body><sec><title>Methods</title><p>{sentence}</p></sec></body></article>",
        encoding="utf-8",
    )
    extraction = extract_jats(path, [sentence], "paper.pdf")
    assert extraction.aligned_sentences == 1


def test_pipeline_uses_high_alignment_jats_for_structure_without_changing_pdf_grounding(tmp_path):
    paper = SyntheticPaper()
    pdf = build_pdf(tmp_path / "paper.pdf", paper)
    xml = tmp_path / "fulltext.xml"
    xml.write_text(_jats(paper), encoding="utf-8")
    config = DigestConfig(
        work_dir=tmp_path / "work",
        enable_doi_metadata=False,
        jats_min_aligned_sentences=5,
        jats_min_alignment_ratio=0.5,
        min_body_words=6000,
        target_body_words=(6000, 7000),
        hard_max_body_words=8000,
    )

    bundle = build_bundle([pdf, xml], config, tmp_path / "build")

    assert bundle.structured_source["mode"] == "jats-xml-aligned-to-pdf"
    assert bundle.structured_source["selected"] is True
    assert {"Methods", "Results", "Discussion"} <= set(bundle.sections)
    assert bundle.grounding_text
    assert "jats-xml-aligned-to-pdf" in bundle.parser_notes
