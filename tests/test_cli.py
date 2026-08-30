from __future__ import annotations

import pytest
from paper_digest import cli


def test_cli_wires_quality_and_stage2_controls(monkeypatch, tmp_path):
    captured = {}

    class Result:
        status = "NOT_SOURCE_READY"
        qa = {"errors": ["held"]}

        def to_dict(self, *, include_markdown):
            return {"status": self.status, "markdown_included": include_markdown}

    def fake_digest(paths, config):
        captured["paths"] = paths
        captured["config"] = config
        return Result()

    monkeypatch.setattr(cli, "digest_files", fake_digest)
    paper = tmp_path / "paper.pdf"
    code = cli.main(
        [
            str(paper),
            "--json-only",
            "--source-ready-threshold",
            "0.8",
            "--disable-stage2",
            "--stage2-min-score",
            "0.65",
            "--stage2-max-rounds",
            "5",
        ]
    )

    assert code == 2
    assert captured["paths"] == [paper]
    assert captured["config"].source_ready_threshold == 0.8
    assert captured["config"].enable_stage2 is False
    assert captured["config"].stage2_min_score == 0.65
    assert captured["config"].stage2_max_rounds == 5


def test_cli_rejects_an_invalid_stage2_window(capsys):
    with pytest.raises(SystemExit) as exc:
        cli.main(
            [
                "paper.pdf",
                "--source-ready-threshold",
                "0.6",
                "--stage2-min-score",
                "0.7",
            ]
        )
    assert exc.value.code == 2
    assert "stage2_min_score" in capsys.readouterr().err
