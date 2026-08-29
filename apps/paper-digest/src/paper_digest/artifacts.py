from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from .models import CompiledDigest

IDENTITY_RE = re.compile(r"^(?:title|doi):\s*(.*)$", re.M)


@dataclass(slots=True)
class ArtifactPaths:
    """Where each artifact of one digest run was written."""

    markdown: Path
    qa: Path
    metadata_evidence: Path
    evidence_coverage: Path

    def as_dict(self) -> dict[str, str]:
        return {
            "markdown": str(self.markdown),
            "qa": str(self.qa),
            "metadata_evidence": str(self.metadata_evidence),
            "evidence_coverage": str(self.evidence_coverage),
        }

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
    return ArtifactPaths(markdown_path, qa_path, metadata_path, coverage_path)
