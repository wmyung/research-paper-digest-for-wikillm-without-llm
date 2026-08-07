from helpers import bundle
from paper_digest.profiles.classifier import choose_profile


def test_universal_profile_classifies_a_method_paper(tmp_path):
    text = "An algorithm benchmark used simulation and a software implementation to evaluate a prediction model."
    b = bundle(tmp_path, text)
    b.metadata.title = "A deterministic benchmark for structured document measurements"
    profile, scores = choose_profile(b)
    assert profile.name == "universal"
    assert b.metadata.category == "method-development"
    assert scores[0].name == "universal"


def test_legacy_generic_alias_routes_to_universal_profile(tmp_path):
    b = bundle(tmp_path, "A cross-sectional survey measured prevalence and outcomes.")
    profile, _ = choose_profile(b, "generic")
    assert profile.name == "universal"
    assert b.metadata.category == "cross-sectional"
