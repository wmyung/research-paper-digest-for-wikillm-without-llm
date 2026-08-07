import json
from io import BytesIO

from paper_digest.metadata import enrich_from_doi_registry
from paper_digest.models import PublicationMetadata


class Response(BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def test_crossref_enrichment_sends_only_encoded_doi(monkeypatch):
    captured = {}
    payload = {
        "message": {
            "DOI": "10.1000/synthetic.1",
            "title": ["A synthetic registry record"],
            "author": [{"given": "A.", "family": "Example"}],
            "container-title": ["Synthetic Methods Journal"],
            "published-online": {"date-parts": [[2024, 2, 3]]},
            "volume": "12",
            "issue": "2",
            "page": "10-20",
            "type": "journal-article",
        }
    }

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        return Response(json.dumps(payload).encode())

    monkeypatch.setattr("paper_digest.metadata.urlopen", fake_urlopen)
    metadata = PublicationMetadata(doi="10.1000/synthetic.1")
    assert enrich_from_doi_registry(metadata, timeout=3.0) is True
    assert captured == {
        "url": "https://api.crossref.org/works/10.1000%2Fsynthetic.1",
        "timeout": 3.0,
    }
    assert metadata.title == "A synthetic registry record"
    assert metadata.authorship.authors == ["A. Example"]
    assert metadata.journal == "Synthetic Methods Journal"
    assert metadata.year == 2024
    assert metadata.metadata_sources == ["Crossref DOI registry"]
