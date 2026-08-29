from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .models import CompiledDigest


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


def write_artifacts(result: CompiledDigest, output_dir: Path) -> ArtifactPaths:
    """Write the grounded Markdown plus its QA report and two audit ledgers.

    The ledgers mirror the records an LLM-assisted workflow keeps beside a
    digest: where every bibliographic value came from, and which evidence slots
    of the resolved document profile the source actually covers.
    """
    output_dir = output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = Path(result.filename).stem
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
