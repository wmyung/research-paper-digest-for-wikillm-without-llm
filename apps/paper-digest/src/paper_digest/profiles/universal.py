"""The digest compiler.

One profile drives every document type; the resolved :class:`DocumentProfile`
supplies the sub-headings, the applicable targets and the evidence slots. All
prose is assembled from verbatim source sentences chosen by
:mod:`paper_digest.selection`, so the output is grounded by construction.
"""

from __future__ import annotations

import re

from ..config import DigestConfig
from ..documents import DEFAULT_PROFILE, PROFILES_BY_KEY, DocumentProfile, classify_document
from ..evidence import coverage_ledger, evidence_units
from ..glossary import build as build_glossary
from ..keywords import extract_keyphrases
from ..models import ParsedBundle
from ..selection import Candidate, build_candidates, expand_passage, score_for, select
from ..taxonomy import classify_design
from ..text import normalize_prose, unique_preserve, word_count
from .base import ProfileContent, ProfileScore
from .common import classification_block

# Word budgets per target before repair scaling, and the maximum number of
# evidence units each section may carry.
BUDGETS = {
    "information": 330,
    "contributions": 460,
    "methods": 1050,
    "results": 1150,
    "limitations": 450,
    "related": 480,
}
LIMITS = {"information": 8, "contributions": 7, "methods": 26, "results": 28, "limitations": 9, "related": 10}
# Targets are filled in this order; high-risk semantic targets reserve their
# cue-matching evidence before broader results and methods selection.
ORDER = ("summary", "information", "limitations", "related", "contributions", "results", "methods")
# Targets whose meaning comes from the source section itself may be filled
# without a cue match. Limitations is not one of them: a limitation is defined
# by its cue, so relaxing it would turn ordinary discussion into a caveat.
RELAXABLE = {"methods": 3, "results": 3, "information": 2, "contributions": 3, "related": 2}

ABSENCE_NOTES = {
    "information": "The source states no explicit objective or data-availability statement that could be quoted verbatim.",
    "contributions": "The source states no self-attributed contribution claim that could be quoted verbatim.",
    "methods": "The source describes no study design, population or analysis in quotable prose.",
    "results": "The source reports no quantitative or directional finding in quotable prose.",
    "limitations": "The source states no limitation, caveat or boundary condition.",
    "related": "The source positions itself against no prior work in quotable prose.",
}
NOT_APPLICABLE_NOTES = {
    "results": "This document type reports no findings; the source contains none to quote.",
    "methods": "This document type describes no study procedure.",
    "limitations": "This document type states no study limitations.",
    "related": "This document type cites no prior work in quotable prose.",
}


def _words(items: list[Candidate]) -> int:
    return sum(word_count(item.text) for item in items)


def _pack(items: list[Candidate], heading: str, max_words: int = 110) -> str:
    paragraphs: list[str] = []
    current: list[str] = []
    count = 0
    for item in items:
        size = word_count(item.text)
        if current and count + size > max_words:
            paragraphs.append(" ".join(current))
            current, count = [], 0
        current.append(item.text)
        count += size
    if current:
        paragraphs.append(" ".join(current))
    body = "\n\n".join(paragraphs)
    return f"### {heading}\n\n{body}" if body else f"### {heading}"


def _section_body(
    target: str,
    items: list[Candidate],
    profile: DocumentProfile,
    style: str = "paragraph",
    authored: list[str] | None = None,
    pack_words: int = 110,
) -> str:
    heading = profile.subheadings.get(target, target.title())
    if items:
        if style == "numbered":
            return "\n".join(f"{index}. {item.text}" for index, item in enumerate(items, start=1))
        if style == "bullet":
            return "\n".join(f"- {item.text}" for item in items)
        return _pack(items, heading, pack_words)
    if target not in profile.applicable_targets:
        note = NOT_APPLICABLE_NOTES.get(target, "This document type does not carry this content.")
    else:
        note = ABSENCE_NOTES[target]
    if authored is not None:
        authored.append(note)
    if style in {"numbered", "bullet"}:
        return f"- {note}"
    return f"### {heading}\n\n{note}"


NO_SUMMARY_NOTE = "The supplied source did not yield a grounded one-line summary."


