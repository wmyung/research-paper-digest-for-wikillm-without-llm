#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
from hashlib import sha256
from pathlib import Path


def digest(path: Path) -> str:
    h = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    required = [
        root / "README.md",
        root / "README-KO.md",
        root / "CHANGELOG.md",
        root / "LICENSE",
        root / "THIRD_PARTY_NOTICES.md",
        root / "docker-compose.paper-digest.yml",
        root / "overlay/apps/api/src/controllers/v2/paper-digest.ts",
        root / "scripts/apply-firecrawl-overlay.py",
        root / "scripts/build-release.py",
        root / "patches/firecrawl-v2-paper-digest.patch",
        root / "schemas/paper-digest-options.schema.json",
        root / "schemas/paper-digest-response.schema.json",
        root / "apps/paper-digest/pyproject.toml",
        root / "apps/paper-digest/requirements.lock",
        root / "apps/paper-digest/Dockerfile",
    ]
    missing = [str(path.relative_to(root)) for path in required if not path.is_file()]
    commands = [
        [sys.executable, "-m", "compileall", "-q", str(root / "apps/paper-digest/src")],
        [sys.executable, str(root / "scripts/no-llm-audit.py"), str(root)],
        [sys.executable, "-m", "pytest", str(root / "tests"), "-q"],
    ]
    command_results = []
    for command in commands:
        completed = subprocess.run(
            command,
            cwd=root,
            text=True,
            capture_output=True,
            env={**dict(__import__("os").environ), "PYTHONPATH": str(root / "apps/paper-digest/src")},
        )
        command_results.append(
            {
                "command": command,
                "returncode": completed.returncode,
                "stdout": completed.stdout[-4000:],
                "stderr": completed.stderr[-4000:],
            }
        )
    private_suffixes = {".pdf", ".docx", ".xlsx", ".xlsm", ".csv", ".tsv"}
    private_artifacts = sorted(
        str(path.relative_to(root))
        for path in root.rglob("*")
        if path.is_file()
        and not any(part in {".git", ".venv", "dist", "build"} for part in path.parts)
        and path.suffix.casefold() in private_suffixes
    )
    success = not missing and not private_artifacts and all(item["returncode"] == 0 for item in command_results)
    report = {
        "success": success,
        "version": "2.2.0",
        "missing": missing,
        "commands": command_results,
        "private_artifacts": private_artifacts,
        "files": {str(path.relative_to(root)): digest(path) for path in required if path.is_file()},
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
