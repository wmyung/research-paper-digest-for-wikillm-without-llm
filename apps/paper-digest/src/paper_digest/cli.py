from __future__ import annotations

import argparse
import json
from pathlib import Path

from . import __version__
from .artifacts import write_artifacts
from .config import DigestConfig
from .pipeline import digest_files


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="paper-digest",
        description="Compile a research paper into WikiLLM source Markdown without an LLM.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("inputs", nargs="+", type=Path, help="Canonical paper PDF plus optional supplementary files.")
    parser.add_argument("-o", "--output-dir", type=Path, default=Path.cwd(), help="Output directory.")
    parser.add_argument("--profile", default="auto", help="Profile name (auto, universal, generic).")
    parser.add_argument(
        "--non-strict", action="store_true", help="Allow generic extractive output; it remains NOT_SOURCE_READY."
    )
    parser.add_argument("--pdf-path", default=None, help="Repository path written to frontmatter.")
    parser.add_argument("--source-collection", default="publisher-pdf")
    parser.add_argument("--offline", action="store_true", help="Disable DOI-registry metadata repair.")
    parser.add_argument(
        "--verify-pdf-path",
        action="store_true",
        help="Require the canonical PDF to exist at the pdf_path written to frontmatter.",
    )
    parser.add_argument("--json-only", action="store_true", help="Print JSON only; do not write files.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = DigestConfig(
        profile=args.profile,
        strict=not args.non_strict,
        pdf_path=args.pdf_path,
        source_collection=args.source_collection,
        enable_doi_metadata=not args.offline,
        verify_pdf_path=args.verify_pdf_path,
    )
    result = digest_files(args.inputs, config)
    payload = result.to_dict(include_markdown=args.json_only)
    if args.json_only:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        paths = write_artifacts(result, args.output_dir)
        print(
            json.dumps(
                {
                    "status": result.status,
                    **paths.as_dict(),
                    "quality_score": result.qa.get("quality_score"),
                    "document_profile": result.qa.get("document_profile"),
                    "errors": result.qa.get("errors", []),
                    "warnings": result.qa.get("warnings", []),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    return 0 if result.status == "SOURCE_READY" else 2
