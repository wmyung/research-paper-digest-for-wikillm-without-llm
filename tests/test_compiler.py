from helpers import bundle
from paper_digest.compiler import FRONTMATTER_KEYS, REQUIRED_HEADINGS, compile_markdown
from paper_digest.config import DigestConfig
from paper_digest.profiles.base import ProfileContent


def test_exact_legacy_contract_and_full_authors(tmp_path):
    b = bundle(tmp_path)
    content = ProfileContent(*(["Evidence-bound content."] * 8))
    markdown, filename = compile_markdown(b, content, DigestConfig(extracted_date="2026-08-07"))
    frontmatter = markdown.split("---", 2)[1]
    keys = [line.split(":", 1)[0] for line in frontmatter.splitlines() if ":" in line]
    assert keys == FRONTMATTER_KEYS
    assert "authors: A. Example, B. Example" in markdown
    assert [line for line in markdown.splitlines() if line.startswith("## ")] == REQUIRED_HEADINGS
    assert filename.startswith("example-2024-")
