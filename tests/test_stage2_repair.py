"""Stage-2 diagnosis-driven repair: operators, safety rules, and the loop."""

from __future__ import annotations

from dataclasses import replace

import pytest
from paper_digest import repair as R
from paper_digest.compiler import compile_markdown
from paper_digest.config import DigestConfig
from paper_digest.evidence import metadata_ledger
from paper_digest.pipeline import build_bundle, digest_files
from paper_digest.profiles.classifier import choose_profile
from paper_digest.qa import evaluate_digest
from synthetic import build_pdf

# The source has more quotable Related Work than the selection took, but Stage 1
# claims a sentence for the first target that scores it and never revisits that
# claim, so the section stays under a raised floor across all four passes.
REACHABLE_FLOOR = 240
# At this floor the remaining gap can only be closed with near-duplicate prose,
# which is a repair the loop must decline.
UNREACHABLE_FLOOR = 300


def _floors(**overrides: int) -> dict[str, int]:
    floors = dict(DigestConfig().section_min_words)
    floors.update(overrides)
    return floors


@pytest.fixture(scope="module")
def paper(tmp_path_factory):
    return build_pdf(tmp_path_factory.mktemp("stage2") / "paper.pdf")


def _digest(paper, tmp_path, name: str, **options):
    config = DigestConfig(work_dir=tmp_path / name, enable_doi_metadata=False, **options)
    return digest_files([paper], config)


# --------------------------------------------------------------------------- #
# The score plateau
# --------------------------------------------------------------------------- #


def test_the_published_score_is_clamped_but_the_raw_score_is_reported(paper, tmp_path):
    result = _digest(
        paper,
        tmp_path,
        "clamp",
        enable_stage2=False,
        source_ready_threshold=0.80,
        section_min_words=_floors(related=UNREACHABLE_FLOOR),
    )
    assert result.qa["errors"]
    # Any failing record is pinned to threshold - 0.01, so a benchmark run at
    # threshold 0.80 reports 0.79 for every failing record however far from the
    # gate it actually is. Repair and triage need the unclamped score instead.
    assert result.qa["quality_score"] == 0.79
    assert result.qa["raw_quality_score"] > result.qa["quality_score"]


# --------------------------------------------------------------------------- #
# End to end
# --------------------------------------------------------------------------- #


def test_stage2_certifies_a_record_that_stage1_leaves_failing(paper, tmp_path):
    floors = _floors(related=REACHABLE_FLOOR)
    without = _digest(paper, tmp_path, "off", enable_stage2=False, section_min_words=dict(floors))
    assert without.status == "NOT_SOURCE_READY"
    assert any("underdeveloped" in error for error in without.qa["errors"])
    assert without.qa["stage2"] == {"ran": False, "reason": "disabled"}

    repaired = _digest(paper, tmp_path, "on", enable_stage2=True, section_min_words=dict(floors))
    assert repaired.status == "SOURCE_READY", repaired.qa["errors"]
    assert repaired.qa["errors"] == []
    assert repaired.qa["raw_quality_score"] > without.qa["raw_quality_score"]

    audit = repaired.qa["stage2"]
    assert audit["ran"] is True
    assert "reallocate_units" in audit["operators_accepted"]


def test_stage2_reports_a_partial_repair_without_overstating_it(paper, tmp_path):
    floors = _floors(related=UNREACHABLE_FLOOR)
    without = _digest(paper, tmp_path, "partial-off", enable_stage2=False, section_min_words=dict(floors))
    repaired = _digest(paper, tmp_path, "partial-on", enable_stage2=True, section_min_words=dict(floors))

    assert len(repaired.qa["errors"]) < len(without.qa["errors"])
    # A partial repair must not be dressed up as a certified record.
    assert repaired.status == "NOT_SOURCE_READY"


def test_every_accepted_repair_reduced_errors_and_broke_no_check(paper, tmp_path):
    repaired = _digest(
        paper,
        tmp_path,
        "invariant",
        enable_stage2=True,
        section_min_words=_floors(related=UNREACHABLE_FLOOR),
    )
    trail = repaired.qa["stage2"]["trail"]
    assert trail
    for entry in trail:
        if entry["accepted"]:
            assert entry["errors_after"] <= entry["errors_before"]
            assert entry["raw_score_after"] >= entry["raw_score_before"]
    failing = {name for name, status in repaired.qa["checks"]["check_status"].items() if status == "fail"}
    assert failing <= {"section_density"}


def test_stage2_is_deterministic(paper, tmp_path):
    floors = _floors(related=REACHABLE_FLOOR)
    first = _digest(paper, tmp_path, "det-1", section_min_words=dict(floors))
    second = _digest(paper, tmp_path, "det-2", section_min_words=dict(floors))
    assert first.markdown == second.markdown
    assert first.qa["stage2"]["operators_accepted"] == second.qa["stage2"]["operators_accepted"]


