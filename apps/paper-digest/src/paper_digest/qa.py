from __future__ import annotations

import re
from dataclasses import asdict
from typing import Any

from .compiler import FRONTMATTER_KEYS, REQUIRED_HEADINGS
from .config import DigestConfig
from .models import ParsedBundle
from .profiles.base import ProfileScore
from .retrieval import run_queries, tokenize
from .text import word_count

PROCESS_MARKERS = [
    "SOURCE_READY",
    "NOT_SOURCE_READY",
    "validator",
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


def _frontmatter(markdown: str) -> tuple[list[str], dict[str, str]]:
    if not markdown.startswith("---\n"):
        return [], {}
    end = markdown.find("\n---\n", 4)
    if end < 0:
        return [], {}
    lines = markdown[4:end].splitlines()
    data: dict[str, str] = {}
    order: list[str] = []
    for line in lines:
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        order.append(key.strip())
        data[key.strip()] = value.strip().strip('"')
    return order, data


def _h2(markdown: str) -> list[str]:
    return [line.strip() for line in markdown.splitlines() if line.startswith("## ")]


def _body(markdown: str) -> str:
    end = markdown.find("\n---\n", 4)
    return markdown[end + 5 :] if end >= 0 else markdown


def _prose_units(body: str) -> list[str]:
    units: list[str] = []
    for block in re.split(r"\n\s*\n", body):
        value = block.strip()
        if not value or value.startswith("#") or value.startswith("|") or value.startswith("---"):
            continue
        if all(
            line.lstrip().startswith(("- ", "1. ", "2. ", "3. ", "4. ", "5. ", "6. ", "7. ", "8. ", "9. "))
            for line in value.splitlines()
            if line.strip()
        ):
            continue
        units.append(value)
    return units


def _normalized_unit(value: str) -> str:
    return " ".join(tokenize(value))


def _duplicate_audit(units: list[str], threshold: float = 0.78) -> dict[str, Any]:
    normalized = [_normalized_unit(unit) for unit in units]
    exact: list[dict[str, int]] = []
    near: list[dict[str, Any]] = []
    seen: dict[str, int] = {}
    token_sets = [set(value.split()) for value in normalized]
    for index, value in enumerate(normalized):
        if value in seen and value:
            exact.append({"first": seen[value] + 1, "duplicate": index + 1})
        else:
            seen[value] = index
    for left in range(len(units)):
        if len(token_sets[left]) < 12:
            continue
        for right in range(left + 1, len(units)):
            if normalized[left] == normalized[right] or len(token_sets[right]) < 12:
                continue
            union = token_sets[left] | token_sets[right]
            similarity = len(token_sets[left] & token_sets[right]) / max(1, len(union))
            if similarity >= threshold:
                near.append({"left": left + 1, "right": right + 1, "jaccard": round(similarity, 4)})
    return {"threshold": threshold, "exact": exact, "near": near}


def evaluate_digest(
    markdown: str,
    bundle: ParsedBundle,
    profile_name: str,
    profile_scores: list[ProfileScore],
    profile_warnings: list[str],
    config: DigestConfig,
    evidence: list[dict[str, object]] | None = None,
    retrieval_queries: list[dict[str, object]] | None = None,
) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = list(profile_warnings)
    checks: dict[str, Any] = {}

    order, fm = _frontmatter(markdown)
    checks["frontmatter_keys"] = order
    if order != FRONTMATTER_KEYS:
        errors.append("Frontmatter does not contain the exact Joonan-compatible 11-key sequence.")
    for key in ("title", "authors", "year", "doi", "category", "pdf_filename"):
        if not fm.get(key):
            errors.append(f"Required frontmatter value is empty: {key}.")

    headings = _h2(markdown)
    checks["h2_headings"] = headings
    if headings != REQUIRED_HEADINGS:
        errors.append("The eight required level-2 headings are missing, duplicated, or out of order.")

    meta = bundle.metadata
    author_count = len(meta.authorship.authors)
    checks["author_count"] = author_count
    if author_count == 0:
        errors.append("No ordered author list was resolved.")
    if author_count <= config.max_authors_full and re.search(r"\bet al\.\b|\.\.\.|…", fm.get("authors", ""), re.I):
        errors.append("The full author list is required for papers at or below the configured author threshold.")
    if meta.authorship.author_count not in {None, author_count}:
        errors.append("Declared author count differs from the resolved ordered author list.")
    if not meta.journal or not (meta.online_date or meta.issue_date or meta.year):
        errors.append("Journal or publication date metadata could not be resolved.")
    if not 2 <= len(meta.research_fields) <= config.field_limit:
        errors.append("Research fields must contain 2-6 editorial labels.")
    if not 6 <= len(meta.index_keywords) <= 15:
        errors.append("Index keywords must contain 6-15 retrieval labels.")

    doc_info = markdown.split("## 1. Document Information", 1)[-1].split("## 2. Key Contributions", 1)[0]
    missing_labels = [label for label in CLASSIFICATION_LABELS if f"**{label}:**" not in doc_info]
    checks["classification_labels_missing"] = missing_labels
    if missing_labels:
        errors.append("Classification metadata is incomplete: " + ", ".join(missing_labels) + ".")

    body = _body(markdown)
    body_words = word_count(body)
    checks["body_words"] = body_words
    if body_words < config.min_body_words:
        errors.append(f"Body is too short for a validated source record ({body_words} words).")
    if body_words > config.hard_max_body_words:
        errors.append(f"Body exceeds the hard density limit ({body_words} words).")
    elif body_words > config.target_body_words[1]:
        warnings.append(f"Body exceeds the preferred density range ({body_words} words).")

    units = _prose_units(body)
    lengths = [word_count(unit) for unit in units]
    checks["prose_units"] = len(units)
    checks["longest_prose_unit_words"] = max(lengths, default=0)
    checks["prose_units_over_soft_limit"] = sum(length > config.paragraph_soft_max_words for length in lengths)
    checks["prose_units_over_hard_limit"] = sum(length > config.paragraph_hard_max_words for length in lengths)
    if any(length > config.paragraph_hard_max_words for length in lengths):
        errors.append("At least one prose unit exceeds the hard retrieval-density limit.")
    elif any(length > config.paragraph_soft_max_words for length in lengths):
        warnings.append("At least one prose unit exceeds the preferred retrieval-density limit.")

    duplicate_audit = _duplicate_audit(units)
    checks["duplicate_audit"] = duplicate_audit
    if duplicate_audit["exact"]:
        errors.append("Exact duplicate prose units were found in the source Markdown.")
    if duplicate_audit["near"]:
        warnings.append("Near-duplicate prose units were found and require density review.")

    lower = body.casefold()
    leaked = [marker for marker in PROCESS_MARKERS if marker.casefold() in lower]
    checks["process_markers"] = leaked
    if leaked:
        errors.append("Processing or placeholder metadata leaked into the source Markdown: " + ", ".join(leaked) + ".")

    numeric_anchors = len(
        re.findall(
            r"(?:\bN\s*=|\bP\s*[=<]|\brg\s*=|\bR\^?2\b|\bR2\b|\bPIP\s*=|\b\d+(?:\.\d+)?%|×\s*10\^?-?\d+|\b\d+\.\d+\b)",
            body,
            re.I,
        )
    )
    checks["quantitative_anchor_count"] = numeric_anchors
    quantitative_categories = {
        "randomized-trial",
        "meta-analysis",
        "prediction-model",
        "psychometrics",
        "gwas",
        "neuroimaging",
        "observational-cohort",
        "case-control",
        "cross-sectional",
    }
    minimum_anchors = 8 if meta.category in quantitative_categories else 3
    checks["minimum_quantitative_anchors"] = minimum_anchors
    if numeric_anchors < minimum_anchors:
        errors.append("Too few quantitative anchors were preserved for a quantitative paper digest.")

    for expected in ("Limitations", "Related Work", "Glossary"):
        if expected.casefold() not in lower:
            errors.append(f"Required scientific boundary content is missing: {expected}.")
    if meta.category in quantitative_categories:
        null_pattern = re.compile(
            r"\b(?:no significant|not significant|did not|does not|no association|null result|failed to|"
            r"was not|were not|cannot|uncertain)\b",
            re.I,
        )
        checks["quantitative_boundary_statement"] = bool(null_pattern.search(body))
        if not checks["quantitative_boundary_statement"]:
            errors.append("No source-grounded null, uncertainty, or quantitative boundary statement was retained.")

    if any("[PARSER_ERROR:" in text for text in bundle.supplements_text.values()):
        errors.append("One or more supplied supplements could not be parsed.")
    if config.fail_on_missing_supplement and len(bundle.files) <= 1:
        errors.append("Strict configuration requires supplementary evidence, but none was supplied.")
    for warning in profile_warnings:
        if warning.startswith("No grounded evidence unit"):
            errors.append(warning)

    retrieval_regression: dict[str, Any] | None = None
    if retrieval_queries:
        retrieval_regression = run_queries(markdown, retrieval_queries, top_k=config.retrieval_top_k)
        ranks = [
            item["first_matching_rank"]
            for item in retrieval_regression["results"]
            if item["first_matching_rank"] is not None
        ]
        retrieval_regression["top3_passed"] = sum(rank <= 3 for rank in ranks)
        retrieval_regression["median_rank"] = sorted(ranks)[len(ranks) // 2] if ranks else None
        checks["retrieval_regression"] = retrieval_regression
        if retrieval_regression["passed"] != retrieval_regression["total"]:
            errors.append("The validated full-question retrieval regression did not pass for every query.")
        elif retrieval_regression["top3_passed"] != retrieval_regression["total"]:
            warnings.append("At least one research question was not answered within the top three chunks.")

    evidence = evidence or []
    checks["evidence_ledger_entries"] = len(evidence)
    checks["evidence_pages"] = sorted({int(item["page_start"]) for item in evidence if item.get("page_start")})
    incomplete_evidence = [
        index + 1
        for index, item in enumerate(evidence)
        if not re.search(r"[.!?][)\]\"'’]*$", str(item.get("statement", "")).strip())
    ]
    caption_evidence = [
        index + 1
        for index, item in enumerate(evidence)
        if re.search(
            r"(?:^this figure\b|^the (?:black|dashed|solid|red|blue|horizontal|vertical) line\b|"
            r"^error bars?\b|^venn diagrams? depicting\b|included in this figure\b)",
            str(item.get("statement", "")).strip(),
            re.I,
        )
    ]
    checks["incomplete_evidence_statements"] = incomplete_evidence
    checks["caption_evidence_statements"] = caption_evidence
    authorship_evidence = [
        index + 1
        for index, item in enumerate(evidence)
        if re.search(r"credit authorship contribution statement", str(item.get("statement", "")), re.I)
    ]
    fused_subheading_evidence = [
        index + 1
        for index, item in enumerate(evidence)
        if re.search(
            r"(?:^|[.!?]\s+)[A-Z][A-Za-z0-9-]*(?:\s+[A-Za-z][A-Za-z0-9-]*){1,9}\s+"
            r"(?i:analysis|analyses|correlation|disorders|genes|heritability|oc|overlap|pathways|results)\s+"
            r"(?=[A-Z])",
            str(item.get("statement", "")),
        )
    ]
    checks["authorship_evidence_statements"] = authorship_evidence
    checks["fused_subheading_evidence_statements"] = fused_subheading_evidence
    checks["soft_hyphen_count"] = body.count("\u00ad")
    if len(evidence) < 12:
        errors.append("Too few page-grounded evidence units were retained in the QA ledger.")
    if incomplete_evidence:
        errors.append("One or more selected evidence statements end at an incomplete PDF text boundary.")
    if caption_evidence:
        errors.append("Figure-caption layout fragments leaked into selected scientific evidence.")
    if authorship_evidence:
        errors.append("Publisher authorship boilerplate leaked into selected scientific evidence.")
    if fused_subheading_evidence:
        errors.append("Publisher subheadings remain fused to selected scientific evidence.")
    if checks["soft_hyphen_count"]:
        errors.append("Soft-hyphen extraction artifacts remain in the source Markdown.")

    # Weighted score is descriptive; every hard error remains fail-closed.
    weights = {
        "schema": 0.18,
        "metadata": 0.17,
        "authors": 0.10,
        "content": 0.20,
        "quantitative": 0.15,
        "density": 0.10,
        "evidence": 0.10,
    }
    components = {
        "schema": float(order == FRONTMATTER_KEYS and headings == REQUIRED_HEADINGS),
        "metadata": float(
            bool(meta.journal and meta.year and len(meta.research_fields) >= 2 and len(meta.index_keywords) >= 6)
        ),
        "authors": float(author_count > 0 and meta.authorship.author_count in {None, author_count}),
        "content": float(
            all(
                term in lower
                for term in (
                    "key contributions",
                    "methodology",
                    "key results",
                    "limitations",
                    "related work",
                    "glossary",
                )
            )
        ),
        "quantitative": min(1.0, numeric_anchors / 20),
        "density": float(
            config.min_body_words <= body_words <= config.hard_max_body_words
            and max(lengths, default=0) <= config.paragraph_hard_max_words
        ),
        "evidence": float(
            len(evidence) >= 12 and not any("[PARSER_ERROR:" in text for text in bundle.supplements_text.values())
        ),
    }
    if retrieval_regression is not None:
        components["content"] = float(
            components["content"]
            and retrieval_regression is not None
            and retrieval_regression["passed"] == retrieval_regression["total"]
        )
    score = sum(weights[key] * components[key] for key in weights)
    if errors:
        score = min(score, max(0.0, config.source_ready_threshold - 0.01))
    checks["score_components"] = components
    source_ready = not errors and score >= config.source_ready_threshold
    return {
        "source_ready": source_ready,
        "quality_score": round(score, 4),
        "threshold": config.source_ready_threshold,
        "profile": profile_name,
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
        "evidence_ledger": evidence,
    }
