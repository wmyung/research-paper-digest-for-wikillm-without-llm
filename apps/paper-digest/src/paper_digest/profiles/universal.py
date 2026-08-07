from __future__ import annotations

import re
from dataclasses import dataclass

from ..config import DigestConfig
from ..keywords import extract_keyphrases
from ..models import ParsedBundle
from ..text import normalize_prose, split_sentences, unique_preserve, word_count
from .base import ProfileContent, ProfileScore
from .common import classification_block


@dataclass(slots=True)
class Candidate:
    text: str
    section: str
    page_start: int
    page_end: int
    source_file: str
    order: int
    score: float = 0.0


DESIGNS: list[tuple[str, list[str], tuple[str, ...]]] = [
    (
        "randomized-trial",
        ["clinical research", "randomized trials"],
        ("randomized", "randomised", "placebo", "trial registration"),
    ),
    (
        "meta-analysis",
        ["evidence synthesis", "meta-analysis"],
        ("meta-analysis", "pooled effect", "heterogeneity", "forest plot"),
    ),
    (
        "systematic-review",
        ["evidence synthesis", "systematic review"],
        ("systematic review", "search strategy", "prisma"),
    ),
    (
        "prediction-model",
        ["prediction modeling", "clinical informatics"],
        ("area under the curve", "calibration", "validation cohort", "prediction model"),
    ),
    (
        "psychometrics",
        ["psychometrics", "measurement science"],
        ("factor analysis", "internal consistency", "test-retest", "measurement invariance"),
    ),
    (
        "gwas",
        ["statistical genetics", "population genomics"],
        ("genome-wide association", "polygenic", "snp heritability", "genetic correlation"),
    ),
    (
        "neuroimaging",
        ["neuroimaging", "computational neuroscience"],
        ("functional magnetic resonance", "voxel", "cortical thickness", "connectivity"),
    ),
    (
        "observational-cohort",
        ["epidemiology", "observational research"],
        ("prospective cohort", "retrospective cohort", "follow-up", "hazard ratio"),
    ),
    ("case-control", ["epidemiology", "case-control research"], ("case-control", "odds ratio", "matched controls")),
    ("cross-sectional", ["epidemiology", "cross-sectional research"], ("cross-sectional", "prevalence", "survey")),
    (
        "qualitative-study",
        ["qualitative research", "health services research"],
        ("thematic analysis", "grounded theory", "semi-structured interviews"),
    ),
    (
        "method-development",
        ["computational methods", "method development"],
        ("algorithm", "benchmark", "simulation", "software implementation"),
    ),
]

TARGET_RULES = {
    "information": (
        {"Front matter", "Abstract", "Objectives", "Data availability", "Code availability"},
        ("objective", "aim", "purpose", "participant", "sample", "data", "code", "available", "license"),
    ),
    "contributions": (
        {"Abstract", "Introduction", "Results", "Discussion", "Conclusion"},
        ("first", "novel", "demonstrat", "show", "found", "develop", "compared", "improv"),
    ),
    "methods": (
        {"Methods", "Objectives", "Front matter"},
        (
            "participant",
            "included",
            "recruited",
            "measured",
            "assessed",
            "model",
            "regression",
            "adjust",
            "random",
            "outcome",
            "exposure",
            "analysis",
        ),
    ),
    "results": (
        {"Results", "Abstract", "Discussion", "Conclusion"},
        (
            "result",
            "found",
            "higher",
            "lower",
            "associated",
            "difference",
            "increased",
            "decreased",
            "confidence interval",
            "p ",
            "significant",
            "not significant",
        ),
    ),
    "limitations": (
        {"Limitations", "Discussion", "Conclusion", "Abstract"},
        (
            "limit",
            "caution",
            "cannot",
            "unable",
            "may not",
            "uncertain",
            "generaliz",
            "future",
            "bias",
            "small sample",
            "underrepresent",
            "did not assess",
            "only examined",
        ),
    ),
    "related": (
        {"Introduction", "Discussion", "References"},
        ("previous", "prior", "earlier", "reported", "compared with", "consistent with", "in contrast"),
    ),
}

