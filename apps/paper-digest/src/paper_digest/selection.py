"""Evidence-unit selection.

Candidate sentences are built from the prose sections, scored per digest target
from the deterministic features in :mod:`features` plus a stdlib LexRank
centrality signal, then chosen with maximal-marginal-relevance so that the
sections of the digest do not repeat one another. Every selected unit is a
verbatim (lightly normalised) span of the source, which is what makes the
grounding check in :mod:`grounding` decidable.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass, field

from . import features as F
from .models import ParsedBundle
from .sections import NON_SCIENTIFIC
from .text import has_finite_verb, normalize_prose, split_sentences, word_count

TARGETS = ("summary", "limitations", "contributions", "results", "methods", "related", "information")

LEADING_NOISE_RE = re.compile(
    r"^(?:\[[0-9][0-9,\s–-]*\]|\(\.{2,}\)|\(\s*\)|[•▪◦·\-–—]\s*|\d+[.)]\s+(?=[A-Z])|"
    r"\([^()]{2,70}\)\s*(?=[A-Z])|"
    r"(?:background|objectives?|methods?|results?|conclusions?|limitations?|findings?|"
    r"interpretation|significance|importance)\s*[::.-]\s+)",
    re.I,
)
INLINE_DISPLAY_RE = re.compile(
    r"\s*[(\[]\s*(?:see\s+)?(?:Fig(?:ure)?\.?\s*\d+[a-z]?|Table\s*\d+[a-z]?|Box\s*\d+)\s*[)\]]",
    re.I,
)
TRAILING_DISPLAY_RE = re.compile(
    r"\s*[(\[]?\s*(?:see\s+)?(?:Fig(?:ure)?\.?\s*\d+[a-z]?|Table\s*\d+[a-z]?|Box\s*\d+)\s*[)\]]?\s*\.?$",
    re.I,
)
SENTENCE_START_RE = re.compile(r"^[A-Z0-9(\[“]")
SENTENCE_END_RE = re.compile(r"[.!?][)\]\"'’”]*$")
TOKEN_RE = re.compile(r"[a-z0-9]+")
STOPWORDS = frozenset(
    """a an and are as at be been but by can could did do does for from had has have how in into is it its
    may might not of on or our ours than that the their them there these they this those to was we were what
    when where which who will with would""".split()
)


@dataclass(slots=True)
class Candidate:
    text: str
    section: str
    subsection: str | None
    page_start: int
    page_end: int
    source_file: str
    order: int
    paragraph: int
    features: F.SentenceFeatures
    tokens: set[str] = field(default_factory=set)
    centrality: float = 0.0
    # How far through its own section the sentence sits, in [0, 1]. Authors put
    # their limitations at the end of the Discussion.
    section_position: float = 0.0
    score: float = 0.0


@dataclass(slots=True)
class TargetSpec:
    primary_sections: frozenset[str]
    allowed_sections: frozenset[str]
    weights: dict[str, float]
    require: tuple[str, ...] = ()
    penalise: dict[str, float] = field(default_factory=dict)
    # Papers that do not use IMRaD headings still label their structure in
    # sub-headings; a matching sub-heading counts as a primary section.
    subsection_pattern: str | None = None
    min_words: int = 10
    max_words: int = 80


# Section priors and feature weights per digest target. Weights are on the
# feature names of features.SentenceFeatures.
SPECS: dict[str, TargetSpec] = {
    "summary": TargetSpec(
        primary_sections=frozenset({"Abstract", "Conclusion"}),
        allowed_sections=frozenset({"Abstract", "Conclusion", "Discussion"}),
        weights={"relational_score": 1.0, "has_effect": 1.2, "has_novelty": 1.0, "has_direction": 0.6},
        min_words=12,
        max_words=70,
    ),
    "information": TargetSpec(
        primary_sections=frozenset({"Objectives", "Abstract", "Data availability", "Code availability"}),
        allowed_sections=frozenset(
            {
                "Objectives",
                "Abstract",
                "Data availability",
                "Code availability",
                "Introduction",
                "Methods",
                "Front matter",
            }
        ),
        weights={
            "has_objective": 3.2,
            "has_data_availability": 3.0,
            "has_population": 0.8,
            "has_self_reference": 0.5,
        },
        require=("has_objective|has_data_availability",),
        penalise={"has_limitation": 1.0, "has_related": 0.8},
        subsection_pattern=r"objectiv|aim|scope|availability|registration|data statement",
    ),
    "contributions": TargetSpec(
        primary_sections=frozenset({"Abstract", "Conclusion", "Discussion", "Results"}),
        allowed_sections=frozenset({"Abstract", "Introduction", "Results", "Discussion", "Conclusion"}),
        weights={
            "has_novelty": 2.6,
            "has_self_reference": 1.0,
            "has_effect": 1.0,
            "relational_score": 0.5,
            "has_direction": 0.4,
        },
        require=("has_novelty|has_self_reference",),
        penalise={
            "has_limitation": 3.0,
            "has_hedge": 0.5,
            "has_related": 1.2,
            "references_display": 0.6,
            "has_url": 1.0,
        },
        subsection_pattern=r"contribution|summary points|key messages|what this adds|conclusion",
    ),
    "methods": TargetSpec(
        primary_sections=frozenset({"Methods"}),
        allowed_sections=frozenset({"Methods", "Objectives", "Abstract"}),
        weights={
            "has_method": 2.0,
            "has_population": 1.2,
            "has_effect": 0.6,
            "relational_score": 0.25,
        },
        require=("has_method|has_population",),
        penalise={"has_limitation": 1.5, "has_related": 1.0},
        max_words=90,
        subsection_pattern=r"develop|process|procedure|design|analys|search|data collection|participants|materials|methods|panel|consensus",
    ),
    "results": TargetSpec(
        primary_sections=frozenset({"Results"}),
        allowed_sections=frozenset({"Results", "Abstract", "Discussion", "Conclusion"}),
        weights={
            "has_effect": 2.8,
            "relational_score": 1.1,
            "has_direction": 1.0,
            "has_comparison": 0.9,
            "has_null_result": 0.9,
            "has_population": 0.4,
        },
        require=("has_effect|has_direction|has_null_result",),
        penalise={"has_limitation": 1.2, "has_method": 0.4},
        subsection_pattern=r"result|finding|statement|checklist|recommendation|outcome|how to use|characteristics",
    ),
    "limitations": TargetSpec(
        primary_sections=frozenset({"Limitations", "Discussion", "Conclusion"}),
        allowed_sections=frozenset({"Limitations", "Discussion", "Conclusion", "Abstract", "Results"}),
        weights={
            "has_limitation": 3.0,
            "has_limitation_strong": 1.2,
            "has_self_reference": 0.7,
            "has_null_result": 0.8,
            "has_hedge": 0.3,
        },
        require=("has_limitation",),
        penalise={"has_novelty": 0.8},
        subsection_pattern=r"limitation|strength|caveat|future",
    ),
    "related": TargetSpec(
        primary_sections=frozenset({"Introduction", "Discussion"}),
        allowed_sections=frozenset({"Introduction", "Discussion", "Conclusion", "Abstract"}),
        weights={"has_related": 2.4, "has_effect": 0.5, "has_comparison": 0.5, "relational_score": 0.3},
        require=("has_related",),
        penalise={"has_novelty": 0.6, "has_limitation": 1.0},
        subsection_pattern=r"previous|prior|background|related|comparison with|existing",
    ),
}


def clean_sentence(text: str) -> str:
    value = normalize_prose(text)
    previous = None
    while previous != value:
        previous = value
        value = LEADING_NOISE_RE.sub("", value).strip()
    value = TRAILING_DISPLAY_RE.sub(".", value)
    value = INLINE_DISPLAY_RE.sub(" ", value)
    value = re.sub(r"\s*\(\s*\)\s*", " ", value)
    return normalize_prose(value)


def _acceptable(text: str, feats: F.SentenceFeatures) -> bool:
    if not 8 <= feats.words <= 95:
        return False
    if not SENTENCE_START_RE.match(text) or not SENTENCE_END_RE.search(text):
        return False
    if feats.is_structural_noise:
        return False
    if not has_finite_verb(text):
        return False
    if feats.numeric_ratio > 0.30:
        return False
    if feats.citation_count >= 4 and feats.words < 45:
        return False
    if feats.has_url and feats.words < 25:
        return False
    return True


def build_candidates(bundle: ParsedBundle) -> list[Candidate]:
    output: list[Candidate] = []
    order = 0
    paragraph_index = 0
    for name, section in bundle.sections.items():
        if name in NON_SCIENTIFIC or name in {"References", "Supplementary"}:
            continue
        for paragraph in section.paragraphs:
            paragraph_index += 1
            for raw in split_sentences(paragraph.text):
                order += 1
                text = clean_sentence(raw)
                if not text:
                    continue
                feats = F.extract(text)
                if not _acceptable(text, feats):
                    continue
                output.append(
                    Candidate(
                        text=text,
                        section=name,
                        subsection=paragraph.subsection,
                        page_start=paragraph.page_start,
                        page_end=paragraph.page_end,
                        source_file=paragraph.source_file,
                        order=order,
                        paragraph=paragraph_index,
                        features=feats,
                        tokens={token for token in TOKEN_RE.findall(text.casefold()) if token not in STOPWORDS},
                    )
                )
    _score_centrality(output)
    _score_section_position(output)
    return output


def _score_section_position(candidates: list[Candidate]) -> None:
    by_section: dict[str, list[Candidate]] = {}
    for candidate in candidates:
        by_section.setdefault(candidate.section, []).append(candidate)
    for items in by_section.values():
        last = len(items) - 1
        for index, candidate in enumerate(items):
            candidate.section_position = index / last if last else 1.0


def _score_centrality(candidates: list[Candidate], iterations: int = 24, damping: float = 0.85) -> None:
    """LexRank over an idf-weighted token-overlap graph (pure standard library)."""
    count = len(candidates)
    if count < 3:
        for candidate in candidates:
            candidate.centrality = 1.0 / max(1, count)
        return
    document_frequency: Counter[str] = Counter()
    for candidate in candidates:
        document_frequency.update(candidate.tokens)
    idf = {token: math.log(1 + count / (1 + frequency)) for token, frequency in document_frequency.items()}
    norms = [math.sqrt(sum(idf[token] ** 2 for token in candidate.tokens)) or 1.0 for candidate in candidates]
    neighbours: list[list[tuple[int, float]]] = [[] for _ in range(count)]
    for left in range(count):
        tokens_left = candidates[left].tokens
        for right in range(left + 1, count):
            shared = tokens_left & candidates[right].tokens
            if not shared:
                continue
            similarity = sum(idf[token] ** 2 for token in shared) / (norms[left] * norms[right])
            if similarity >= 0.10:
                neighbours[left].append((right, similarity))
                neighbours[right].append((left, similarity))
    scores = [1.0 / count] * count
    degree = [sum(weight for _, weight in row) or 1.0 for row in neighbours]
    for _ in range(iterations):
        updated = [(1 - damping) / count] * count
        for index, row in enumerate(neighbours):
            share = damping * scores[index] / degree[index]
            for neighbour, weight in row:
                updated[neighbour] += share * weight
        scores = updated
    highest = max(scores) or 1.0
    for candidate, value in zip(candidates, scores, strict=True):
        candidate.centrality = value / highest


def _requirement_met(feats: F.SentenceFeatures, requirement: str) -> bool:
    return any(bool(getattr(feats, name)) for name in requirement.split("|"))


def score_for(candidate: Candidate, target: str, relaxed: bool = False) -> float:
    """Score a candidate for a target.

    In relaxed mode the cue requirement is dropped: the source clearly has a
    section for this target, so its most central sentences are quoted rather
    than leaving the digest section empty.
    """
    spec = SPECS[target]
    if candidate.section not in spec.allowed_sections:
        return 0.0
    if not spec.min_words <= candidate.features.words <= spec.max_words:
        return 0.0
    if not all(_requirement_met(candidate.features, requirement) for requirement in spec.require):
        if not relaxed:
            return 0.0
        subsection_match = bool(
            spec.subsection_pattern
            and candidate.subsection
            and re.search(spec.subsection_pattern, candidate.subsection, re.I)
        )
        if candidate.section not in spec.primary_sections and not subsection_match:
            return 0.0
    primary = candidate.section in spec.primary_sections
    if not primary and spec.subsection_pattern and candidate.subsection:
        primary = bool(re.search(spec.subsection_pattern, candidate.subsection, re.I))
    score = 3.0 if primary else 0.6
    for name, weight in spec.weights.items():
        # Boolean probes contribute their weight; relational_score contributes
        # its count, so both read the same way here.
        score += weight * float(getattr(candidate.features, name))
    for name, penalty in spec.penalise.items():
        if getattr(candidate.features, name):
            score -= penalty
    if 18 <= candidate.features.words <= 60:
        score += 0.8
    score += 1.2 * candidate.centrality
    if target == "summary":
        # A paper's own concluding sentence is the closest a rule-based system
        # gets to a whole-paper summary, and the abstract's conclusion — which
        # comes first in document order — is better than the body's.
        if candidate.section == "Conclusion":
            score += 4.0
        if candidate.subsection and re.search(r"conclusion|interpretation", candidate.subsection, re.I):
            score += 3.0
        score -= candidate.order / 4000.0
    if candidate.subsection and re.search(r"limitation|strength", candidate.subsection, re.I):
        score += 1.5 if target == "limitations" else -1.0
    if target == "limitations" and candidate.section == "Discussion":
        # Limitations passages sit at the end of a Discussion section.
        score += 1.6 * max(0.0, candidate.section_position - 0.55) / 0.45
    return max(0.0, score)


def expand_passage(
    candidates: list[Candidate],
    chosen: list[Candidate],
    *,
    budget: int,
    limit: int,
    taken: list[Candidate],
) -> list[Candidate]:
    """Add the neighbours of chosen sentences inside the same paragraph.

    A limitations passage is contiguous prose: the authors signal it once and
    then continue. Sentences beside a cue-matching sentence, in the same
    paragraph, belong to the same passage even when they carry no cue of their
    own — and they are still verbatim source text.
    """
    if not chosen:
        return chosen
    anchors = {item.paragraph for item in chosen}
    picked = {id(item) for item in chosen}
    blocked = [item.tokens for item in taken if id(item) not in picked]
    words = sum(word_count(item.text) for item in chosen)
    neighbours = [
        item
        for item in candidates
        if item.paragraph in anchors and id(item) not in picked and not item.features.is_structural_noise
    ]
    for item in sorted(neighbours, key=lambda value: value.order):
        if len(chosen) >= limit or words >= budget:
            break
        if max((_similarity(item.tokens, other) for other in blocked), default=0.0) >= 0.55:
            continue
        chosen.append(item)
        blocked.append(item.tokens)
        words += word_count(item.text)
    return sorted(chosen, key=lambda item: item.order)


def _similarity(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def select(
    candidates: list[Candidate],
    target: str,
    *,
    budget: int,
    limit: int,
    taken: list[Candidate],
    redundancy: float = 0.55,
    diversity: float = 0.6,
    relaxed: bool = False,
) -> list[Candidate]:
    """Maximal-marginal-relevance selection under a word budget."""
    ranked = [(score_for(candidate, target, relaxed), candidate) for candidate in candidates]
    ranked = [(score, candidate) for score, candidate in ranked if score > 0.0]
    if not ranked:
        return []
    highest = max(score for score, _ in ranked) or 1.0
    pool = [(score / highest, candidate) for score, candidate in ranked]
    chosen: list[Candidate] = []
    used_tokens = [candidate.tokens for candidate in taken]
    words = 0
    while pool and len(chosen) < limit and words < budget:
        best_index = -1
        best_value = -1e9
        for index, (score, candidate) in enumerate(pool):
            overlap = max((_similarity(candidate.tokens, other) for other in used_tokens), default=0.0)
            if overlap >= redundancy:
                continue
            value = score - diversity * overlap
            if value > best_value or (
                value == best_value and best_index >= 0 and candidate.order < pool[best_index][1].order
            ):
                best_value, best_index = value, index
        if best_index < 0:
            break
        _score, candidate = pool.pop(best_index)
        length = word_count(candidate.text)
        if chosen and words + length > budget:
            continue
        chosen.append(candidate)
        used_tokens.append(candidate.tokens)
        words += length
    return sorted(chosen, key=lambda item: item.order)
