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
    parser.add_argument(
        "--source-ready-threshold",
        type=float,
        default=0.95,
        help="Certification threshold in (0, 1]; default: 0.95.",
    )
    parser.add_argument("--disable-stage2", action="store_true", help="Disable diagnosis-driven Stage-2 repair.")
    parser.add_argument("--stage2-min-score", type=float, default=0.70, help="Minimum raw score eligible for Stage 2.")
    parser.add_argument("--stage2-max-rounds", type=int, default=3, help="Stage-2 repair rounds, from 1 to 6.")
    parser.add_argument(
        "--repair-plan",
        type=Path,
        default=None,
        help="Validated luna_repair_plan_v1 JSON containing grounded candidate assignments.",
    )
    parser.add_argument("--offline", action="store_true", help="Disable DOI-registry metadata repair.")
    parser.add_argument(
        "--verify-pdf-path",
        action="store_true",
        help="Require the canonical PDF to exist at the pdf_path written to frontmatter.",
    )
    parser.add_argument("--json-only", action="store_true", help="Print JSON only; do not write files.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        config = DigestConfig(
            profile=args.profile,
            strict=not args.non_strict,
            pdf_path=args.pdf_path,
            source_collection=args.source_collection,
            source_ready_threshold=args.source_ready_threshold,
            enable_doi_metadata=not args.offline,
            verify_pdf_path=args.verify_pdf_path,
            enable_stage2=not args.disable_stage2,
            stage2_min_score=args.stage2_min_score,
            stage2_max_rounds=args.stage2_max_rounds,
            external_repair_plan=args.repair_plan,
        )
    except ValueError as exc:
        parser.error(str(exc))
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
                    "raw_quality_score": result.qa.get("raw_quality_score"),
                    "stage2_operators": result.qa.get("stage2", {}).get("operators_accepted", []),
                    "document_profile": result.qa.get("document_profile"),
                    "errors": result.qa.get("errors", []),
                    "warnings": result.qa.get("warnings", []),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    return 0 if result.status == "SOURCE_READY" else 2