NOISE_RE = re.compile(
    r"creative commons|correspondence:|@|department of|university|all rights reserved|"
    r"publisher'?s note|supplementary information is available|^https?://|^research\s+open\s+access|"
    r"science\+business media|published by .*?(?:sons|press|publishing)|sage publications|"
    r"credit authorship contribution statement",
    re.I,
)
NUMERIC_RE = re.compile(r"\b(?:n\s*=|p\s*[<=>]|\d+(?:\.\d+)?%|\d+\.\d+|95%\s*ci|odds ratio|hazard ratio)\b", re.I)
SELF_REFERENCE_RE = re.compile(
    r"\b(?:we|our|this study|current study|present study|these findings|the findings)\b", re.I
)
TABLE_FRAGMENT_RE = re.compile(r"\b(?:table|fig(?:ure)?\.?|χ\s*2|critical ratio|standard error)\b", re.I)
LAYOUT_NOISE_RE = re.compile(r"[A-Za-z]{25,}|\buntreated period\b|\bforest plot\b", re.I)
CAPTION_SENTENCE_RE = re.compile(
    r"^(?:fig(?:ure)?\.?\s*\d+|table\s*\d+|this figure\b|"
    r"the threshold for significance\b|"
    r"the (?:black|dashed|solid|red|blue|horizontal|vertical) line\b|"
    r"error bars?\b|venn diagrams? depicting\b|included in this figure\b|"
    r"[a-f]\.\s+(?:the|each|association|results?)\b)",
    re.I,
)
INLINE_LABEL_ENDINGS = {
    "analysis",
    "analyses",
    "architecture",
    "availability",
    "control",
    "correlation",
    "correlations",
    "disorder",
    "disorders",
    "genes",
    "heritability",
    "oc",
    "overlap",
    "pathways",
    "phenotyping",
    "population",
    "results",
    "scoring",
}


def _strip_inline_label(sentence: str) -> str:
    """Remove a short publisher subheading fused to the first sentence."""
    first_word = re.match(r"([A-Z][A-Za-z0-9-]*)\b", sentence)
    if first_word:
        tail = sentence[first_word.end() :]
        repeated = re.search(rf"\s+(?={re.escape(first_word.group(1))}\b)", tail)
        if repeated:
            cut = first_word.end() + repeated.start()
            prefix = sentence[:cut]
            if word_count(prefix) <= 12 and not re.search(r"[.;:!?]", prefix):
                return sentence[cut:].strip()

    for match in re.finditer(r"\s+(?=[A-Z][A-Za-z0-9-]*\b)", sentence):
        prefix = sentence[: match.start()].strip()
        words = re.findall(r"[A-Za-z][A-Za-z-]*", prefix)
        if not 1 <= len(words) <= 10 or re.search(r"[.;:!?]", prefix):
            continue
        if words[-1].casefold() in INLINE_LABEL_ENDINGS:
            return sentence[match.end() :].strip()

    endings = "|".join(sorted(INLINE_LABEL_ENDINGS, key=len, reverse=True))
    sentence = re.sub(
        rf"(?<=[.!?])\s+[A-Z][A-Za-z0-9-]*(?:\s+[A-Za-z][A-Za-z0-9-]*){{0,9}}\s+(?:{endings})\s+(?=[A-Z])",
        " ",
        sentence,
    )
    return sentence


