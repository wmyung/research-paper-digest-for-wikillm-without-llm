import os
from pathlib import Path

import pytest
from paper_digest.config import DigestConfig
from paper_digest.pipeline import digest_files


@pytest.mark.skipif(not os.environ.get("PAPER_DIGEST_E2E_PDF"), reason="Private E2E fixture paths are opt-in")
def test_private_uploaded_bundle_reaches_quality_gate(tmp_path: Path):
    paths = [Path(os.environ["PAPER_DIGEST_E2E_PDF"])]
    for key in ("PAPER_DIGEST_E2E_SUPP_PDF", "PAPER_DIGEST_E2E_XLSX"):
        if os.environ.get(key):
            paths.append(Path(os.environ[key]))
    result = digest_files(paths, DigestConfig(work_dir=tmp_path / "work", extracted_date="2026-08-07"))
    assert result.status == "SOURCE_READY", result.qa["errors"]
    assert result.qa["quality_score"] >= 0.95
    assert result.qa["errors"] == []
    assert result.markdown.startswith("---\n")
