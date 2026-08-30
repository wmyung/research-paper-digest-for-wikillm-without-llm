import asyncio

from mcp import Client


def test_mcp_tool_is_listed_and_writes_artifacts(monkeypatch, tmp_path):
    import paper_digest.mcp_server as module
    from paper_digest.models import AuthorMetadata, CompiledDigest, PublicationMetadata

    metadata = PublicationMetadata(
        title="Synthetic",
        authorship=AuthorMetadata(authors=["A. Example"], author_count=1),
        year=2026,
    )
    compiled = CompiledDigest(
        status="SOURCE_READY",
        markdown="# Synthetic grounded output\n",
        filename="synthetic.md",
        metadata=metadata,
        qa={"source_ready": True, "quality_score": 1.0, "errors": []},
    )
    captured = {}

    def fake_digest(paths, config):
        captured["config"] = config
        return compiled

    monkeypatch.setattr(module, "digest_files", fake_digest)
    source = tmp_path / "synthetic.pdf"
    source.write_bytes(b"%PDF-1.4 synthetic test fixture")
    output = tmp_path / "output"

    async def exercise() -> None:
        async with Client(module.mcp) as client:
            tools = await client.list_tools()
            assert [tool.name for tool in tools.tools] == ["digest_research_paper"]
            answer = await client.call_tool(
                "digest_research_paper",
                {
                    "input_paths": [str(source)],
                    "output_dir": str(output),
                    "source_ready_threshold": 0.8,
                    "stage2_min_score": 0.65,
                    "stage2_max_rounds": 4,
                },
            )
            assert answer.structured_content["status"] == "SOURCE_READY"
            assert answer.structured_content["llm_used"] is False
            assert answer.structured_content["external_paper_content_sent"] is False

    asyncio.run(exercise())
    assert (output / "synthetic.md").read_text() == compiled.markdown
    assert (output / "synthetic.qa.json").is_file()
    assert captured["config"].source_ready_threshold == 0.8
    assert captured["config"].stage2_min_score == 0.65
    assert captured["config"].stage2_max_rounds == 4