def _sentences(bundle: ParsedBundle) -> list[Candidate]:
    output: list[Candidate] = []
    order = 0
    for section_name, section in bundle.sections.items():
        if section_name in {"References", "Acknowledgements", "Author contributions", "Competing interests"}:
            continue
        for paragraph in section.paragraphs:
            for sentence in split_sentences(paragraph.text):
                order += 1
                sentence = normalize_prose(sentence)
                sentence = re.sub(
                    r"^(?:background|objective|objectives|methods?|results?|limitations?|conclusions?)\s*[:.-]?\s+",
                    "",
                    sentence,
                    flags=re.I,
                )
                sentence = _strip_inline_label(sentence)
                marker = re.search(
                    r"\b(?:Table\s+\d+|Fig(?:ure)?\.?\s*\d+|Est unstandardized model estimate|SE Critical Ratio)\b",
                    sentence,
                    re.I,
                )
                if marker and word_count(sentence[: marker.start()]) >= 8:
                    sentence = sentence[: marker.start()].rstrip(" ,;:(") + "."
                elif marker and marker.start() < 20:
                    continue
                count = word_count(sentence)
                if (
                    count < 8
                    or count > 105
                    or NOISE_RE.search(sentence)
                    or LAYOUT_NOISE_RE.search(sentence)
                    or CAPTION_SENTENCE_RE.search(sentence)
                    or "included in this figure" in sentence.casefold()
                    or not re.match(r"^[A-Z0-9(\[]", sentence)
                    or re.search(r"\s+[a-f]\.\s*$", sentence, re.I)
                    or re.search(r",\s*[A-Z]{1,4}\.\s*$", sentence)
                    or re.search(r"\b(?:FDR|P|CI|OR|HR|r[_ ]?g)\s*[<=>]\s+(?=[A-Z])", sentence)
                    or not re.search(r"[.!?][)\]\"'’]*$", sentence)
                ):
                    continue
                number_count = len(re.findall(r"(?<![A-Za-z])[-+]?\d+(?:\.\d+)?%?", sentence))
                if number_count >= 9 and (TABLE_FRAGMENT_RE.search(sentence) or number_count / max(1, count) > 0.22):
                    continue
                if TABLE_FRAGMENT_RE.search(sentence) and number_count >= 4:
                    continue
                tail_numbers = len(re.findall(r"[-+]?\d+(?:\.\d+)?%?", " ".join(sentence.split()[-10:])))
                if tail_numbers >= 5:
                    continue
                if re.search(r"\b[A-Z]\.$", sentence):
                    continue
                if len(re.findall(r"\[[0-9, -]+\]|\([A-Z][A-Za-z]+ et al\.,? \d{4}\)", sentence)) > 4:
                    continue
                output.append(
                    Candidate(
                        text=sentence,
                        section=section_name,
                        page_start=paragraph.page_start,
                        page_end=paragraph.page_end,
                        source_file=paragraph.source_file,
                        order=order,
                    )
                )
    return output


def _token_set(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.casefold()))


def _select(candidates: list[Candidate], target: str, budget: int, limit: int) -> list[Candidate]:
    sections, cues = TARGET_RULES[target]
    available_sections = {item.section for item in candidates}
    has_methods = "Methods" in available_sections
    has_limitations = "Limitations" in available_sections
    has_discussion = "Discussion" in available_sections
    ranked: list[Candidate] = []
    for item in candidates:
        lower = item.text.casefold()
        cue_hits = sum(cue in lower for cue in cues)
        if target == "information" and item.section not in sections:
            continue
        if (
            target == "information"
            and cue_hits == 0
            and item.section
            not in {
                "Objectives",
                "Data availability",
                "Code availability",
            }
        ):
            continue
        if target == "methods" and has_methods and item.section not in {"Methods", "Abstract"}:
            continue
        if target == "methods" and item.section == "Abstract" and cue_hits == 0:
            continue
        if target == "results" and item.section not in sections:
            continue
        if target == "results" and item.section != "Results" and cue_hits == 0:
            continue
        if target == "contributions" and item.section not in sections:
            continue
        if target == "contributions" and not SELF_REFERENCE_RE.search(item.text):
            continue
        if target == "contributions" and re.search(
            r"\b(?:hypothes|expect|sought to|aim(?:ed)? to|objective|would|will|we regressed|we used|we applied)\b",
            lower,
        ):
            continue
        if target == "limitations" and has_limitations and item.section != "Limitations":
            continue
        if target == "limitations" and not has_limitations:
            fallback_sections = {"Discussion", "Conclusion"} if has_discussion else {"Abstract", "Conclusion"}
            explicit_boundary = re.search(r"\b(?:limitations?|caveats?)\b", lower)
            if item.section not in fallback_sections and not explicit_boundary:
                continue
        if target == "related" and item.section not in {"Introduction", "Discussion", "Abstract", "Front matter"}:
            continue
        if target in {"contributions", "limitations", "related"} and cue_hits == 0:
            continue
        section_score = 4.0 if item.section in sections else -1.0
        cue_score = cue_hits * 1.7
        numeric_score = 2.5 if NUMERIC_RE.search(item.text) and target in {"methods", "results", "limitations"} else 0.0
        length = word_count(item.text)
        length_score = 1.5 if 18 <= length <= 70 else 0.2
        item.score = section_score + cue_score + numeric_score + length_score
        if item.score > 1.0:
            ranked.append(item)
    ranked.sort(key=lambda item: (-item.score, item.order))
    chosen: list[Candidate] = []
    chosen_sets: list[set[str]] = []
    words = 0
    for item in ranked:
        tokens = _token_set(item.text)
        if any(len(tokens & other) / max(1, len(tokens | other)) >= 0.68 for other in chosen_sets):
            continue
        count = word_count(item.text)
        if chosen and words + count > budget:
            continue
        chosen.append(item)
        chosen_sets.append(tokens)
        words += count
        if len(chosen) >= limit or words >= budget * 0.9:
            break
    return sorted(chosen, key=lambda item: item.order)


