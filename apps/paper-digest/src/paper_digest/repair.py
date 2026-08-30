"""Stage-2 diagnosis-driven repair.

Stage 1 (``pipeline.digest_files``) recompiles the whole digest with a larger
evidence budget and never looks at which gate failed, so a record that fails
structurally does not move across its four passes. Stage 2 does the opposite:
it reads the QA report and applies one targeted operator per failing gate.

Operators amend the *selection* — the evidence units chosen per target — and
the digest is then rebuilt from that amended selection by
:meth:`UniversalProfile.render`. Repairing the selection and regenerating
everything downstream keeps the prose, the evidence ledger, the coverage ledger
and the retrieval questions consistent with one another, and every unit stays a
verbatim source span, so the grounding gate cannot be broken by a repair.

Three rules make the loop safe to run unattended:

* **Deterministic.** Every operator is a pure function of the bundle, the
  config, the current selection and the QA report; operators run in a fixed
  order and every internal ordering is total.
* **Regression-safe.** A proposal is discarded if it introduces any error the
  previous artifact did not already have.
* **Monotone.** A proposal is accepted only when it strictly improves
  ``(fewer errors, higher unclamped score, fewer warnings)``, so the loop
  cannot oscillate and stops at a fixpoint.

The published ``quality_score`` is clamped to ``threshold - 0.01`` for every
artifact carrying a hard error, which makes it constant across repairs. Stage 2
ranks on ``raw_quality_score``.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Callable

from .compiler import compile_markdown
from .config import DigestConfig
from .evidence import metadata_ledger
from .grounding import build_index, is_grounded
from .models import ParsedBundle
from .profiles.base import ProfileContent, ProfileScore
from .profiles.universal import BUDGETS, LIMITS, ORDER, RELAXABLE, UniversalProfile
from .qa import (
    PROCESS_MARKERS,
    SECTION_HEADINGS,
    STATISTICAL_ANCHOR_RE,
    TABLE_LEAK_RE,
    evaluate_digest,
)
from .selection import Candidate, score_for, select
from .text import word_count

Selection = dict[str, list[Candidate]]

TARGET_BY_HEADING = {heading: target for target, heading in SECTION_HEADINGS.items()}
# Where a repair may add units. "summary" is a single sentence and "glossary"
# is compiled from the source's own definitions, so neither is refillable.
REFILLABLE = tuple(target for target in ORDER if target != "summary")
BOUNDARY_RE = re.compile(
    r"\b(?:no significant|not significant|did not|does not|no association|null result|failed to|"
    r"was not|were not|cannot|could not|uncertain|limitation)\b",
    re.I,
)
MISSING_TARGET_RE = re.compile(r"No grounded evidence unit was selected for ([a-z]+)\.", re.I)


# --------------------------------------------------------------------------- #
# Selection helpers
# --------------------------------------------------------------------------- #


def _copy(selection: Selection) -> Selection:
    return {target: list(items) for target, items in selection.items()}


def _units(selection: Selection) -> int:
    return sum(len(items) for items in selection.values())


def _taken(selection: Selection, exclude: str) -> list[Candidate]:
    return [item for target, items in selection.items() if target != exclude for item in items]


def _drop(selection: Selection, reject: Callable[[Candidate], bool]) -> Selection:
    return {target: [item for item in items if not reject(item)] for target, items in selection.items()}


def _add(selection: Selection, target: str, fresh: list[Candidate]) -> Selection:
    if not fresh:
        return selection
    existing = {id(item) for item in selection.get(target, [])}
    merged = list(selection.get(target, [])) + [item for item in fresh if id(item) not in existing]
    amended = _copy(selection)
    amended[target] = sorted(merged, key=lambda item: item.order)
    return amended


def _words(items: list[Candidate]) -> int:
    return sum(word_count(item.text) for item in items)


def _headroom(qa: dict[str, Any], config: DigestConfig) -> int:
    body_words = int(qa["checks"].get("body_words", 0))
    ceiling = min(config.target_body_words[1], config.hard_max_body_words - 120)
    return max(0, ceiling - body_words)


def _shortfall_targets(qa: dict[str, Any]) -> list[tuple[str, int]]:
    """Targets QA calls underdeveloped where the source has the words."""
    shortfalls = qa["checks"].get("section_shortfalls") or {}
    output: list[tuple[str, int]] = []
    for heading, detail in shortfalls.items():
        target = TARGET_BY_HEADING.get(heading)
        if target is None or target not in REFILLABLE:
            continue
        floor = int(detail.get("floor", 0))
        capacity = int(detail.get("source_capacity", 0))
        # A shortfall the source cannot fill is a warning, not an error; padding
        # it would mean quoting sentences that are not about this section.
        if capacity >= floor:
            output.append((target, floor))
    return sorted(output)


# --------------------------------------------------------------------------- #
# Repair operators
# --------------------------------------------------------------------------- #


def drop_leaked_units(bundle, config, profile, selection, qa) -> Selection | None:
    """Remove units carrying extraction or checklist artifacts."""
    checks = qa["checks"]
    if not (checks.get("soft_hyphen_count") or checks.get("table_row_leaks") or checks.get("process_markers")):
        return None
    markers = [marker.casefold() for marker in PROCESS_MARKERS]

    def leaked(item: Candidate) -> bool:
        text = item.text
        lower = text.casefold()
        return "\u00ad" in text or bool(TABLE_LEAK_RE.search(text)) or any(marker in lower for marker in markers)

    amended = _drop(selection, leaked)
    return amended if _units(amended) < _units(selection) else None


def drop_repeated_units(bundle, config, profile, selection, qa) -> Selection | None:
    """Keep a repeated sentence only in the first target that claimed it."""
    audit = qa["checks"].get("duplicate_audit") or {}
    if not audit.get("exact") and not audit.get("repeated_sentences"):
        return None
    seen: set[str] = set()
    amended: Selection = {}
    changed = False
    for target in ORDER:
        kept: list[Candidate] = []
        for item in selection.get(target, []):
            key = " ".join(re.findall(r"[a-z0-9]+", item.text.casefold()))
            if key and key in seen:
                changed = True
                continue
            seen.add(key)
            kept.append(item)
        amended[target] = kept
    return amended if changed else None


def drop_ungrounded_units(bundle, config, profile, selection, qa) -> Selection | None:
    """Remove any unit the grounding check cannot match to the source."""
    grounding = qa["checks"].get("grounding") or {}
    if not grounding.get("ungrounded_count"):
        return None
    index = build_index(bundle.grounding_text or bundle.full_text)
    amended = _drop(selection, lambda item: not is_grounded(item.text, index))
    return amended if _units(amended) < _units(selection) else None


def apply_external_repair_plan(bundle, config, profile, selection, qa) -> Selection | None:
    """Apply only grounded candidate IDs from an explicit Luna repair plan.

    Arbitrary prose is impossible here: an assignment must reference a
    candidate emitted by this compiler, match the canonical PDF hash, and
    satisfy the target's deterministic strict/approved-relaxed scoring rule.
    The ordinary Stage-2 regression guard then decides whether the complete
    proposal is an improvement.
    """
    path = config.external_repair_plan
    if path is None:
        return None
    path = path.expanduser().resolve()
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("schema_version") != "luna_repair_plan_v1":
        raise ValueError("external repair plan must use schema_version luna_repair_plan_v1")
    identity = payload.get("identity")
    if not isinstance(identity, dict):
        raise ValueError("external repair plan identity is required")
    canonical = next((item for item in bundle.files if item.role == "canonical-paper"), None)
    expected_sha = canonical.sha256 if canonical else ""
    if not expected_sha or str(identity.get("pdf_sha256") or "").casefold() != expected_sha.casefold():
        raise ValueError("external repair plan PDF SHA-256 does not match the canonical source")
    plan_doi = str(identity.get("doi") or "").strip().casefold()
    if plan_doi and plan_doi != bundle.metadata.doi.strip().casefold():
        raise ValueError("external repair plan DOI does not match the canonical source")
    assignments = payload.get("assignments")
    if not isinstance(assignments, list) or not 1 <= len(assignments) <= 20:
        raise ValueError("external repair plan assignments must contain 1 to 20 items")
    by_id = {f"c{item.order:05d}": item for item in profile.candidates}
    amended = _copy(selection)
    changed = False
    for assignment in assignments:
        if not isinstance(assignment, dict):
            raise ValueError("external repair plan assignment must be an object")
        candidate_id = str(assignment.get("candidate_id") or "")
        target = str(assignment.get("target") or "").casefold()
        mode = str(assignment.get("mode") or "strict").casefold()
        candidate = by_id.get(candidate_id)
        if candidate is None or target not in REFILLABLE:
            raise ValueError(f"invalid external repair assignment: {candidate_id!r} -> {target!r}")
        if target not in profile.document_profile.applicable_targets:
            raise ValueError(f"external repair target is not applicable to this document profile: {target}")
        relaxed = mode == "relaxed"
        if mode not in {"strict", "relaxed"} or (relaxed and target not in RELAXABLE):
            raise ValueError(f"external repair mode is not allowed for target: {target}")
        if score_for(candidate, target, relaxed=relaxed) <= 0.0:
            raise ValueError(f"external repair candidate does not satisfy target rules: {candidate_id} -> {target}")
        for donor in amended:
            amended[donor] = [item for item in amended[donor] if item is not candidate]
        amended = _add(amended, target, [candidate])
        changed = True
    return amended if changed and amended != selection else None


def refill_sections(bundle, config, profile, selection, qa) -> Selection | None:
    """Re-select for each underdeveloped section the source can still fill.

    Stage 1 already backfills against the section floors, but blindly and
    before QA runs. Here the failing section is named, so the retry is spent
    only where it is needed and with a budget derived from that floor.
    """
    targets = _shortfall_targets(qa)
    if not targets:
        return None
    candidates = profile.candidates
    if not candidates:
        return None
    amended = _copy(selection)
    changed = False
    for target, floor in targets:
        current = amended.get(target, [])
        deficit = floor - _words(current)
        if deficit <= 0:
            continue
        fresh = select(
            candidates,
            target,
            budget=int(max(BUDGETS.get(target, floor), floor * 2.5)),
            limit=LIMITS.get(target, 8) * 2,
            taken=_taken(amended, target),
            # Stage 1 rejects a candidate that overlaps an already-taken unit by
            # 0.55. For a section that is failing its floor a partly overlapping
            # sentence is still better than a missing one, so the bar is lowered
            # to just under the 0.78 the near-duplicate audit reports on.
            redundancy=0.72,
            relaxed=target in RELAXABLE,
        )
        chosen = [item for item in fresh if all(item.text != other.text for other in current)]
        if not chosen:
            continue
        amended = _add(amended, target, chosen)
        changed = True
    return amended if changed else None


def fill_missing_targets(bundle, config, profile, selection, qa) -> Selection | None:
    """Fill an explicitly empty applicable target before density repair.

    Empty sections used to be visible only as a generic supplement/profile
    warning. This operator turns that exact diagnosis into a bounded selection
    retry. It first uses an unclaimed cue-matching unit, then (only for the
    already-approved RELAXABLE targets) a section-grounded relaxed unit. As a
    last resort it moves a valid unit from a donor that remains above its own
    floor; the normal Stage-2 regression guard rejects any harmful move.
    """
    missing = {
        match.group(1).casefold() for error in qa.get("errors", []) if (match := MISSING_TARGET_RE.search(error))
    }
    targets = [target for target in ORDER if target in missing and target in REFILLABLE]
    if not targets or not profile.candidates:
        return None
    amended = _copy(selection)
    changed = False
    for target in targets:
        if amended.get(target):
            continue
        kwargs = {
            "budget": BUDGETS.get(target, 300),
            "limit": max(1, min(3, LIMITS.get(target, 3))),
            "taken": _taken(amended, target),
            "redundancy": 0.72,
        }
        fresh = select(profile.candidates, target, **kwargs)
        if not fresh and target in RELAXABLE:
            fresh = select(profile.candidates, target, relaxed=True, **kwargs)
        if fresh:
            amended = _add(amended, target, fresh)
            changed = True
            continue

        floors = config.section_min_words
        moves: list[tuple[float, int, str, Candidate]] = []
        for donor, items in amended.items():
            if donor == target or donor not in REFILLABLE:
                continue
            for item in items:
                gain = score_for(item, target, relaxed=target in RELAXABLE)
                if gain <= 0.0:
                    continue
                loss = score_for(item, donor, relaxed=donor in RELAXABLE)
                moves.append((loss - gain, item.order, donor, item))
        for _cost, _order, donor, item in sorted(moves, key=lambda value: (value[0], value[1], value[2])):
            if _words(amended[donor]) - word_count(item.text) < floors.get(donor, 0):
                continue
            amended[donor] = [other for other in amended[donor] if other is not item]
            amended = _add(amended, target, [item])
            changed = True
            break
    return amended if changed else None


def reallocate_units(bundle, config, profile, selection, qa) -> Selection | None:
    """Move a unit to a section that needs it from one that can spare it.

    Stage 1 fills targets in a fixed order and the first target to claim a
    sentence keeps it, so a later section can stay under its floor while an
    earlier one sits well above its own. That claim is irrevocable in Stage 1
    and is what leaves a shortfall standing after four passes. A unit only
    moves when it scores for the receiving target on that target's own rules,
    and only when the donor stays above its floor without it.
    """
    targets = _shortfall_targets(qa)
    if not targets:
        return None
    floors = config.section_min_words
    amended = _copy(selection)
    changed = False
    for target, floor in targets:
        deficit = floor - _words(amended.get(target, []))
        if deficit <= 0:
            continue
        held = {id(item) for item in amended.get(target, [])}
        moves: list[tuple[float, int, str, Candidate]] = []
        for donor, items in amended.items():
            if donor == target or donor not in REFILLABLE:
                continue
            for item in items:
                if id(item) in held:
                    continue
                gain = score_for(item, target, relaxed=target in RELAXABLE)
                if gain <= 0.0:
                    continue
                loss = score_for(item, donor, relaxed=donor in RELAXABLE)
                moves.append((loss - gain, item.order, donor, item))
        for _cost, _order, donor, item in sorted(moves, key=lambda move: (move[0], move[1], move[2])):
            if deficit <= 0:
                break
            size = word_count(item.text)
            if _words(amended[donor]) - size < floors.get(donor, 0):
                continue
            amended[donor] = [other for other in amended[donor] if other is not item]
            amended = _add(amended, target, [item])
            deficit -= size
            changed = True
    return amended if changed else None


def fix_contribution_items(bundle, config, profile, selection, qa) -> Selection | None:
    """Bring Key Contributions inside its required item band."""
    count = int(qa["checks"].get("contribution_items", 0))
    minimum = config.min_contribution_items
    maximum = config.max_contribution_items
    if minimum <= count <= maximum:
        return None
    current = list(selection.get("contributions", []))
    if count > maximum:
        keep = sorted(current, key=lambda item: -score_for(item, "contributions"))[:maximum]
        amended = _copy(selection)
        amended["contributions"] = sorted(keep, key=lambda item: item.order)
        return amended if len(keep) != len(current) else None
    candidates = profile.candidates
    if not candidates:
        return None
    fresh = select(
        candidates,
        "results",
        budget=BUDGETS.get("contributions", 460),
        limit=minimum - count + 2,
        taken=_taken(selection, "contributions"),
    )
    chosen = [item for item in fresh if all(item.text != other.text for other in current)]
    return _add(selection, "contributions", chosen) if chosen else None


def add_quantitative_anchors(bundle, config, profile, selection, qa) -> Selection | None:
    """Recover effect sizes and test statistics the selection left behind."""
    components = qa["checks"].get("score_components") or {}
    anchor_error = any("anchors were preserved" in error for error in qa["errors"])
    if not anchor_error and components.get("quantitative", 0.0) >= 1.0:
        return None
    headroom = _headroom(qa, config)
    if headroom < 40:
        return None
    present = {item.text for items in selection.values() for item in items}
    pool = [item for item in profile.candidates if item.text not in present and STATISTICAL_ANCHOR_RE.search(item.text)]
    if not pool:
        return None
    amended = selection
    spent = 0
    added = 0
    for item in sorted(pool, key=lambda value: (-score_for(value, "results"), value.order)):
        size = word_count(item.text)
        if spent + size > headroom:
            continue
        target = "results" if score_for(item, "results") > 0.0 else "methods"
        amended = _add(amended, target, [item])
        spent += size
        added += 1
        if added >= 6:
            break
    return amended if added else None


def add_boundary_statement(bundle, config, profile, selection, qa) -> Selection | None:
    """Reinstate a source-stated null, uncertainty or boundary sentence."""
    if qa["checks"].get("quantitative_boundary_statement", True):
        return None
    present = {item.text for items in selection.values() for item in items}
    pool = [item for item in profile.candidates if item.text not in present and BOUNDARY_RE.search(item.text)]
    if not pool:
        return None
    best = min(pool, key=lambda item: (-score_for(item, "limitations"), item.order))
    target = "limitations" if score_for(best, "limitations") > 0.0 else "results"
    return _add(selection, target, [best])


def trim_density(bundle, config, profile, selection, qa) -> Selection | None:
    """Drop the weakest units from the largest section when the body is too long."""
    checks = qa["checks"]
    over_body = int(checks.get("body_words", 0)) > config.hard_max_body_words
    over_unit = int(checks.get("longest_prose_unit_words", 0)) > config.paragraph_hard_max_words
    if not over_body and not over_unit:
        return None
    floors = config.section_min_words
    amended = _copy(selection)
    excess = max(0, int(checks.get("body_words", 0)) - config.target_body_words[1])
    removed = 0
    for target, _size in sorted(
        ((target, _words(items)) for target, items in amended.items() if target in REFILLABLE),
        key=lambda pair: (-pair[1], pair[0]),
    ):
        floor = floors.get(target, 0)
        items = amended[target]
        ranked = sorted(items, key=lambda item: (score_for(item, target), -item.order))
        for item in ranked:
            if removed >= excess and not over_unit:
                break
            if _words(items) - word_count(item.text) < floor:
                break
            items = [other for other in items if other is not item]
            removed += word_count(item.text)
        if len(items) != len(amended[target]):
            amended[target] = items
    return amended if _units(amended) < _units(selection) else None


def repair_retrieval(bundle, config, profile, selection, qa) -> Selection | None:
    """Promote a source sentence that answers a failing research question.

    The questions are regenerated from the selection on every render, so a
    failure means the digest no longer carries the evidence its own question
    set was built from. The repair restores that evidence rather than editing
    the question.
    """
    regression = qa["checks"].get("retrieval_regression")
    if not regression or regression["passed"] == regression["total"]:
        return None
    present = {item.text for items in selection.values() for item in items}
    amended = selection
    changed = False
    for failure in regression["results"]:
        if failure["passed"]:
            continue
        query_id = str(failure.get("id"))
        # publication and authorship questions are answered from metadata, not
        # from selected evidence, so no selection change can repair them.
        target = query_id if query_id in REFILLABLE else ("results" if query_id.startswith("evidence-") else "")
        if not target:
            continue
        terms = [str(term) for term in failure.get("expected_terms", []) if str(term).strip()]
        if not terms:
            continue
        term = terms[0]
        pool = [
            item
            for item in profile.candidates
            if item.text not in present and term in item.text.casefold() and score_for(item, target) > 0.0
        ]
        if not pool:
            continue
        best = min(pool, key=lambda item: (-score_for(item, target), item.order))
        amended = _add(amended, target, [best])
        present.add(best.text)
        changed = True
    return amended if changed else None


@dataclass(frozen=True, slots=True)
class RepairOperator:
    name: str
    gate: str
    apply: Callable[..., Selection | None]


# Removals run before additions: a leaked or repeated unit should not be
# counted as section content that a refill then decides is sufficient.
OPERATORS: tuple[RepairOperator, ...] = (
    RepairOperator(
        "apply_external_repair_plan", "validated grounded candidate assignments", apply_external_repair_plan
    ),
    RepairOperator("drop_leaked_units", "extraction and checklist artifacts", drop_leaked_units),
    RepairOperator("drop_repeated_units", "cross-section duplication", drop_repeated_units),
    RepairOperator("drop_ungrounded_units", "verbatim grounding", drop_ungrounded_units),
    RepairOperator("fill_missing_targets", "empty applicable digest section", fill_missing_targets),
    RepairOperator("refill_sections", "section density floors", refill_sections),
    RepairOperator("reallocate_units", "section density floors", reallocate_units),
    RepairOperator("fix_contribution_items", "key-contribution item band", fix_contribution_items),
    RepairOperator("add_quantitative_anchors", "quantitative anchor density", add_quantitative_anchors),
    RepairOperator("add_boundary_statement", "null or boundary statement", add_boundary_statement),
    RepairOperator("trim_density", "body and prose-unit limits", trim_density),
    RepairOperator("repair_retrieval", "full-question retrieval regression", repair_retrieval),
)


# --------------------------------------------------------------------------- #
# Control loop
# --------------------------------------------------------------------------- #


@dataclass(slots=True)
class RepairCandidate:
    selection: Selection
    content: ProfileContent
    markdown: str
    filename: str
    qa: dict[str, Any]


def _rank(qa: dict[str, Any]) -> tuple[int, float, int]:
    return (
        -len(qa["errors"]),
        float(qa.get("raw_quality_score", qa["quality_score"])),
        -len(qa["warnings"]),
    )


MEASUREMENT_RE = re.compile(r"\d+(?:\.\d+)?")


def _error_key(error: str) -> str:
    """Identify an error by its gate, not by the measurement it quotes.

    Several gates name their own numbers ("has 328 words; minimum is 400"), so
    comparing raw strings would read a partial repair of the same gate as a
    brand-new failure and reject it.
    """
    return MEASUREMENT_RE.sub("#", error)


def _failing_checks(qa: dict[str, Any]) -> set[str]:
    return {name for name, status in (qa["checks"].get("check_status") or {}).items() if status == "fail"}


def _new_errors(before: dict[str, Any], after: dict[str, Any]) -> list[str]:
    """Errors and checks that the proposal introduced, in the source wording."""
    known = {_error_key(error) for error in before["errors"]}
    introduced = [error for error in after["errors"] if _error_key(error) not in known]
    broken = sorted(_failing_checks(after) - _failing_checks(before))
    return sorted(introduced) + [f"check '{name}' now fails" for name in broken]


def repair_digest(
    *,
    bundle: ParsedBundle,
    config: DigestConfig,
    profile: UniversalProfile,
    profile_scores: list[ProfileScore],
    selection: Selection,
    content: ProfileContent,
    markdown: str,
    filename: str,
    qa: dict[str, Any],
) -> RepairCandidate | None:
    """Run the Stage-2 loop and return an improved candidate, or None."""

    def evaluate(proposal: Selection) -> RepairCandidate:
        rebuilt = profile.render(bundle, proposal)
        rendered, name = compile_markdown(bundle, rebuilt, config)
        report = evaluate_digest(
            markdown=rendered,
            bundle=bundle,
            profile_name=profile.name,
            profile_scores=profile_scores,
            profile_warnings=rebuilt.warnings,
            config=config,
            evidence=rebuilt.evidence,
            retrieval_queries=rebuilt.retrieval_queries,
            coverage=profile.coverage,
            section_capacity=profile.section_capacity,
            document_profile=bundle.metadata.document_profile,
            metadata_ledger=metadata_ledger(bundle),
            authored=rebuilt.authored,
        )
        return RepairCandidate(proposal, rebuilt, rendered, name, report)

    baseline = _rank(qa)
    current = RepairCandidate(selection, content, markdown, filename, qa)
    trail: list[dict[str, Any]] = []
    rounds = 0

    def judge(label: str, gate: str, round_index: int, candidate: RepairCandidate) -> bool:
        entry: dict[str, Any] = {
            "round": round_index,
            "operator": label,
            "gate": gate,
            "errors_before": len(current.qa["errors"]),
            "errors_after": len(candidate.qa["errors"]),
            "raw_score_before": current.qa.get("raw_quality_score"),
            "raw_score_after": candidate.qa.get("raw_quality_score"),
        }
        regressions = _new_errors(current.qa, candidate.qa)
        if regressions:
            trail.append({**entry, "accepted": False, "reason": "regression", "new_errors": regressions})
            return False
        if _rank(candidate.qa) <= _rank(current.qa):
            trail.append({**entry, "accepted": False, "reason": "no-improvement"})
            return False
        trail.append({**entry, "accepted": True, "reason": "improved"})
        return True

    for round_index in range(1, config.stage2_max_rounds + 1):
        rounds = round_index
        improved = False
        blocked: list[tuple[RepairOperator, RepairCandidate]] = []
        for operator in OPERATORS:
            proposal = operator.apply(bundle, config, profile, current.selection, current.qa)
            if proposal is None:
                continue
            candidate = evaluate(proposal)
            if judge(operator.name, operator.gate, round_index, candidate):
                current = candidate
                improved = True
                if current.qa["source_ready"]:
                    break
            elif _new_errors(current.qa, candidate.qa):
                blocked.append((operator, candidate))
        # Some repairs are only worth making together: filling a thin section
        # can push the body over its density limit until the trim runs too.
        # Single-step hill climbing stalls there, so each blocked operator is
        # retried paired with one follow-up and the pair is judged as one move.
        if not improved and not current.qa["source_ready"]:
            for first, interim in blocked:
                for second in OPERATORS:
                    if second.name == first.name:
                        continue
                    proposal = second.apply(bundle, config, profile, interim.selection, interim.qa)
                    if proposal is None:
                        continue
                    candidate = evaluate(proposal)
                    if judge(f"{first.name}+{second.name}", f"{first.gate} + {second.gate}", round_index, candidate):
                        current = candidate
                        improved = True
                        break
                if improved:
                    break
        if current.qa["source_ready"] or not improved:
            break

    accepted = [entry for entry in trail if entry["accepted"]]
    current.qa["stage2"] = {
        "ran": True,
        "rounds": rounds,
        "max_rounds": config.stage2_max_rounds,
        "operators_accepted": [entry["operator"] for entry in accepted],
        "raw_score_before": qa.get("raw_quality_score"),
        "raw_score_after": current.qa.get("raw_quality_score"),
        "errors_before": len(qa["errors"]),
        "errors_after": len(current.qa["errors"]),
        "trail": trail,
    }
    if not accepted or _rank(current.qa) <= baseline:
        return None
    return current
