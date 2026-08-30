# WikiLLM Paper Digest runtime

This service converts a publisher PDF and optional supplementary PDF, XLSX,
DOCX, CSV, JSON, text, or ZIP files into the fixed source-Markdown contract. It
does not load or call any LLM, embedding model, reranker, or VLM.

The universal compiler uses deterministic layout parsing, OCR, section rules,
source-sentence scoring, quantitative checks, and BM25 retrieval regression.
It retries with expanded evidence budgets and returns `SOURCE_READY` only after
every hard gate passes at a score of at least 0.95.

When enabled, bibliographic repair sends only the public DOI to Crossref. Use
`--offline` or `"enable_doi_metadata": false` to prevent that request. Paper
text is never sent to the registry.

```bash
python -m pip install -e .
paper-digest paper.pdf fulltext.xml supplement.pdf tables.xlsx -o output
paper-digest --offline paper.pdf -o output
```

```bash
paper-digest-web --open
paper-digest-mcp
uvicorn paper_digest.api:app --host 127.0.0.1 --port 8088
curl -X POST http://localhost:8088/v1/digest \
  -F "files=@paper.pdf" \
  -F 'options={"profile":"auto","strict":true}'
```

`/v1/digest?raw=true` returns a Markdown attachment only for certified output.
An uncertified response still contains the generated Markdown and exact QA gaps
in JSON.