def _pack(items: list[Candidate], heading: str, max_words: int = 170) -> str:
    paragraphs: list[str] = []
    current: list[str] = []
    count = 0
    for item in items:
        size = word_count(item.text)
        if current and count + size > max_words:
            paragraphs.append(" ".join(current))
            current = []
            count = 0
        current.append(item.text)
        count += size
    if current:
        paragraphs.append(" ".join(current))
    return f"### {heading}\n\n" + "\n\n".join(paragraphs)


def _single_sentence(items: list[Candidate]) -> str:
    if not items:
        return "The supplied paper could not yield a sufficiently grounded one-line summary."
    selected: list[str] = []
    words = 0
    for item in items:
        clean = item.text.strip().rstrip(".!?;:")
        size = word_count(clean)
        if selected and words + size > 95:
            break
        selected.append(clean)
        words += size
        if words >= 35:
            break
    return "; ".join(selected).strip() + "."


def _initials(words: list[str]) -> str:
    stop = {"a", "an", "and", "for", "in", "of", "on", "the", "to", "with"}
    letters: list[str] = []
    for word in words:
        if word.casefold() in stop:
            continue
        for part in re.findall(r"[A-Za-z]+", word):
            if part.casefold() not in stop:
                letters.append(part[0].upper())
    return "".join(letters)


def _glossary(text: str, keywords: list[str]) -> str:
    pairs: list[tuple[str, str]] = []
    for match in re.finditer(r"\(([A-Z][A-Z0-9+\-]{1,11})\)", text):
        acronym = match.group(1)
        letters = re.sub(r"[^A-Z]", "", acronym)
        if len(letters) < 2 or len(letters) / len(acronym) < 0.6:
            continue
        prefix = normalize_prose(text[max(0, match.start() - 150) : match.start()]).strip(" ,.;:")
        prefix = re.split(r"[.;:]", prefix)[-1].strip()
        words = re.findall(r"[A-Za-z][A-Za-z'’/\-]*", prefix)[-14:]
        full = ""
        for size in range(2, min(12, len(words)) + 1):
            candidate_words = words[-size:]
            if _initials(candidate_words) == letters:
                full = " ".join(candidate_words)
                break
        if full:
            pairs.append((acronym, full))
    lines: list[str] = []
    seen_pairs: set[str] = set()
    for acronym, full in pairs:
        key = acronym.casefold()
        if key in seen_pairs:
            continue
        seen_pairs.add(key)
        lines.append(f"- **{acronym}** — {full}.")
    if len(lines) < 5:
        for term in keywords:
            if len(lines) >= 10:
                break
            if re.fullmatch(r"[A-Z][A-Z0-9+\-]{1,11}", term):
                continue
            lines.append(
                f"- **{term}** — An author-supplied or deterministically selected indexing term from the paper."
            )
    return "\n".join(unique_preserve(lines)[:12])


