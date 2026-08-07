from __future__ import annotations

import json
from pathlib import Path

from .models import CompiledDigest


def write_artifacts(result: CompiledDigest, output_dir: Path) -> tuple[Path, Path]:
    """Write the grounded Markdown candidate and its QA evidence sidecar."""
    output_dir = output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    markdown_path = output_dir / Path(result.filename).name
    qa_path = output_dir / Path(result.filename).name.replace(".md", ".qa.json")
    markdown_path.write_text(result.markdown, encoding="utf-8")
    qa_path.write_text(json.dumps(result.qa, ensure_ascii=False, indent=2), encoding="utf-8")
    return markdown_path, qa_path
