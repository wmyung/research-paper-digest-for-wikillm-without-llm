#!/usr/bin/env python3
"""Install the deterministic paper-digest sidecar into a Firecrawl checkout.

The script is intentionally anchor-based and fail-closed: it refuses to patch an
unknown route layout instead of guessing. Re-running it is idempotent.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

IMPORT_BLOCK = """import {
  paperDigestController,
  paperDigestUploadMiddleware,
} from "../controllers/v2/paper-digest";
"""
PARSE_IMPORT_ANCHOR = """import {
  parseController,
  parseMultipartPayloadMiddleware,
} from "../controllers/v2/parse";
"""
ROUTE_BLOCK = """v2Router.post(
  "/paper-digest",
  authMiddleware(RateLimiterMode.Scrape, { allowKeyless: true }),
  countryCheck,
  checkCreditsMiddleware(1),
  paperDigestUploadMiddleware,
  wrap(paperDigestController),
);

"""
ROUTE_ANCHOR = """v2Router.post(
  "/parse/upload-url","""


@dataclass(slots=True)
class Report:
    firecrawl_root: str
    copied: list[str]
    changed: list[str]
    unchanged: list[str]
    backup: str | None


def copy_tree(source: Path, destination: Path, report: Report) -> None:
    if not source.is_dir():
        raise FileNotFoundError(source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(source, destination, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache"))
    report.copied.append(str(destination))


def copy_file(source: Path, destination: Path, report: Report) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    before = destination.read_bytes() if destination.exists() else None
    data = source.read_bytes()
    destination.write_bytes(data)
    (report.unchanged if before == data else report.copied).append(str(destination))


def patch_routes(path: Path, make_backup: bool, report: Report) -> None:
    text = path.read_text(encoding="utf-8")
    original = text
    if IMPORT_BLOCK.strip() not in text:
        if PARSE_IMPORT_ANCHOR not in text:
            raise RuntimeError(
                "Firecrawl route import anchor was not found; upstream layout changed. "
                "Review apps/api/src/routes/v2.ts before applying this overlay."
            )
        text = text.replace(PARSE_IMPORT_ANCHOR, PARSE_IMPORT_ANCHOR + IMPORT_BLOCK, 1)
    if '"/paper-digest"' not in text:
        if ROUTE_ANCHOR not in text:
            raise RuntimeError(
                "Firecrawl parse route anchor was not found; upstream layout changed. "
                "Review apps/api/src/routes/v2.ts before applying this overlay."
            )
        text = text.replace(ROUTE_ANCHOR, ROUTE_BLOCK + ROUTE_ANCHOR, 1)
    if text == original:
        report.unchanged.append(str(path))
        return
    if make_backup:
        backup = path.with_suffix(path.suffix + ".paper-digest.bak")
        if not backup.exists():
            backup.write_text(original, encoding="utf-8")
        report.backup = str(backup)
    path.write_text(text, encoding="utf-8")
    report.changed.append(str(path))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("firecrawl_root", type=Path, help="Path to a local firecrawl/firecrawl checkout")
    parser.add_argument("--no-backup", action="store_true", help="Do not create a one-time route backup")
    args = parser.parse_args()

    source_root = Path(__file__).resolve().parents[1]
    firecrawl = args.firecrawl_root.expanduser().resolve()
    route = firecrawl / "apps/api/src/routes/v2.ts"
    compose = firecrawl / "docker-compose.yaml"
    if not route.is_file() or not compose.is_file():
        raise SystemExit(
            "The target is not a compatible Firecrawl checkout: apps/api/src/routes/v2.ts "
            "and docker-compose.yaml are required."
        )

    report = Report(str(firecrawl), [], [], [], None)
    copy_tree(source_root / "apps/paper-digest", firecrawl / "apps/paper-digest", report)
    copy_file(
        source_root / "overlay/apps/api/src/controllers/v2/paper-digest.ts",
        firecrawl / "apps/api/src/controllers/v2/paper-digest.ts",
        report,
    )
    copy_file(
        source_root / "docker-compose.paper-digest.yml",
        firecrawl / "docker-compose.paper-digest.yml",
        report,
    )
    patch_routes(route, not args.no_backup, report)
    print(json.dumps(asdict(report), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(
            json.dumps({"success": False, "error": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False), file=sys.stderr
        )
        raise