def _evidence(items_by_target: dict[str, list[Candidate]]) -> list[dict[str, object]]:
    ledger: list[dict[str, object]] = []
    seen: set[tuple[str, int, str]] = set()
    for target, items in items_by_target.items():
        for item in items:
            key = (item.source_file, item.page_start, item.text)
            if key in seen:
                continue
            seen.add(key)
            ledger.append(
                {
                    "target": target,
                    "source_file": item.source_file,
                    "page_start": item.page_start,
                    "page_end": item.page_end,
                    "source_section": item.section,
                    "statement": item.text,
                }
            )
    return ledger


def _queries(bundle: ParsedBundle, items_by_target: dict[str, list[Candidate]]) -> list[dict[str, object]]:
    metadata = bundle.metadata
    surname = metadata.authorship.authors[0].split()[-1] if metadata.authorship.authors else "authors"
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
    }

    def anchor(text: str) -> str:
        numeric = re.search(r"\b(?:\d+(?:\.\d+)?%|\d+\.\d+|[A-Z]{3,}[A-Z0-9+\-]*)\b", text)
        if numeric:
            return numeric.group(0)
        tokens = [token for token in re.findall(r"[A-Za-z][A-Za-z0-9+\-]{4,}", text) if token.casefold() not in stop]
        return max(tokens, key=len, default=bundle.metadata.category.replace("-", " "))

    prompts = {
        "information": "What was the paper's objective and what data or materials did it use?",
        "contributions": "What concrete contributions does the paper make relative to prior work?",
        "methods": "What study design, participants, measurements, and analyses were used?",
        "results": "What were the paper's principal quantitative or directional findings?",
        "limitations": "What limitations, uncertainty, and boundary conditions does the paper report?",
        "related": "In the Related Work section, how does the paper relate to previous studies or methods?",
    }
    for target, prompt in prompts.items():
        selected = items_by_target.get(target, [])
        if not selected:
            continue
        term = anchor(selected[0].text)
        queries.append(
            {
                "id": target,
                "query": f"{prompt.rstrip('?')} Specifically, what does it report about {term}?",
                "expected_terms": [term],
            }
        )
    while len(queries) < 10:
        index = len(queries) - 1
        selected = items_by_target.get("results", []) + items_by_target.get("methods", [])
        if not selected:
            break
        item = selected[index % len(selected)]
        term = anchor(item.text)
        queries.append(
            {
                "id": f"evidence-{len(queries) + 1}",
                "query": f"What evidence does the paper provide about {term}?",
                "expected_terms": [term],
            }
        )
    return queries[:12]


