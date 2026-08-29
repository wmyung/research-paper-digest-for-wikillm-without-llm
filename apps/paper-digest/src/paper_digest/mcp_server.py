from __future__ import annotations

from pathlib import Path
from typing import Any

from mcp.server import MCPServer

from . import __version__
from .artifacts import write_artifacts
from .config import DigestConfig
from .pipeline import digest_files

mcp = MCPServer(
    "WikiLLM Paper Digest",
    instructions=(
        "Convert a local research-paper evidence bundle to quality-gated WikiLLM source Markdown "
        "without calling an LLM. SOURCE_READY is certified; NOT_SOURCE_READY includes exact QA gaps."
    ),
)


@mcp.tool()
def digest_research_paper(
    input_paths: list[str],
    output_dir: str,
    offline: bool = False,
    profile: str = "auto",
) -> dict[str, Any]:
    """Convert a local PDF and optional supplements to WikiLLM Markdown and QA JSON.

    The first canonical PDF is required. Paper content stays on this machine.
    Set offline=false only to permit a DOI-only Crossref metadata lookup.
    """
    if not input_paths:
        raise ValueError("input_paths must contain a canonical PDF.")
    inputs = [Path(value).expanduser().resolve() for value in input_paths]
    missing = [str(path) for path in inputs if not path.is_file()]
    if missing:
        raise ValueError("Input files do not exist: " + ", ".join(missing))

    destination = Path(output_dir).expanduser().resolve()
    result = digest_files(
        inputs,
        DigestConfig(profile=profile, enable_doi_metadata=not offline),
    )
    paths = write_artifacts(result, destination)
    return {
        "success": result.status == "SOURCE_READY",
        "status": result.status,
        "version": __version__,
        "markdown_path": str(paths.markdown),
        "qa_path": str(paths.qa),
        "metadata_evidence_path": str(paths.metadata_evidence),
        "evidence_coverage_path": str(paths.evidence_coverage),
        "document_profile": result.qa.get("document_profile"),
        "quality_score": result.qa.get("quality_score"),
        "errors": result.qa.get("errors", []),
        "warnings": result.qa.get("warnings", []),
        "llm_used": False,
        "external_paper_content_sent": False,
    }


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
