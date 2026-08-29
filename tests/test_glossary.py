"""Glossary construction."""

from __future__ import annotations

from paper_digest.glossary import acronym_pairs, build, stated_definitions


def test_acronyms_are_expanded_only_when_the_source_states_the_expansion():
    text = (
        "We used an Interferon Gamma Release Assay (IGRA) and a tuberculin skin test (TST). "
        "The QFT assay (XYZ) was unrelated to the preceding words."
    )
    pairs = dict(acronym_pairs(text))
    assert pairs["IGRA"] == "Interferon Gamma Release Assay"
    assert pairs["TST"] == "tuberculin skin test"
    assert "XYZ" not in pairs


def test_glossary_box_definitions_stop_at_the_next_term():
    text = (
        "Systematic review — A review that uses explicit, systematic methods to collate findings [43] "
        "Statistical synthesis — The combination of quantitative results of two or more studies."
    )
    definitions = dict(stated_definitions(text))
    assert definitions["Systematic review"] == ("A review that uses explicit, systematic methods to collate findings")
    assert definitions["Statistical synthesis"].startswith("The combination of quantitative results")


def test_no_filler_glosses_are_invented_when_the_source_defines_nothing():
    body, authored = build("The study measured outcomes across nine publishers.", ["retrieval", "accuracy"])
    assert "deterministically selected indexing term" not in body
    assert authored and authored[0] in body
    assert "retrieval" in body


def test_real_definitions_are_emitted_without_a_fallback_note():
    text = (
        "We used an Interferon Gamma Release Assay (IGRA), a tuberculin skin test (TST), "
        "a chest X-ray (CXR) and a Public Health Service (PHS) register."
    )
    body, authored = build(text, ["tuberculosis"])
    assert authored == []
    assert body.count("- **") == 4
