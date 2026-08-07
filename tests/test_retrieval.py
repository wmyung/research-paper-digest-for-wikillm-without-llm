from paper_digest.retrieval import run_queries


def test_bm25_full_question_regression_serializes_slot_dataclass():
    markdown = """## 4. Key Results and Benchmarks

### Validation finding

In the external validation set, the calibration slope was 0.94 and was not significantly different from one at P = 0.18.
"""
    result = run_queries(
        markdown,
        [
            {
                "id": "validation",
                "query": "What calibration result was reported for the external validation set?",
                "expected_terms": ["calibration", "0.94"],
            }
        ],
    )
    assert result["passed"] == 1
    assert result["results"][0]["hits"][0]["rank"] == 1
