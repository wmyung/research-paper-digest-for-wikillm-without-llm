"""Fail-closed quality assurance.

Every check is a small function over a :class:`QAContext` returning errors,
warnings and recorded measurements. Adding a diagnostic means appending to
``CHECKS``; nothing else has to change. Errors are fail-closed: any error makes
the record NOT_SOURCE_READY regardless of the weighted score.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .compiler import FRONTMATTER_KEYS, REQUIRED_HEADINGS
from .config import DigestConfig
from .documents import PROFILES_BY_KEY
from .grounding import audit as grounding_audit
from .grounding import prose_sentences
from .models import ParsedBundle
from .profiles.base import ProfileScore
from .retrieval import run_queries, tokenize
from .text import split_sentences, word_count

PROCESS_MARKERS = [
    "SOURCE_READY",
    "NOT_SOURCE_READY",
    "retrieval regression",
    "processing log",
    "agent name",
    "batch id",
    "PARSER_ERROR",
    "TODO",
    "TBD",
    "PLACEHOLDER",
]
CLASSIFICATION_LABELS = [
    "Journal",
    "Publication date",
    "Article type",
    "Author count",
    "Author notes",
    "Research fields (editorial)",
    "Index keywords (editorial)",
]
QUANTITATIVE_CATEGORIES = {
    "randomized-trial",
    "meta-analysis",
    "prediction-model",
    "psychometrics",
    "gwas",
    "neuroimaging",
    "observational-cohort",
    "case-control",
    "cross-sectional",
    "diagnostic-accuracy",
    "economic-evaluation",
}
# Document types that legitimately carry little or no numeric evidence.
QUALITATIVE_PROFILES = {
    "guideline_consensus",
    "editorial_commentary",
    "narrative_review",
    "letter_response_correspondence",
    "study_protocol",
    "case_report",
    "excluded_non_paper",
}
# Statistical anchors are effect sizes and test statistics; numeric anchors are
# any figure a reader could check, which is the right bar for a guideline or an
# editorial that reports counts rather than estimates.
STATISTICAL_ANCHOR_RE = re.compile(
    r"(?:\bN\s*=|\bn\s*=|\bP\s*[=<]|\brg\s*=|\bR\^?2\b|\bR2\b|\bPIP\s*=|\b\d+(?:\.\d+)?%|"
    r"×\s*10\^?-?\d+|\b\d+\.\d+\b|\b95\s*%\s*CI|\b(?:OR|HR|RR|aOR|aHR|SMD|IRR|AUC)\b\s*[=:(])",
    re.I,
)
NUMERIC_ANCHOR_RE = re.compile(r"(?<![A-Za-z0-9.-])\d{1,6}(?:\.\d+)?(?:%|-item|-day|-member)?(?![A-Za-z0-9])")
CITATION_NUMBER_RE = re.compile(r"\[[0-9][0-9,\s–-]*\]")
TABLE_LEAK_RE = re.compile(
    r"^(?:Specify|Describe|Present|Provide|Report|List|Identify|Indicate|State)\b\s+[a-z]|"
    r"\b\d+[a-z]?\s+(?:Specify|Describe|Present|Provide|Report|List)\b",
)


@dataclass(slots=True)
class QAContext:
    markdown: str
    bundle: ParsedBundle
    config: DigestConfig
    profile_name: str
    profile_scores: list[ProfileScore]
    profile_warnings: list[str]
    evidence: list[dict[str, Any]]
    retrieval_queries: list[dict[str, Any]]
    coverage: dict[str, Any]
    document_profile: str
    metadata_ledger: list[dict[str, Any]]
    section_capacity: dict[str, int] = field(default_factory=dict)
    authored: list[str] = field(default_factory=list)
    frontmatter_order: list[str] = field(default_factory=list)
    frontmatter: dict[str, str] = field(default_factory=dict)
    headings: list[str] = field(default_factory=list)
    body: str = ""
    body_words: int = 0
    prose_units: list[str] = field(default_factory=list)


@dataclass(slots=True)
class CheckResult:
    name: str
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    measurements: dict[str, Any] = field(default_factory=dict)
    components: dict[str, float] = field(default_factory=dict)


def _frontmatter(markdown: str) -> tuple[list[str], dict[str, str]]:
    if not markdown.startswith("---\n"):
        return [], {}
    end = markdown.find("\n---\n", 4)
    if end < 0:
        return [], {}
    data: dict[str, str] = {}
    order: list[str] = []
    for line in markdown[4:end].splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        order.append(key.strip())
        data[key.strip()] = value.strip().strip('"')
    return order, data


def _body(markdown: str) -> str:
    end = markdown.find("\n---\n", 4)
    return markdown[end + 5 :] if end >= 0 else markdown


def _prose_units(body: str) -> list[str]:
    units: list[str] = []
    for block in re.split(r"\n\s*\n", body):
        value = block.strip()
        if not value or value.startswith(("#", "|", "---")):
            continue
        if all(
            line.lstrip().startswith(("- ", *(f"{n}. " for n in range(1, 10))))
            for line in value.splitlines()
            if line.strip()
        ):
            continue
        units.append(value)
    return units


def _normalised(value: str) -> str:
    return " ".join(tokenize(value))


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------


def check_schema(context: QAContext) -> CheckResult:
    result = CheckResult("schema")
    result.measurements["frontmatter_keys"] = context.frontmatter_order
    result.measurements["h2_headings"] = context.headings
    if context.frontmatter_order != FRONTMATTER_KEYS:
        result.errors.append("Frontmatter does not contain the exact WikiLLM-compatible 11-key sequence.")
    for key in ("title", "authors", "year", "doi", "category", "pdf_filename"):
        if not context.frontmatter.get(key):
            result.errors.append(f"Required frontmatter value is empty: {key}.")
    if context.headings != REQUIRED_HEADINGS:
        result.errors.append("The eight required level-2 headings are missing, duplicated, or out of order.")
    result.components["schema"] = float(
        context.frontmatter_order == FRONTMATTER_KEYS and context.headings == REQUIRED_HEADINGS
    )
    return result


def check_metadata(context: QAContext) -> CheckResult:
    result = CheckResult("metadata")
    meta = context.bundle.metadata
    if not meta.journal:
        result.errors.append("The journal or publication venue could not be resolved.")
    if not (meta.publication_date or meta.online_date or meta.issue_date or meta.year):
        result.errors.append("No publication date or year could be resolved.")
    if not 2 <= len(meta.research_fields) <= context.config.field_limit:
        result.errors.append("Research fields must contain 2-6 editorial labels.")
    if not 6 <= len(meta.index_keywords) <= 15:
        result.errors.append("Index keywords must contain 6-15 retrieval labels.")
    doc_info = context.markdown.split("## 1. Document Information", 1)[-1].split("## 2. Key Contributions", 1)[0]
    missing = [label for label in CLASSIFICATION_LABELS if f"**{label}:**" not in doc_info]
    result.measurements["classification_labels_missing"] = missing
    if missing:
        result.errors.append("Classification metadata is incomplete: " + ", ".join(missing) + ".")
    resolved = [entry["field"] for entry in context.metadata_ledger]
    result.measurements["metadata_fields_with_evidence"] = sorted(resolved)
    for field_name in ("title", "authors", "doi"):
        if field_name not in resolved:
            result.warnings.append(f"No source evidence was recorded for the {field_name} field.")
    if meta.publication_date_label and meta.publication_date_label != "online_published":
        result.warnings.append(
            f"Publication date resolved from the '{meta.publication_date_label}' field; "
            "no online-publication date was printed in the source."
        )
    result.components["metadata"] = float(
        bool(meta.journal and meta.year and len(meta.research_fields) >= 2 and len(meta.index_keywords) >= 6)
    )
    return result


COMPACT_AUTHOR_RE = re.compile(r"\bet al\.?\b|\.\.\.|…|additional authors?|remaining authors?", re.I)


def check_authors(context: QAContext) -> CheckResult:
    result = CheckResult("authors")
    meta = context.bundle.metadata
    count = len(meta.authorship.authors)
    rendered = context.frontmatter.get("authors", "")
    compacted = bool(COMPACT_AUTHOR_RE.search(rendered))
    result.measurements["author_count"] = count
    result.measurements["author_list_compacted"] = compacted
    # The complete extracted list always survives in the sidecar, even when the
    # frontmatter is compacted.
    result.measurements["full_author_list"] = list(meta.authorship.authors)
    if count == 0:
        result.errors.append("No ordered author list was resolved.")
    if count <= context.config.max_authors_full and compacted:
        result.errors.append(
            "Manageable author list is compacted: papers with "
            f"{context.config.max_authors_full} or fewer named authors must list every author."
        )
    if compacted and count > context.config.max_authors_full:
        note = meta.authorship.representation_note
        if not re.search(r"compact|mega|consortium|full list|sidecar|QA", note, re.I):
            result.errors.append("A compacted mega-authorship list must state the representation rule in Author notes.")
    if meta.authorship.author_count not in {None, count}:
        result.errors.append("Declared author count differs from the resolved ordered author list.")
    if meta.authorship.representation_note and "Mega-authorship" not in meta.authorship.representation_note:
        result.warnings.append("The source byline is truncated with 'et al.'; the author list is incomplete.")
    result.components["authors"] = float(count > 0 and meta.authorship.author_count in {None, count})
    return result


def check_pdf_path(context: QAContext) -> CheckResult:
    """The record must point at a canonical PDF that shares its filename stem."""
    result = CheckResult("pdf_path")
    pdf_path = context.frontmatter.get("pdf_path", "")
    pdf_filename = context.frontmatter.get("pdf_filename", "")
    markdown_stem = Path(context.frontmatter.get("pdf_filename", "x.pdf")).stem
    result.measurements["pdf_path"] = pdf_path
    if pdf_path and Path(pdf_path).name != pdf_filename:
        result.errors.append("pdf_path and pdf_filename disagree; the canonical PDF is ambiguous.")
    if context.config.verify_pdf_path:
        if not pdf_path or not Path(pdf_path).is_file():
            result.errors.append(f"Canonical PDF is not present at the declared pdf_path: {pdf_path or '(empty)'}.")
        else:
            result.measurements["pdf_path_verified"] = True
    elif pdf_path and not Path(pdf_path).is_file():
        result.warnings.append(
            "pdf_path does not resolve on this machine; set --pdf-path to the repository location "
            "and re-run with --verify-pdf-path before ingestion."
        )
    result.measurements["stem"] = markdown_stem
    return result


def check_density(context: QAContext) -> CheckResult:
    result = CheckResult("density")
    config = context.config
    source_words = word_count(context.bundle.full_text)
    # A short source cannot yield a long record; scale the floor to the source
    # rather than failing every short paper against a fixed absolute minimum.
    floor = max(400, min(config.min_body_words, int(source_words * 0.12)))
    result.measurements["source_words"] = source_words
    result.measurements["body_words"] = context.body_words
    result.measurements["min_body_words_applied"] = floor
    ratio = context.body_words / source_words if source_words else 0.0
    result.measurements["digest_to_source_ratio"] = round(ratio, 4)
    if context.body_words < floor:
        result.errors.append(
            f"Body is too short for a validated source record ({context.body_words} words, floor {floor})."
        )
    if context.body_words > config.hard_max_body_words:
        result.errors.append(f"Body exceeds the hard density limit ({context.body_words} words).")
    elif context.body_words > config.target_body_words[1]:
        result.warnings.append(f"Body exceeds the preferred density range ({context.body_words} words).")
    if source_words and not 0.05 <= ratio <= 0.8:
        result.warnings.append(
            f"Digest-to-source ratio {ratio:.2f} sits outside the 0.05-0.80 band expected of a source record."
        )
    lengths = [word_count(unit) for unit in context.prose_units]
    result.measurements["prose_units"] = len(context.prose_units)
    result.measurements["longest_prose_unit_words"] = max(lengths, default=0)
    result.measurements["prose_units_over_soft_limit"] = sum(
        length > config.paragraph_soft_max_words for length in lengths
    )
    if any(length > config.paragraph_hard_max_words for length in lengths):
        result.errors.append("At least one prose unit exceeds the hard retrieval-density limit.")
    elif any(length > config.paragraph_soft_max_words for length in lengths):
        result.warnings.append("At least one prose unit exceeds the preferred retrieval-density limit.")
    result.components["density"] = float(
        floor <= context.body_words <= config.hard_max_body_words
        and max(lengths, default=0) <= config.paragraph_hard_max_words
    )
    return result


# Digest target -> the heading it is rendered under.
SECTION_HEADINGS = {
    "summary": "## One-line Summary",
    "information": "## 1. Document Information",
    "contributions": "## 2. Key Contributions",
    "methods": "## 3. Methodology and Architecture",
    "results": "## 4. Key Results and Benchmarks",
    "limitations": "## 5. Limitations and Future Work",
    "related": "## 6. Related Work",
    "glossary": "## 7. Glossary",
}


def _sections(markdown: str) -> dict[str, str]:
    body = _body(markdown)
    parts = re.split(r"(?m)^(## .+)$", body)
    return {parts[index].strip(): parts[index + 1] for index in range(1, len(parts) - 1, 2)}


def check_section_density(context: QAContext) -> CheckResult:
    """Each section must carry its own weight, not just the body as a whole.

    A section below its floor is an error when the source could have supplied
    the words and a warning when it could not: a three-page guideline has no
    300-word methods passage to quote, and saying so is the honest outcome.
    """
    result = CheckResult("section_density")
    sections = _sections(context.markdown)
    floors = context.config.section_min_words
    applicable = PROFILES_BY_KEY.get(context.document_profile)
    counts: dict[str, int] = {}
    shortfalls: dict[str, dict[str, int]] = {}
    # A glossary that already lists every term the source defines is complete
    # even when those definitions are short; padding it would mean inventing
    # glosses the paper never wrote.
    glossary = sections.get("## 7. Glossary", "")
    glossary_entry_count = len(re.findall(r"(?m)^[-*+]\s+", glossary))
    authored_sentences = {sentence.casefold() for sentence in context.authored}
    glossary_source_exhausted = any(
        marker in glossary.casefold() and any(marker in sentence for sentence in authored_sentences)
        for marker in (
            "the source states no further defined terms.",
            "the source states no defined terms or expanded acronyms.",
        )
    )
    for target, heading in SECTION_HEADINGS.items():
        floor = floors.get(target, 0)
        words = word_count(sections.get(heading, ""))
        counts[heading] = words
        if words >= floor:
            continue
        if applicable is not None and target not in applicable.applicable_targets and target != "glossary":
            continue
        capacity = context.section_capacity.get(target)
        if target == "glossary":
            shortfalls[heading] = {"words": words, "floor": floor, "entries": glossary_entry_count}
            if glossary_entry_count >= context.config.min_glossary_entries or glossary_source_exhausted:
                result.warnings.append(
                    f"{heading} has {words} words against a {floor}-word floor, but lists "
                    f"{glossary_entry_count} entries and records that the source defines no more terms."
                )
            else:
                result.errors.append(f"Section is underdeveloped: {heading} has {words} words; minimum is {floor}.")
            continue
        shortfalls[heading] = {"words": words, "floor": floor, "source_capacity": capacity or 0}
        if capacity is not None and capacity < floor:
            result.warnings.append(
                f"{heading} has {words} words against a {floor}-word floor; the source offers only "
                f"about {capacity} quotable words for this section, so the shortfall is in the paper."
            )
        else:
            result.errors.append(f"Section is underdeveloped: {heading} has {words} words; minimum is {floor}.")
    result.measurements["section_word_counts"] = counts
    result.measurements["section_shortfalls"] = shortfalls

    document_information = counts.get("## 1. Document Information", 0)
    if document_information > context.config.max_document_information_words:
        result.errors.append("Document Information is audit-heavy rather than retrieval-native.")

    contributions = sections.get("## 2. Key Contributions", "")
    items = re.findall(r"(?m)^(?:\d+\.|[-*+])\s+", contributions)
    result.measurements["contribution_items"] = len(items)
    if not context.config.min_contribution_items <= len(items) <= context.config.max_contribution_items:
        result.errors.append(
            f"Key Contributions must contain {context.config.min_contribution_items}-"
            f"{context.config.max_contribution_items} explicit items; found {len(items)}."
        )

    glossary_entries = re.findall(r"(?m)^[-*+]\s+", glossary)
    result.measurements["glossary_entries"] = len(glossary_entries)
    result.measurements["glossary_source_exhausted"] = glossary_source_exhausted
    if len(glossary_entries) < context.config.min_glossary_entries:
        if glossary_source_exhausted:
            result.warnings.append(
                f"Glossary has {len(glossary_entries)} entries because the source defines no additional terms."
            )
        else:
            result.errors.append(
                f"Glossary must contain at least {context.config.min_glossary_entries} entries; "
                f"found {len(glossary_entries)}."
            )

    summary = sections.get("## One-line Summary", "").strip()
    summary_words = word_count(summary)
    result.measurements["one_line_summary_words"] = summary_words
    if re.search(r"(?m)^[-*+] |^\d+\. ", summary) or len(re.split(r"\n\s*\n", summary)) != 1:
        result.errors.append("One-line Summary must be a single prose paragraph without a list.")
    if summary_words > 140:
        result.errors.append("One-line Summary exceeds 140 words and is no longer a one-line digest.")
    elif not 30 <= summary_words <= 100:
        result.warnings.append(f"One-line Summary has {summary_words} words; the retrieval-density target is 30-100.")
    result.components["section_density"] = 0.0 if result.errors else (1.0 if not shortfalls else 0.75)
    return result


def check_duplication(context: QAContext) -> CheckResult:
    result = CheckResult("duplication")
    units = context.prose_units
    normalised = [_normalised(unit) for unit in units]
    token_sets = [set(value.split()) for value in normalised]
    exact: list[dict[str, int]] = []
    near: list[dict[str, Any]] = []
    seen: dict[str, int] = {}
    for index, value in enumerate(normalised):
        if value and value in seen:
            exact.append({"first": seen[value] + 1, "duplicate": index + 1})
        else:
            seen[value] = index
    for left in range(len(units)):
        if len(token_sets[left]) < 12:
            continue
        for right in range(left + 1, len(units)):
            if normalised[left] == normalised[right] or len(token_sets[right]) < 12:
                continue
            similarity = len(token_sets[left] & token_sets[right]) / max(1, len(token_sets[left] | token_sets[right]))
            if similarity >= 0.78:
                near.append({"left": left + 1, "right": right + 1, "jaccard": round(similarity, 4)})
    # Repeated sentences across sections waste retrieval budget even when the
    # containing paragraphs differ.
    sentences = prose_sentences(context.markdown)
    counts: dict[str, int] = {}
    for sentence in sentences:
        key = _normalised(sentence)
        if len(key.split()) >= 8:
            counts[key] = counts.get(key, 0) + 1
    repeated = sorted(key for key, count in counts.items() if count > 1)
    result.measurements["duplicate_audit"] = {"exact": exact, "near": near, "repeated_sentences": len(repeated)}
    if exact:
        result.errors.append("Exact duplicate prose units were found in the source Markdown.")
    if repeated:
        result.errors.append(f"{len(repeated)} sentence(s) are repeated across digest sections.")
    if near:
        result.warnings.append("Near-duplicate prose units were found and require density review.")
    return result


def check_process_leak(context: QAContext) -> CheckResult:
    result = CheckResult("process_leak")
    lower = context.body.casefold()
    leaked = [marker for marker in PROCESS_MARKERS if marker.casefold() in lower]
    result.measurements["process_markers"] = leaked
    if leaked:
        result.errors.append("Processing or placeholder metadata leaked into the Markdown: " + ", ".join(leaked) + ".")
    result.measurements["soft_hyphen_count"] = context.body.count("­")
    if result.measurements["soft_hyphen_count"]:
        result.errors.append("Soft-hyphen extraction artifacts remain in the source Markdown.")
    table_leaks = [sentence for sentence in prose_sentences(context.markdown) if TABLE_LEAK_RE.search(sentence)]
    result.measurements["table_row_leaks"] = table_leaks[:5]
    if table_leaks:
        result.errors.append(f"{len(table_leaks)} checklist or table row(s) leaked into the digest prose.")
    return result


def check_quantitative(context: QAContext) -> CheckResult:
    result = CheckResult("quantitative")
    meta = context.bundle.metadata
    prose = CITATION_NUMBER_RE.sub(" ", context.body)
    statistical = len(STATISTICAL_ANCHOR_RE.findall(prose))
    numeric = len(NUMERIC_ANCHOR_RE.findall(prose))
    result.measurements["statistical_anchor_count"] = statistical
    result.measurements["quantitative_anchor_count"] = numeric
    if context.document_profile in QUALITATIVE_PROFILES:
        anchors, minimum, kind = numeric, 4, "numeric"
    elif meta.category in QUANTITATIVE_CATEGORIES:
        anchors, minimum, kind = statistical, 8, "statistical"
    else:
        anchors, minimum, kind = statistical, 3, "statistical"
    result.measurements["minimum_quantitative_anchors"] = minimum
    if anchors < minimum:
        result.errors.append(
            f"Too few {kind} anchors were preserved ({anchors} < {minimum}) for a "
            f"{meta.category} {context.document_profile} record."
        )
    if meta.category in QUANTITATIVE_CATEGORIES and context.document_profile not in QUALITATIVE_PROFILES:
        boundary = re.compile(
            r"\b(?:no significant|not significant|did not|does not|no association|null result|failed to|"
            r"was not|were not|cannot|could not|uncertain|limitation)\b",
            re.I,
        )
        present = bool(boundary.search(context.body))
        result.measurements["quantitative_boundary_statement"] = present
        if not present:
            result.errors.append("No source-grounded null, uncertainty, or boundary statement was retained.")
    result.components["quantitative"] = min(1.0, anchors / max(4.0, minimum * 2.0))
    return result


def check_numeric_consistency(context: QAContext) -> CheckResult:
    """Headline numbers in the abstract should reappear in the body or tables."""
    result = CheckResult("numeric_consistency")
    abstract = context.bundle.metadata.abstract
    if not abstract:
        result.measurements["abstract_numbers_checked"] = 0
        return result
    rest = context.bundle.grounding_text.replace(abstract, " ")
    numbers = {
        match.group(0)
        for match in re.finditer(r"(?<![A-Za-z0-9.])\d{1,4}(?:\.\d+)?%?(?![A-Za-z0-9])", abstract)
        if not re.fullmatch(r"(?:19|20)\d{2}", match.group(0))
    }
    unmatched = sorted(number for number in numbers if number not in rest)
    result.measurements["abstract_numbers_checked"] = len(numbers)
    result.measurements["abstract_numbers_unmatched"] = unmatched[:12]
    if unmatched:
        result.warnings.append(
            f"{len(unmatched)} headline number(s) in the abstract do not reappear elsewhere in the source; "
            "cross-check against the tables before relying on them."
        )
    return result


def check_grounding(context: QAContext) -> CheckResult:
    """Every emitted sentence must be a verbatim span of the extracted source."""
    result = CheckResult("grounding")
    # An authored note may span several sentences; compare sentence by sentence.
    authored = {_normalised(part) for note in context.authored for part in split_sentences(note) or [note]}
    quoted = [sentence for sentence in prose_sentences(context.markdown) if _normalised(sentence) not in authored]
    audit = grounding_audit(quoted, context.bundle.grounding_text or context.bundle.full_text)
    audit["authored_sentences"] = len(context.authored)
    result.measurements["grounding"] = audit
    if audit["ungrounded_count"]:
        result.errors.append(
            f"{audit['ungrounded_count']} digest sentence(s) are not verbatim spans of the extracted source."
        )
    result.components["grounding"] = float(audit["ratio"])
    return result


def check_coverage(context: QAContext) -> CheckResult:
    result = CheckResult("coverage")
    coverage = context.coverage or {}
    slots = coverage.get("slots", [])
    absent = [slot["id"] for slot in slots if slot["status"] == "absent_in_source"]
    unchecked = [slot["id"] for slot in slots if slot["status"] == "unchecked"]
    result.measurements["coverage_ratio"] = coverage.get("coverage_ratio", 0.0)
    result.measurements["absent_required_slots"] = absent
    if unchecked:
        result.errors.append("Evidence coverage ledger contains unchecked slots: " + ", ".join(unchecked) + ".")
    for slot_id in absent:
        result.warnings.append(f"Required evidence slot absent from the source: {slot_id}.")
    ratio = float(coverage.get("coverage_ratio", 0.0) or 0.0)
    if ratio < 0.5 and slots:
        result.errors.append(
            f"Only {ratio:.0%} of the applicable evidence slots for the "
            f"{coverage.get('document_profile')} profile are covered by the source."
        )
    result.components["coverage"] = ratio
    return result


def check_content(context: QAContext) -> CheckResult:
    result = CheckResult("content")
    lower = context.body.casefold()
    required_terms = ("key contributions", "methodology", "key results", "limitations", "related work", "glossary")
    present = all(term in lower for term in required_terms)
    for expected in ("Limitations", "Related Work", "Glossary"):
        if expected.casefold() not in lower:
            result.errors.append(f"Required scientific boundary content is missing: {expected}.")
    relational = [
        int(item.get("relational_score", 0))
        for item in context.evidence
        if item.get("target") in {"results", "contributions"}
    ]
    strong = sum(1 for value in relational if value >= 3)
    result.measurements["relational_units"] = len(relational)
    result.measurements["self_contained_units"] = strong
    if relational and strong / len(relational) < 0.4:
        result.warnings.append(
            "Fewer than 40% of result and contribution units name an entity, population, comparison, "
            "direction and magnitude; retrieval answers may need their neighbours for context."
        )
    result.components["content"] = float(present)
    return result


def check_supplements(context: QAContext) -> CheckResult:
    result = CheckResult("supplements")
    if any("[PARSER_ERROR:" in text for text in context.bundle.supplements_text.values()):
        result.errors.append("One or more supplied supplements could not be parsed.")
    if context.config.fail_on_missing_supplement and len(context.bundle.files) <= 1:
        result.errors.append("Strict configuration requires supplementary evidence, but none was supplied.")
    for warning in context.profile_warnings:
        if warning.startswith("No grounded evidence unit"):
            result.errors.append(warning)
        else:
            result.warnings.append(warning)
    return result


def check_evidence(context: QAContext) -> CheckResult:
    result = CheckResult("evidence")
    evidence = context.evidence
    result.measurements["evidence_ledger_entries"] = len(evidence)
    result.measurements["evidence_pages"] = sorted(
        {int(item["page_start"]) for item in evidence if item.get("page_start")}
    )
    incomplete = [
        index + 1
        for index, item in enumerate(evidence)
        if not re.search(r"[.!?][)\]\"'’”]*$", str(item.get("statement", "")).strip())
    ]
    result.measurements["incomplete_evidence_statements"] = incomplete
    if len(evidence) < 10:
        result.errors.append("Too few page-grounded evidence units were retained in the QA ledger.")
    if incomplete:
        result.errors.append("One or more selected evidence statements end at an incomplete text boundary.")
    result.components["evidence"] = float(
        len(evidence) >= 10 and not any("[PARSER_ERROR:" in text for text in context.bundle.supplements_text.values())
    )
    return result


def check_retrieval(context: QAContext) -> CheckResult:
    result = CheckResult("retrieval")
    if not context.retrieval_queries:
        return result
    regression = run_queries(context.markdown, context.retrieval_queries, top_k=context.config.retrieval_top_k)
    ranks = [item["first_matching_rank"] for item in regression["results"] if item["first_matching_rank"] is not None]
    regression["top3_passed"] = sum(rank <= 3 for rank in ranks)
    regression["median_rank"] = sorted(ranks)[len(ranks) // 2] if ranks else None
    result.measurements["retrieval_regression"] = regression
    if regression["passed"] != regression["total"]:
        result.errors.append("The validated full-question retrieval regression did not pass for every query.")
    elif regression["top3_passed"] != regression["total"]:
        result.warnings.append("At least one research question was not answered within the top three chunks.")
    result.components["retrieval"] = regression["passed"] / max(1, regression["total"])
    return result


CHECKS: tuple[Callable[[QAContext], CheckResult], ...] = (
    check_schema,
    check_metadata,
    check_authors,
    check_pdf_path,
    check_density,
    check_section_density,
    check_duplication,
    check_process_leak,
    check_quantitative,
    check_numeric_consistency,
    check_grounding,
    check_coverage,
    check_content,
    check_supplements,
    check_evidence,
    check_retrieval,
)

WEIGHTS = {
    "schema": 0.12,
    "metadata": 0.11,
    "authors": 0.06,
    "content": 0.11,
    "quantitative": 0.09,
    "density": 0.05,
    "section_density": 0.07,
    "evidence": 0.07,
    "grounding": 0.16,
    "coverage": 0.10,
    "retrieval": 0.06,
}
assert abs(sum(WEIGHTS.values()) - 1.0) < 1e-9, "quality-score weights must sum to 1"


def evaluate_digest(
    markdown: str,
    bundle: ParsedBundle,
    profile_name: str,
    profile_scores: list[ProfileScore],
    profile_warnings: list[str],
    config: DigestConfig,
    evidence: list[dict[str, object]] | None = None,
    retrieval_queries: list[dict[str, object]] | None = None,
    coverage: dict[str, Any] | None = None,
    document_profile: str = "empirical_research",
    metadata_ledger: list[dict[str, Any]] | None = None,
    section_capacity: dict[str, int] | None = None,
    authored: list[str] | None = None,
) -> dict[str, Any]:
    order, frontmatter = _frontmatter(markdown)
    body = _body(markdown)
    context = QAContext(
        markdown=markdown,
        bundle=bundle,
        config=config,
        profile_name=profile_name,
        profile_scores=profile_scores,
        profile_warnings=list(profile_warnings),
        evidence=list(evidence or []),
        retrieval_queries=list(retrieval_queries or []),
        coverage=coverage or {},
        document_profile=document_profile,
        metadata_ledger=list(metadata_ledger or []),
        section_capacity=dict(section_capacity or {}),
        authored=list(authored or []),
        frontmatter_order=order,
        frontmatter=frontmatter,
        headings=[line.strip() for line in markdown.splitlines() if line.startswith("## ")],
        body=body,
        body_words=word_count(body),
        prose_units=_prose_units(body),
    )

    errors: list[str] = []
    warnings: list[str] = []
    checks: dict[str, Any] = {}
    components: dict[str, float] = {}
    for check in CHECKS:
        outcome = check(context)
        errors.extend(outcome.errors)
        warnings.extend(outcome.warnings)
        checks.update(outcome.measurements)
        components.update(outcome.components)
        checks.setdefault("check_status", {})[outcome.name] = "fail" if outcome.errors else "pass"

    # The published score is clamped so a failing record can never read as
    # nearly certified, which also collapses every failing record onto one
    # value. The unclamped score is reported alongside it because triage and
    # the repair stage need a signal that still moves while errors remain.
    raw_score = sum(weight * components.get(key, 0.0) for key, weight in WEIGHTS.items())
    score = min(raw_score, max(0.0, config.source_ready_threshold - 0.01)) if errors else raw_score
    checks["score_components"] = components
    return {
        "source_ready": not errors and score >= config.source_ready_threshold,
        "quality_score": round(score, 4),
        "raw_quality_score": round(raw_score, 4),
        "threshold": config.source_ready_threshold,
        "profile": profile_name,
        "document_profile": document_profile,
        "profile_scores": [asdict(item) for item in profile_scores],
        "errors": errors,
        "warnings": sorted(set(warnings)),
        "checks": checks,
        "input_inventory": [
            {
                "name": item.path.name,
                "role": item.role,
                "media_type": item.media_type,
                "bytes": item.size_bytes,
                "sha256": item.sha256,
                "pages": item.page_count,
                "sheets": item.sheet_count,
                "note": item.note,
            }
            for item in bundle.files
        ],
        "coverage": {
            "canonical_pdf_pages": next(
                (item.page_count for item in bundle.files if item.role == "canonical-paper"), None
            ),
            "supplement_pdf_pages": sum(
                item.page_count or 0
                for item in bundle.files
                if item.role == "supplement" and item.media_type == "application/pdf"
            ),
            "workbook_sheets": len(bundle.workbooks),
            "parsed_supplement_documents": len(bundle.supplements_text),
            "ocr_pages": bundle.ocr_pages,
            "figure_captions_detected": bundle.figure_caption_count,
            "table_captions_detected": bundle.table_caption_count,
        },
        "evidence_ledger": context.evidence,
        "metadata_ledger": context.metadata_ledger,
        "coverage_ledger": context.coverage,
    }
