#!/usr/bin/env python3
"""Fail if the paper-processing runtime acquires model or external inference dependencies."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

FORBIDDEN_DEPENDENCIES = {
    "openai",
    "anthropic",
    "google-generativeai",
    "transformers",
    "sentence-transformers",
    "litellm",
    "langchain",
    "llama-index",
    "vllm",
    "ollama",
    "ctransformers",
    "llama-cpp-python",
}
FORBIDDEN_IMPORTS = re.compile(
    r"^\s*(?:from|import)\s+(openai|anthropic|transformers|sentence_transformers|"
    r"langchain|llama_index|litellm|vllm|ollama|google\.generativeai)\b",
    re.M,
)
NETWORK_IMPORTS = re.compile(r"^\s*(?:from|import)\s+(requests|httpx|urllib\.request)\b", re.M)
FORBIDDEN_ENDPOINTS = re.compile(
    r"https?://(?:api\.openai\.com|api\.anthropic\.com|generativelanguage\.googleapis\.com|"
    r"api-inference\.huggingface\.co|localhost:(?:11434|8000))",
    re.I,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", nargs="?", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    root = args.root.resolve()
    code_roots = [root / "apps/paper-digest/src", root / "overlay/apps/api/src"]
    errors: list[str] = []
    scanned = 0
    for base in code_roots:
        for path in base.rglob("*"):
            if not path.is_file() or path.suffix not in {".py", ".ts", ".tsx"}:
                continue
            scanned += 1
            text = path.read_text(encoding="utf-8", errors="replace")
            if path.suffix == ".py":
                match = FORBIDDEN_IMPORTS.search(text)
                if match:
                    errors.append(f"Forbidden runtime import {match.group(1)!r}: {path.relative_to(root)}")
                network = NETWORK_IMPORTS.search(text)
                if network and path.relative_to(root).as_posix() != "apps/paper-digest/src/paper_digest/metadata.py":
                    errors.append(f"Unapproved runtime network import {network.group(1)!r}: {path.relative_to(root)}")
                if network and path.relative_to(root).as_posix() == "apps/paper-digest/src/paper_digest/metadata.py":
                    if "https://api.crossref.org/works/" not in text:
                        errors.append("The approved DOI registry endpoint is missing from metadata.py")
            if FORBIDDEN_ENDPOINTS.search(text):
                errors.append(f"External inference endpoint found: {path.relative_to(root)}")

    manifests = [
        root / "apps/paper-digest/pyproject.toml",
        root / "apps/paper-digest/requirements.txt",
        root / "apps/paper-digest/requirements.lock",
    ]
    for path in manifests:
        text = path.read_text(encoding="utf-8", errors="replace").casefold()
        for dependency in sorted(FORBIDDEN_DEPENDENCIES):
            if re.search(rf"(?<![a-z0-9_-]){re.escape(dependency)}(?![a-z0-9_-])", text):
                errors.append(f"Forbidden model dependency {dependency!r}: {path.relative_to(root)}")

    report = {
        "success": not errors,
        "scanned_code_files": scanned,
        "model_runtime_dependencies": 0 if not errors else None,
        "external_inference_calls": 0 if not errors else None,
        "paper_text_external_transmission": 0 if not errors else None,
        "allowed_metadata_registry": "Crossref /works/{doi}; DOI only",
        "errors": errors,
        "allowed_internal_proxy": "Firecrawl TypeScript controller -> paper-digest sidecar",
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