class UniversalProfile:
    name = "universal"

    def __init__(self, config: DigestConfig, repair_pass: int = 0):
        self.config = config
        self.repair_pass = repair_pass

    def score(self, bundle: ParsedBundle) -> ProfileScore:
        sections = {name for name, value in bundle.sections.items() if value.paragraphs}
        required = len(sections & {"Abstract", "Methods", "Results", "Discussion", "Conclusion"})
        score = min(0.99, 0.45 + required * 0.1 + min(0.2, len(bundle.full_text.split()) / 30000))
        return ProfileScore(self.name, bundle.metadata.category, score, sorted(sections))

    def classify(self, bundle: ParsedBundle) -> None:
        corpus = (bundle.metadata.title + "\n" + bundle.full_text[:100000]).casefold()
        scored: list[tuple[int, int, str, list[str], tuple[str, ...]]] = []
        for order, (category, fields, terms) in enumerate(DESIGNS):
            score = sum(corpus.count(term) for term in terms)
            scored.append((score, -order, category, fields, terms))
        best = max(scored)
        if best[0] == 0:
            article = bundle.metadata.article_type.casefold()
            if "review" in article:
                category, fields, terms = "systematic-review", ["evidence synthesis", "scientific review"], ("review",)
            else:
                category, fields, terms = (
                    "observational-study",
                    ["scientific research", "empirical research"],
                    ("observational",),
                )
        else:
            _, _, category, fields, terms = best
        bundle.metadata.category = category
        bundle.metadata.research_fields = fields[: self.config.field_limit]
        preferred = list(bundle.metadata.author_keywords) + list(terms) + [category.replace("-", " ")]
        keywords = extract_keyphrases(
            bundle.metadata.title + " " + bundle.full_text[:60000], self.config.keyword_limit, preferred
        )
        fillers = [category.replace("-", " "), "study design", "methods", "outcomes", "limitations", "evidence"]
        bundle.metadata.index_keywords = unique_preserve(keywords + fillers)[: self.config.keyword_limit]

    def compile(self, bundle: ParsedBundle) -> ProfileContent:
        candidates = _sentences(bundle)
        scale = 1.0 + self.repair_pass * 0.18
        budgets = {
            "information": int(320 * scale),
            "contributions": int(420 * scale),
            "methods": int(1050 * scale),
            "results": int(1150 * scale),
            "limitations": int(420 * scale),
            "related": int(420 * scale),
        }
        limits = {"information": 8, "contributions": 7, "methods": 28, "results": 30, "limitations": 10, "related": 10}
        selected = {target: _select(candidates, target, budget, limits[target]) for target, budget in budgets.items()}
        related_exclusions = {
            item.text for target in ("methods", "results", "limitations") for item in selected[target]
        }
        related_pool = _select(candidates, "related", int(800 * scale), 20)
        selected["related"] = []
        related_words = 0
        for item in related_pool:
            item_words = word_count(item.text)
            if item.text in related_exclusions or (
                selected["related"] and related_words + item_words > budgets["related"]
            ):
                continue
            selected["related"].append(item)
            related_words += item_words
            if len(selected["related"]) >= limits["related"]:
                break
        if len(selected["contributions"]) < 4:
            contribution_keys = {item.text for item in selected["contributions"]}
            contribution_fallback = sorted(
                selected["results"],
                key=lambda item: (
                    {"Results": 0, "Discussion": 1, "Conclusion": 2, "Abstract": 3}.get(item.section, 4),
                    item.order,
                ),
            )
            for item in contribution_fallback:
                if item.text not in contribution_keys:
                    selected["contributions"].append(item)
                    contribution_keys.add(item.text)
                if len(selected["contributions"]) >= 7:
                    break
            selected["contributions"].sort(key=lambda item: item.order)
        selected["information"].sort(
            key=lambda item: (
                0 if re.search(r"\b(?:objective|aim|purpose)\b", item.text, re.I) else 1,
                item.order,
            )
        )
        summary_pool = _select(candidates, "results", 100, 3) or _select(candidates, "information", 100, 3)

        info_text = _pack(selected["information"], "Study scope and source availability")
        contributions = "\n".join(
            f"{index}. {item.text}" for index, item in enumerate(selected["contributions"], start=1)
        )
        methodology = _pack(selected["methods"], "Design, data, measurements, and analysis")
        results = _pack(selected["results"], "Primary, secondary, and boundary findings")
        limitations = "\n".join(f"- {item.text}" for item in selected["limitations"])
        related = _pack(selected["related"], "Prior evidence and methodological context")
        glossary = _glossary(bundle.full_text, bundle.metadata.index_keywords)

        warnings: list[str] = []
        for target in ("information", "contributions", "methods", "results", "limitations", "related"):
            if not selected[target]:
                warnings.append(f"No grounded evidence unit was selected for {target}.")
        return ProfileContent(
            one_line_summary=_single_sentence(summary_pool),
            document_information=classification_block(bundle) + "\n\n" + info_text,
            key_contributions=contributions,
            methodology=methodology,
            results=results,
            limitations=limitations,
            related_work=related,
            glossary=glossary,
            warnings=warnings,
            evidence=_evidence(selected),
            retrieval_queries=_queries(bundle, selected),
        )