def _one_line(items: list[Candidate], bundle: ParsedBundle, authored: list[str]) -> str:
    if items:
        return items[0].text
    abstract = normalize_prose(bundle.metadata.abstract)
    if abstract:
        from ..text import split_sentences

        sentences = split_sentences(abstract)
        if sentences:
            return sentences[-1]
    authored.append(NO_SUMMARY_NOTE)
    return NO_SUMMARY_NOTE


def _retrieval_queries(bundle: ParsedBundle, selected: dict[str, list[Candidate]]) -> list[dict[str, object]]:
    metadata = bundle.metadata
    surname = metadata.authorship.authors[0].split()[-1] if metadata.authorship.authors else "the authors"
    journal_term = metadata.journal or str(metadata.year or "publication")
    queries: list[dict[str, object]] = [
        {
            "id": "publication",
            "query": "In which journal and year was this paper published?",
            "expected_terms": [journal_term],
        },
        {
            "id": "authorship",
            "query": f"What is the author count, and who authored the paper including {surname}?",
            "expected_terms": ["Author count"],
        },
    ]
    stop = {
        "about",
        "after",
        "also",
        "among",
        "because",
        "before",
        "between",
        "could",
        "from",
        "have",
        "into",
        "paper",
        "participants",
        "reported",
        "study",
        "their",
        "these",
        "this",
        "those",
        "through",
        "using",
        "were",
        "which",
        "with",
        "would",
        "there",
    }

    def anchor(text: str) -> str:
        numeric = re.search(r"\b(?:\d+(?:\.\d+)?%|\d+\.\d+|[A-Z]{3,}[A-Z0-9+\-]*)\b", text)
        if numeric:
            return numeric.group(0)
        tokens = [token for token in re.findall(r"[A-Za-z][A-Za-z0-9+\-]{4,}", text) if token.casefold() not in stop]
        return max(tokens, key=len, default=bundle.metadata.category.replace("-", " "))

    prompts = {
        "information": "What was the objective, and what data or materials were used?",
        "contributions": "What concrete contributions does the paper make relative to prior work?",
        "methods": "What design, population, measurements and analyses were used?",
        "results": "What were the principal quantitative or directional findings?",
        "limitations": "What limitations, uncertainty and boundary conditions are reported?",
        "related": "How does the paper relate to previous studies or methods?",
    }
    for target, prompt in prompts.items():
        items = selected.get(target, [])
        if not items:
            continue
        term = anchor(items[0].text)
        queries.append(
            {
                "id": target,
                "query": f"{prompt.rstrip('?')} Specifically, what does it report about {term}?",
                "expected_terms": [term],
            }
        )
    pool = selected.get("results", []) + selected.get("methods", [])
    index = 0
    while len(queries) < 10 and pool:
        item = pool[index % len(pool)]
        term = anchor(item.text)
        queries.append(
            {
                "id": f"evidence-{len(queries) + 1}",
                "query": f"What evidence does the paper provide about {term}?",
                "expected_terms": [term],
            }
        )
        index += 1
        if index > len(pool) * 2:
            break
    return queries[:12]