def test_stage2_declines_a_record_below_its_window(paper, tmp_path):
    result = _digest(
        paper,
        tmp_path,
        "window",
        stage2_min_score=0.94,
        section_min_words=_floors(related=REACHABLE_FLOOR),
    )
    assert result.qa["stage2"] == {
        "ran": False,
        "reason": "below-stage2-window",
        "raw_quality_score": result.qa["raw_quality_score"],
    }


def test_a_healthy_record_never_reaches_stage2(paper, tmp_path):
    result = _digest(paper, tmp_path, "healthy")
    assert result.status == "SOURCE_READY"
    assert "stage2" not in result.qa


# --------------------------------------------------------------------------- #
# Regression guard
# --------------------------------------------------------------------------- #


def test_the_guard_ignores_a_changed_measurement_in_the_same_gate():
    before = {
        "errors": ["Section is underdeveloped: ## 6. Related Work has 228 words; minimum is 300."],
        "checks": {"check_status": {"section_density": "fail"}},
    }
    after = {
        "errors": ["Section is underdeveloped: ## 6. Related Work has 280 words; minimum is 300."],
        "checks": {"check_status": {"section_density": "fail"}},
    }
    assert R._new_errors(before, after) == []


def test_the_guard_catches_a_gate_that_was_passing():
    before = {"errors": [], "checks": {"check_status": {"density": "pass", "grounding": "pass"}}}
    after = {
        "errors": ["Body exceeds the hard density limit (6100 words)."],
        "checks": {"check_status": {"density": "fail", "grounding": "pass"}},
    }
    introduced = R._new_errors(before, after)
    assert any("hard density limit" in item for item in introduced)
    assert "check 'density' now fails" in introduced


# --------------------------------------------------------------------------- #
# Operators
# --------------------------------------------------------------------------- #


@pytest.fixture(scope="module")
def state(paper, tmp_path_factory):
    """A real bundle, profile, selection and QA report to drive operators."""
    work = tmp_path_factory.mktemp("stage2-state")
    config = DigestConfig(work_dir=work, enable_doi_metadata=False)
    bundle = build_bundle([paper], config, work / "build")
    profile, scores = choose_profile(bundle, "auto", config=config, repair_pass=0)
    selection = profile.select_all(bundle)
    content = profile.render(bundle, selection)
    markdown, _ = compile_markdown(bundle, content, config)
    qa = evaluate_digest(
        markdown=markdown,
        bundle=bundle,
        profile_name=profile.name,
        profile_scores=scores,
        profile_warnings=content.warnings,
        config=config,
        evidence=content.evidence,
        retrieval_queries=content.retrieval_queries,
        coverage=profile.coverage,
        section_capacity=profile.section_capacity,
        document_profile=bundle.metadata.document_profile,
        metadata_ledger=metadata_ledger(bundle),
        authored=content.authored,
    )
    return bundle, config, profile, selection, qa


def test_drop_leaked_units_removes_soft_hyphen_and_checklist_prose(state):
    bundle, config, profile, selection, qa = state
    amended = {target: list(items) for target, items in selection.items()}
    victim = amended["results"][0]
    amended["results"][0] = replace(victim, text="Specify the inclusion criteria applied to every record.")
    qa = {**qa, "checks": {**qa["checks"], "table_row_leaks": ["Specify the inclusion criteria."]}}

    repaired = R.drop_leaked_units(bundle, config, profile, amended, qa)
    assert repaired is not None
    assert all("Specify the inclusion" not in item.text for item in repaired["results"])


def test_drop_repeated_units_keeps_the_first_claim_only(state):
    bundle, config, profile, selection, qa = state
    amended = {target: list(items) for target, items in selection.items()}
    borrowed = amended["results"][0]
    amended["related"] = amended["related"] + [borrowed]
    qa = {**qa, "checks": {**qa["checks"], "duplicate_audit": {"exact": [], "near": [], "repeated_sentences": 1}}}

    repaired = R.drop_repeated_units(bundle, config, profile, amended, qa)
    assert repaired is not None
    texts = [item.text for items in repaired.values() for item in items]
    assert texts.count(borrowed.text) == 1


def test_drop_ungrounded_units_removes_prose_absent_from_the_source(state):
    bundle, config, profile, selection, qa = state
    amended = {target: list(items) for target, items in selection.items()}
    invented = "The eruption column reached the stratosphere over southern Iceland during the survey window."
    amended["results"] = amended["results"] + [replace(amended["results"][0], text=invented)]
    qa = {**qa, "checks": {**qa["checks"], "grounding": {"ungrounded_count": 1}}}

    repaired = R.drop_ungrounded_units(bundle, config, profile, amended, qa)
    assert repaired is not None
    assert all(invented != item.text for item in repaired["results"])


def test_operators_decline_a_record_with_nothing_to_repair(state):
    bundle, config, profile, selection, qa = state
    for operator in R.OPERATORS:
        assert operator.apply(bundle, config, profile, selection, qa) is None, operator.name
