"""Evidence ledgers.

Two records are produced next to the Markdown:

* a metadata ledger — for each bibliographic field, the value, its source, the
  page it was read from and a verbatim excerpt;
* a coverage ledger — for each evidence slot of the resolved document profile,
  whether the source covers it, and where.

Neither invents content. A slot with no matching source text is reported as
absent, which is the honest outcome for a rule-based system.
"""

from __future__ import annotations

import re
from dataclasses import asdict
from typing import Any

from .documents import DocumentProfile, EvidenceSlot
from .models import ParsedBundle
from .text import normalize_prose, word_count


def metadata_ledger(bundle: ParsedBundle) -> list[dict[str, Any]]:
    metadata = bundle.metadata
    entries: list[dict[str, Any]] = []
    for field, evidence in metadata.evidence.items():
        entries.append(
            {
                "field": field,
                "value": evidence.value,
                "source": evidence.source,
                "page": evidence.page,
                "source_excerpt": evidence.source_excerpt,
            }
        )
    return sorted(entries, key=lambda item: item["field"])


def _slot_hits(bundle: ParsedBundle, slot: EvidenceSlot, limit: int = 3) -> list[dict[str, Any]]:
    wanted = set(slot.sections) if slot.sections else None
    hits: list[dict[str, Any]] = []
    for name, section in bundle.sections.items():
        if wanted is not None and name not in wanted:
            continue
        for paragraph in section.paragraphs:
            for pattern in slot.patterns:
                match = re.search(pattern, paragraph.text, re.I)
                if not match:
                    continue
                start = max(0, match.start() - 90)
                excerpt = normalize_prose(paragraph.text[start : match.end() + 130]).strip()
                hits.append(
                    {
                        "section": name,
                        "subsection": paragraph.subsection,
                        "page": paragraph.page_start,
                        "matched": match.group(0),
                        "source_excerpt": excerpt,
                    }
                )
                break
            if len(hits) >= limit:
                return hits
    return hits


def coverage_ledger(
    bundle: ParsedBundle,
    profile: DocumentProfile,
    selected_sections: dict[str, list[str]],
) -> dict[str, Any]:
    """Slot-by-slot coverage for the resolved document profile."""
    slots: list[dict[str, Any]] = []
    for slot in profile.slots:
        hits = _slot_hits(bundle, slot)
        if hits:
            status = "covered"
        elif slot.required:
            status = "absent_in_source"
        else:
            status = "not_applicable"
        slots.append(
            {
                "id": slot.id,
                "md_heading": slot.heading,
                "applicable": slot.required,
                "status": status,
                "evidence_locations": hits,
            }
        )
    captions = [
        normalize_prose(block.text) for block in bundle.blocks if block.kind == "caption" and block.text.strip()
    ]
    tables = [caption for caption in captions if re.match(r"^\s*(?:table|box)\b", caption, re.I)]
    figures = [caption for caption in captions if re.match(r"^\s*(?:fig|scheme|chart)", caption, re.I)]
    # Only required slots count towards the ratio; optional slots that happen to
    # be covered must not push it above 1.0.
    covered = sum(1 for slot in slots if slot["applicable"] and slot["status"] == "covered")
    applicable = sum(1 for slot in slots if slot["applicable"])
    covered_optional = sum(1 for slot in slots if not slot["applicable"] and slot["status"] == "covered")
    return {
        "schema_version": "2.0",
        "document_profile": profile.key,
        "document_profile_label": profile.label,
        "source_word_count": word_count(bundle.full_text),
        "source_page_count": max((block.page for block in bundle.blocks), default=0),
        "slots": slots,
        "covered_slots": covered,
        "covered_optional_slots": covered_optional,
        "applicable_slots": applicable,
        "coverage_ratio": round(covered / applicable, 4) if applicable else 1.0,
        "unchecked_slots": [slot["id"] for slot in slots if slot["status"] == "unchecked"],
        "absent_required_slots": [slot["id"] for slot in slots if slot["status"] == "absent_in_source"],
        "digest_sections_populated": {name: len(items) for name, items in selected_sections.items()},
        "major_tables": tables[:25],
        "major_figures": figures[:25],
        "notes": profile.notes,
    }


def evidence_units(items_by_target: dict[str, list[Any]]) -> list[dict[str, Any]]:
    """Page-grounded ledger of every sentence used in the digest."""
    ledger: list[dict[str, Any]] = []
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
                    "source_subsection": item.subsection,
                    "relational_score": item.features.relational_score,
                    "statement": item.text,
                }
            )
    return ledger


def _asdict(value: Any) -> Any:
    try:
        return asdict(value)
    except TypeError:
        return value
