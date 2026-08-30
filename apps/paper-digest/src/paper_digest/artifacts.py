from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from .models import CompiledDigest
from .profiles.universal import ORDER
from .selection import build_candidates, score_for

IDENTITY_RE = re.compile(r"^(?:title|doi):\s*(.*)$", re.M)


@dataclass(slots=True)
class ArtifactPaths:
    """Where each artifact of one digest run was written."""

    markdown: Path
    qa: Path
    metadata_evidence: Path
    evidence_coverage: Path
    luna_repair_input: Path | None = None

    def as_dict(self) -> dict[str, str]:
        output = {
            "markdown": str(self.markdown),
            "qa": str(self.qa),
            "metadata_evidence": str(self.metadata_evidence),
            "evidence_coverage": str(self.evidence_coverage),
        }
        if self.luna_repair_input is not None:
            output["luna_repair_input"] = str(self.luna_repair_input)
        return output

    def __iter__(self):
        # Kept iterable so `markdown_path, qa_path = write_artifacts(...)` works.
        return iter((self.markdown, self.qa))


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _identity(markdown: str) -> tuple[str, ...]:
    """The title and DOI that identify which document a record describes."""
    head = markdown.split("\n---\n", 1)[0]
    return tuple(value.strip().strip('"') for value in IDENTITY_RE.findall(head))


def _free_stem(output_dir: Path, stem: str, markdown: str) -> str:
    """Pick a stem that will not overwrite a different document's record.

    Two papers can share a filename stem when neither yields an author or a
    year — a batch run must not silently lose one of them. Re-running the same
    paper still overwrites its own record in place.
    """
    identity = _identity(markdown)
    candidate = stem
    suffix = 1
    while True:
        existing = output_dir / f"{candidate}.md"
        if not existing.exists():
            return candidate
        try:
            if _identity(existing.read_text(encoding="utf-8")) == identity:
                return candidate
        except OSError:
            return candidate
        suffix += 1
        candidate = f"{stem}-{suffix}"


def _luna_repair_packet(result: CompiledDigest) -> dict[str, object] | None:
    """Build a rich JSON-first handoff without asking Luna to reread the PDF."""
    bundle = result.bundle
    if bundle is None:
        return None
    candidates = build_candidates(bundle)
    canonical = next((item for item in bundle.files if item.role == "canonical-paper"), None)
    catalog: list[dict[str, object]] = []
    section_index: dict[str, list[str]] = {}
    for candidate in candidates:
        candidate_id = f"c{candidate.order:05d}"
        scores = {
            target: round(score, 4)
            for target in ORDER
            if (score := score_for(candidate, target, relaxed=False)) > 0.0
        }
        relaxed_scores = {
            target: round(score, 4)
            for target in ORDER
            if target != "summary"
            and target not in scores
            and (score := score_for(candidate, target, relaxed=True)) > 0.0
        }
        catalog.append(
            {
                "candidate_id": candidate_id,
                "text": candidate.text,
                "source_file": candidate.source_file,
                "page_start": candidate.page_start,
                "page_end": candidate.page_end,
                "section": candidate.section,
                "subsection": candidate.subsection,
                "source_order": candidate.order,
                "strict_target_scores": scores,
                "relaxed_target_scores": relaxed_scores,
            }
        )
        section_index.setdefault(candidate.section, []).append(candidate_id)

    source_sections = {
        name: [
            {
                "page_start": paragraph.page_start,
                "page_end": paragraph.page_end,
                "subsection": paragraph.subsection,
                "text": paragraph.text,
            }
            for paragraph in section.paragraphs
        ]
        for name, section in bundle.sections.items()
        if section.paragraphs and name != "References"
    }
    return {
        "schema_version": "wikillm-luna-repair-input-v1",
        "purpose": "diagnose deterministic extraction/selection failures and propose a bounded repair plan",
        "status": result.status,
        "identity": {
            "title": bundle.metadata.title,
            "doi": bundle.metadata.doi,
            "pdf_filename": bundle.canonical_pdf.name,
            "pdf_sha256": canonical.sha256 if canonical else "",
            "document_profile": bundle.metadata.document_profile,
        },
        "read_strategy": [
            "Read diagnosis, selected_evidence and candidate_section_index first.",
            "Filter candidate_catalog by the failed target; do not read every candidate by default.",
            "Open source_sections only for unresolved extraction or profile questions.",
            "Use the PDF pages only to visually confirm a proposed span when JSON remains ambiguous.",
        ],
        "diagnosis": {
            "errors": list(result.qa.get("errors", [])),
            "warnings": list(result.qa.get("warnings", [])),
            "triage": result.qa.get("triage", {}),
            "coverage": result.qa.get("coverage_ledger", {}),
            "stage2": result.qa.get("stage2", {}),
        },
        "structured_source": bundle.structured_source,
        "selected_evidence": result.qa.get("evidence_ledger", []),
        "candidate_section_index": section_index,
        "candidate_catalog": catalog,
        "source_sections": source_sections,
        "required_output": {
            "format": "luna_repair_plan_v1 JSON only",
            "example": {
                "schema_version": "luna_repair_plan_v1",
                "identity": {
                    "doi": bundle.metadata.doi,
                    "pdf_sha256": canonical.sha256 if canonical else "",
                },
                "assignments": [
                    {"candidate_id": "c00042", "target": "results", "mode": "strict", "reason": "short rationale"}
                ],
                "advisory_actions": [],
            },
            "allowed_actions": [
                "assign_candidate_to_target",
                "change_document_profile",
                "request_official_structured_source",
                "report_unresolved_extraction",
                "propose_general_rule_with_regression_test",
            ],
            "forbidden_actions": [
                "write_paraphrased_digest_prose",
                "invent_or infer missing facts",
                "lower a quality or grounding gate",
                "bypass access controls",
            ],
        },
    }


def write_artifacts(result: CompiledDigest, output_dir: Path) -> ArtifactPaths:
    """Write the grounded Markdown plus its QA report and two audit ledgers.

    The ledgers mirror the records an LLM-assisted workflow keeps beside a
    digest: where every bibliographic value came from, and which evidence slots
    of the resolved document profile the source actually covers.
    """
    output_dir = output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = _free_stem(output_dir, Path(result.filename).stem, result.markdown)
    markdown_path = output_dir / f"{stem}.md"
    qa_path = output_dir / f"{stem}.qa.json"
    metadata_path = output_dir / f"{stem}.metadata-evidence.json"
    coverage_path = output_dir / f"{stem}.evidence-coverage.json"
    luna_path: Path | None = None

    markdown_path.write_text(result.markdown, encoding="utf-8")
    _write_json(qa_path, result.qa)
    _write_json(
        metadata_path,
        {
            "schema_version": "2.0",
            "pdf_filename": f"{stem}.pdf",
            "status": result.status,
            "fields": result.qa.get("metadata_ledger", []),
        },
    )
    _write_json(coverage_path, result.qa.get("coverage_ledger", {}))
    if result.status != "SOURCE_READY":
        packet = _luna_repair_packet(result)
        if packet is not None:
            luna_path = output_dir / f"{stem}.luna-repair-input.json"
            _write_json(luna_path, packet)
    return ArtifactPaths(markdown_path, qa_path, metadata_path, coverage_path, luna_path)
