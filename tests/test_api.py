from fastapi.testclient import TestClient
from paper_digest.api import app


def test_health_declares_no_llm():
    response = TestClient(app).get("/health")
    assert response.status_code == 200
    assert response.json()["llm"] is False


def test_local_web_app_is_self_contained_and_private():
    response = TestClient(app).get("/")
    assert response.status_code == 200
    assert "WikiLLM Paper Digest" in response.text
    assert "research-paper-digest-for-wikillm-without-LLM" in response.text
    assert "https://" not in response.text
    assert response.headers["cache-control"] == "no-store"
    assert "default-src 'self'" in response.headers["content-security-policy"]


def test_digest_requires_file():
    response = TestClient(app).post("/v1/digest")
    assert response.status_code == 422


def test_raw_mode_returns_markdown_attachment(monkeypatch):
    import paper_digest.api as api_module
    from paper_digest.models import AuthorMetadata, CompiledDigest, PublicationMetadata

    metadata = PublicationMetadata(
        title="Test",
        authorship=AuthorMetadata(authors=["A. Example"], author_count=1),
        year=2024,
        doi="10.1000/test",
        journal="Journal",
    )
    result = CompiledDigest(
        status="SOURCE_READY",
        markdown="# certified\n",
        filename="lovelace-2024-test.md",
        metadata=metadata,
        qa={"source_ready": True, "quality_score": 1.0, "errors": []},
    )
    monkeypatch.setattr(api_module, "digest_files", lambda paths, config: result)
    response = TestClient(app).post(
        "/v1/digest?raw=true",
        files={"files": ("paper.pdf", b"%PDF-1.4", "application/pdf")},
    )
    assert response.status_code == 200
    assert response.text == "# certified\n"
    assert response.headers["x-paper-digest-llm"] == "false"
    assert "lovelace-2024-test.md" in response.headers["content-disposition"]
