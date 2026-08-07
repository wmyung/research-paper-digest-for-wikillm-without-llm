import zipfile
from pathlib import Path

import pytest
from paper_digest.config import DigestConfig
from paper_digest.parsers.archive import expand_zip


def test_zip_path_traversal_rejected(tmp_path: Path):
    archive = tmp_path / "bad.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("../escape.txt", "x")
    with pytest.raises(ValueError, match="Unsafe archive path"):
        expand_zip(archive, tmp_path / "out", DigestConfig())


def test_zip_member_limit_rejected(tmp_path: Path):
    archive = tmp_path / "many.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("a.txt", "a")
        zf.writestr("b.txt", "b")
    with pytest.raises(ValueError, match="members"):
        expand_zip(archive, tmp_path / "out", DigestConfig(max_archive_members=1))
