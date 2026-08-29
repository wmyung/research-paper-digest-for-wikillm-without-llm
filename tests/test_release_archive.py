"""The release archive carries the source, not installed dependencies."""

from __future__ import annotations

import importlib.util
import sys
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def builder():
    spec = importlib.util.spec_from_file_location("paper_digest_release", ROOT / "scripts" / "build-release.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    "relative",
    [
        "node_modules/typescript/lib/typescript.js",
        ".git/config",
        "dist/previous.zip",
        "apps/paper-digest/src/paper_digest/__pycache__/qa.cpython-312.pyc",
        ".venv/bin/python",
    ],
)
def test_dependency_and_cache_paths_are_excluded(builder, relative):
    assert builder.include(Path(relative)) is False


@pytest.mark.parametrize(
    "relative",
    [
        "README.md",
        "apps/paper-digest/src/paper_digest/qa.py",
        "docs/QUALITY_GATES.md",
        "schemas/evidence-coverage.schema.json",
    ],
)
def test_source_paths_are_included(builder, relative):
    assert builder.include(Path(relative)) is True


def test_built_archive_contains_no_installed_dependencies(builder, tmp_path):
    archive = tmp_path / "release.zip"
    builder.write_zip(ROOT, archive, "release")
    with zipfile.ZipFile(archive) as handle:
        names = handle.namelist()
    assert names, "the archive is empty"
    assert not [name for name in names if "node_modules/" in name or "/.git/" in name]
    assert any(name.endswith("README.md") for name in names)


def test_archive_name_does_not_depend_on_the_checkout_directory(builder, tmp_path):
    archive = tmp_path / "chosen-name.zip"
    result = builder.write_zip(ROOT, archive, "chosen-name")
    assert result["path"].endswith("chosen-name.zip")
    with zipfile.ZipFile(archive) as handle:
        assert all(name.startswith("chosen-name/") for name in handle.namelist())
