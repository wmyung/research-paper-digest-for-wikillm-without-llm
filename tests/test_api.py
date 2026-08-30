import json

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
    assert "wikillm-digest-noLLM" in response.text
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


def test_api_accepts_all_stage2_controls(monkeypatch):
    import paper_digest.api as api_module
    from paper_digest.models import CompiledDigest, PublicationMetadata

    captured = {}
    result = CompiledDigest(
        status="NOT_SOURCE_READY",
        markdown="# candidate\n",
        filename="candidate.md",
        metadata=PublicationMetadata(),
        qa={"source_ready": False, "quality_score": 0.79, "errors": ["held"]},
    )

    def fake_digest(paths, config):
        captured["config"] = config
        return result

    monkeypatch.setattr(api_module, "digest_files", fake_digest)
    response = TestClient(app).post(
        "/v1/digest",
        files={"files": ("paper.pdf", b"%PDF-1.4", "application/pdf")},
        data={
            "options": json.dumps(
                {
                    "source_ready_threshold": 0.8,
                    "enable_stage2": True,
                    "stage2_min_score": 0.65,
                    "stage2_max_rounds": 5,
                }
            )
        },
    )
    assert response.status_code == 422
    assert captured["config"].source_ready_threshold == 0.8
    assert captured["config"].stage2_min_score == 0.65
    assert captured["config"].stage2_max_rounds == 5


def test_api_reports_invalid_option_combinations_as_422():
    response = TestClient(app).post(
        "/v1/digest",
        files={"files": ("paper.pdf", b"%PDF-1.4", "application/pdf")},
        data={"options": json.dumps({"source_ready_threshold": 0.6, "stage2_min_score": 0.7})},
    )
    assert response.status_code == 422
    assert "stage2_min_score" in response.json()["detail"]