class UniversalProfile:
    name = "universal"

    def __init__(self, config: DigestConfig, repair_pass: int = 0):
        self.config = config
        self.repair_pass = repair_pass
        self.document_profile: DocumentProfile = DEFAULT_PROFILE
        self.profile_ranking: list[tuple[str, float]] = []
        self.coverage: dict[str, object] = {}
        self.section_capacity: dict[str, int] = {}
        self.candidates: list[Candidate] = []
        self.relaxed_targets: list[str] = []
        self.selection_diagnostics: dict[str, object] = {}

    def score(self, bundle: ParsedBundle) -> ProfileScore:
        sections = {name for name, value in bundle.sections.items() if value.paragraphs}
        required = len(sections & {"Abstract", "Methods", "Results", "Discussion", "Conclusion"})
        score = min(0.99, 0.45 + required * 0.1 + min(0.2, len(bundle.full_text.split()) / 30000))
        return ProfileScore(self.name, bundle.metadata.category, score, sorted(sections))

    def classify(self, bundle: ParsedBundle) -> None:
        metadata = bundle.metadata
        populated_sections = {name for name, section in bundle.sections.items() if section.paragraphs}
        page_count = next(
            (item.page_count for item in bundle.files if item.role == "canonical-paper" and item.page_count),
            len(bundle.page_texts) or None,
        )
        profile, ranking = classify_document(
            metadata.title,
            metadata.abstract,
            bundle.full_text,
            metadata.article_type,
            section_names=populated_sections,
            page_count=page_count,
        )
        self.document_profile = profile
        self.profile_ranking = ranking
        metadata.document_profile = profile.key
        category, fields = classify_design(
            metadata.title,
            metadata.abstract,
            bundle.full_text,
            metadata.article_type,
            preferred=profile.category_bias,
        )
        metadata.category = category
        metadata.research_fields = fields[: self.config.field_limit]
        preferred = list(metadata.author_keywords) + [category.replace("-", " ")]
        keywords = extract_keyphrases(
            metadata.title + " " + metadata.abstract + " " + bundle.full_text[:60000],
            self.config.keyword_limit,
            preferred,
            authors=metadata.authorship.authors,
        )
        fillers = [
            category.replace("-", " "),
            profile.key.replace("_", " "),
            "study design",
            "outcomes",
            "limitations",
            "evidence",
        ]
        metadata.index_keywords = unique_preserve(keywords + fillers)[: self.config.keyword_limit]

    def compile(self, bundle: ParsedBundle) -> ProfileContent:
        return self.render(bundle, self.select_all(bundle))

    def select_all(self, bundle: ParsedBundle) -> dict[str, list[Candidate]]:
        """Choose the evidence units for every target.

        Kept separate from :meth:`render` so a repair stage can adjust the
        selection and rebuild the digest, its ledgers and its retrieval
        questions from the amended selection rather than editing prose.
        """
        profile = self.document_profile
        candidates = build_candidates(bundle)
        self.candidates = candidates
        scale = 1.0 + self.repair_pass * 0.18
        active = tuple(target for target in ORDER if target == "summary" or target in profile.applicable_targets)
        selected: dict[str, list[Candidate]] = {}
        taken: list[Candidate] = []
        for target in ORDER:
            if target != "summary" and target not in profile.applicable_targets:
                selected[target] = []
                continue
            if target == "summary":
                items = select(candidates, "summary", budget=70, limit=1, taken=taken, redundancy=1.01)
            else:
                items = select(
                    candidates,
                    target,
                    budget=int(BUDGETS[target] * scale),
                    limit=LIMITS[target],
                    taken=taken,
                )
            selected[target] = items
            taken.extend(items)

        # A digest section must not be silently thin when the source has the
        # material. First try to reach the section floor with cue-matching
        # sentences, then — only for sections whose meaning comes from the
        # source section itself — retry without the cue requirement.
        floors = self.config.section_min_words
        relaxed_targets: list[str] = []
        for target in ORDER:
            if target == "summary" or target not in profile.applicable_targets:
                continue
            floor = floors.get(target, 0)
            if _words(selected[target]) >= floor:
                continue
            extra = select(
                candidates,
                target,
                budget=int(max(BUDGETS[target] * scale, floor * 2.2)),
                limit=LIMITS[target] * 2,
                taken=[item for item in taken if item not in selected[target]],
            )
            fresh = [item for item in extra if item not in selected[target]]
            if fresh:
                selected[target] = sorted(selected[target] + fresh, key=lambda item: item.order)
                taken.extend(fresh)

        # Cue matching finds the sentence that signals a passage; the rest of
        # that paragraph belongs to the same passage. Taking it whole is how a
        # thin section is filled without relaxing what the cue means.
        for target in ORDER:
            if target == "summary" or target not in profile.applicable_targets:
                continue
            if _words(selected[target]) >= floors.get(target, 0) or not selected[target]:
                continue
            before = list(selected[target])
            selected[target] = expand_passage(
                candidates,
                selected[target],
                budget=int(max(BUDGETS[target] * scale, floors.get(target, 0) * 2.0)),
                limit=LIMITS[target] + 6,
                taken=taken,
            )
            taken.extend(item for item in selected[target] if item not in before)

        # The relaxed pass never invents a limitation out of ordinary prose.
        for target in ORDER:
            if target not in RELAXABLE or target not in profile.applicable_targets:
                continue
            floor = floors.get(target, 0)
            if len(selected[target]) >= RELAXABLE[target] and _words(selected[target]) >= floor:
                continue
            items = select(
                candidates,
                target,
                budget=int(max(BUDGETS[target] * scale * 0.9, floor * 1.8)),
                limit=max(4, LIMITS[target]),
                taken=[item for item in taken if item not in selected[target]],
                relaxed=True,
            )
            fresh = [item for item in items if item not in selected[target]]
            if fresh:
                selected[target] = sorted(selected[target] + fresh, key=lambda item: item.order)
                taken.extend(fresh)
                relaxed_targets.append(target)

        # Key Contributions must carry between three and seven explicit items.
        minimum = self.config.min_contribution_items
        maximum = self.config.max_contribution_items
        if "contributions" in profile.applicable_targets:
            if len(selected["contributions"]) < minimum:
                backfill = select(
                    candidates,
                    "results",
                    budget=int(BUDGETS["contributions"] * scale),
                    limit=minimum + 1 - len(selected["contributions"]),
                    taken=[item for item in taken if item not in selected["contributions"]],
                )
                selected["contributions"].extend(backfill)
                selected["contributions"].sort(key=lambda item: item.order)
                taken.extend(backfill)
            if len(selected["contributions"]) > maximum:
                keep = sorted(
                    selected["contributions"],
                    key=lambda item: -score_for(item, "contributions"),
                )[:maximum]
                selected["contributions"] = sorted(keep, key=lambda item: item.order)

        # Capacity is measured in the mode the target is actually filled in, so
        # a shortfall can be attributed to the source rather than the selector.
        self.section_capacity = {
            target: sum(
                word_count(item.text)
                for item in candidates
                if score_for(item, target, relaxed=target in RELAXABLE) > 0.0
            )
            for target in ORDER
        }
        self.relaxed_targets = relaxed_targets
        self.selection_diagnostics = {
            "algorithm": "risk-ordered-mmr",
            "candidate_count": len(candidates),
            "active_targets": list(active),
            "first_selected": {
                target: {
                    "page": items[0].page_start,
                    "order": items[0].order,
                    "section": items[0].section,
                    "score": round(score_for(items[0], target), 4),
                }
                for target, items in selected.items()
                if items
            },
            "empty_targets": [target for target in active if not selected.get(target)],
            "relaxed_targets": list(relaxed_targets),
        }
        return selected

    def render(self, bundle: ParsedBundle, selection: dict[str, list[Candidate]]) -> ProfileContent:
        """Build the digest, its ledgers and its questions from a selection."""
        profile = self.document_profile
        selected = {target: list(selection.get(target) or []) for target in ORDER}
        summary_items = selected.pop("summary", [])
        content_sections = {target: [item.text for item in items] for target, items in selected.items()}
        self.coverage = coverage_ledger(bundle, profile, content_sections)

        warnings: list[str] = []
        for target in self.relaxed_targets:
            warnings.append(
                f"Section '{target}' was filled from its source section without a matching cue phrase; "
                "review its precision."
            )
        for target in ("information", "contributions", "methods", "results", "limitations", "related"):
            if target in profile.applicable_targets and not selected[target]:
                warnings.append(f"No grounded evidence unit was selected for {target}.")

        authored: list[str] = []
        one_line = _one_line(summary_items, bundle, authored)
        info_body = _section_body(
            "information",
            selected["information"],
            profile,
            authored=authored,
            pack_words=self.config.paragraph_pack_target_words,
        )
        glossary_text, glossary_authored = build_glossary(
            bundle.full_text,
            bundle.metadata.index_keywords,
            minimum=self.config.min_glossary_entries,
            min_words=self.config.section_min_words.get("glossary", 60),
        )
        authored.extend(glossary_authored)
        return ProfileContent(
            one_line_summary=one_line,
            document_information=classification_block(bundle) + "\n\n" + info_body,
            key_contributions=_section_body("contributions", selected["contributions"], profile, "numbered", authored),
            methodology=_section_body("methods", selected["methods"], profile, authored=authored),
            results=_section_body("results", selected["results"], profile, authored=authored),
            limitations=_section_body("limitations", selected["limitations"], profile, "bullet", authored),
            related_work=_section_body("related", selected["related"], profile, authored=authored),
            glossary=glossary_text,
            warnings=warnings,
            authored=authored,
            evidence=evidence_units({**selected, "summary": summary_items}),
            retrieval_queries=_retrieval_queries(bundle, selected),
        )


__all__ = ["UniversalProfile", "PROFILES_BY_KEY"]
