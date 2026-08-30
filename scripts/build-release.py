#!/usr/bin/env python3
"""Build clean release archives for the deterministic Firecrawl extension."""

from __future__ import annotations

import argparse
import json
import shutil
import zipfile
from hashlib import sha256
from pathlib import Path

# Installed dependencies and local caches are never part of a release: they
# bloat the archive and they are not the source anyone is meant to review.
EXCLUDED_PARTS = {
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".git",
    ".github",
    ".venv",
    "venv",
    "node_modules",
    "dist",
    "build",
    ".DS_Store",
}
EXCLUDED_SUFFIXES = {".pyc", ".pyo"}


def digest(path: Path) -> str:
    h = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def include(path: Path) -> bool:
    if any(part in EXCLUDED_PARTS or part.endswith(".egg-info") for part in path.parts):
        return False
    return path.suffix not in EXCLUDED_SUFFIXES


def write_zip(source: Path, archive: Path, prefix: str, selected: list[Path] | None = None) -> dict[str, object]:
    archive.parent.mkdir(parents=True, exist_ok=True)
    if archive.exists():
        archive.unlink()
    files = (
        selected
        if selected is not None
        else [path for path in source.rglob("*") if path.is_file() and include(path.relative_to(source))]
    )
    files = sorted(files, key=lambda p: p.as_posix())
    total = 0
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for path in files:
            relative = path.relative_to(source)
            arcname = Path(prefix) / relative
            zf.write(path, arcname.as_posix())
            total += path.stat().st_size
    return {
        "path": str(archive),
        "sha256": digest(archive),
        "file_count": len(files),
        "uncompressed_bytes": total,
        "archive_bytes": archive.stat().st_size,
    }


def write_sha_sidecar(archive: Path) -> Path:
    sidecar = archive.with_suffix(archive.suffix + ".sha256")
    sidecar.write_text(f"{digest(archive)}  {archive.name}\n", encoding="utf-8")
    return sidecar


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "dist",
        help="Where to write the release archives (default: dist/ beside the repository).",
    )
    parser.add_argument(
        "--name",
        default=None,
        help="Archive base name (default: the checkout directory name).",
    )
    args = parser.parse_args()

    root = args.root.resolve()
    output = args.output_dir.resolve()
    # A checkout can sit in a directory with any name; do not let that decide
    # what the published archive is called.
    name = args.name or root.name
    if not (root / "README.md").is_file() or not (root / "apps/paper-digest").is_dir():
        raise SystemExit(f"Not a release root: {root}")

    main_zip = output / f"{name}.zip"
    main_result = write_zip(root, main_zip, name)
    main_sha = write_sha_sidecar(main_zip)

    runtime_root = output / f"{name}-runtime-overlay"
    if runtime_root.exists():
        shutil.rmtree(runtime_root)
    runtime_root.mkdir(parents=True)
    selected_relatives = [
        Path("README.md"),
        Path("README-KO.md"),
        Path("LICENSE"),
        Path("THIRD_PARTY_NOTICES.md"),
        Path("docs/FIRECRAWL_INTEGRATION.md"),
        Path("docs/NO_LLM_SCOPE.md"),
        Path("docs/QUALITY_GATES.md"),
        Path("docker-compose.paper-digest.yml"),
        Path("scripts/apply-firecrawl-overlay.py"),
        Path("scripts/no-llm-audit.py"),
        Path("patches/firecrawl-v2-paper-digest.patch"),
        Path("overlay/apps/api/src/controllers/v2/paper-digest.ts"),
    ]
    for relative in selected_relatives:
        source = root / relative
        target = runtime_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    shutil.copytree(
        root / "apps/paper-digest",
        runtime_root / "apps/paper-digest",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache", "*.egg-info"),
    )
    runtime_zip = output / f"{name}-runtime-overlay.zip"
    runtime_result = write_zip(runtime_root, runtime_zip, runtime_root.name)
    runtime_sha = write_sha_sidecar(runtime_zip)
    shutil.rmtree(runtime_root)

    manifest = {
        "success": True,
        "version": "2.4.0",
        "source_root": str(root),
        "archives": {
            "release": main_result,
            "runtime_overlay": runtime_result,
        },
        "sha256_sidecars": [str(main_sha), str(runtime_sha)],
        "publisher_source_files_included": False,
    }
    manifest_path = output / f"{name}-release-manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
