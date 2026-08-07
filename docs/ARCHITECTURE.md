# Architecture

## Interface paths

```text
CLI paper-digest -----------\
Local web app GET / ---------+-> sidecar POST /v1/digest --\
MCP digest_research_paper ---+-----------------------------+-> deterministic evidence compiler
Firecrawl POST /v2/paper-digest -> guarded internal proxy --/              |
                                                                            +-> Markdown + QA JSON
```

The CLI and MCP server read only explicitly supplied local paths. The local web
app binds to `127.0.0.1` by default and handles uploads in per-request temporary
directories. The Firecrawl API performs authentication, country checks, and one-credit
accounting before proxying the evidence bundle. The Python sidecar is not
published to the host by the supplied Compose file; it is reachable only on the
Firecrawl `backend` network.

## Compiler stages

1. **Inventory and canonical selection**
   - resolve files and nested ZIPs;
   - hash and deduplicate;
   - classify full paper versus supplements;
   - require a readable canonical PDF.
2. **Layout extraction**
   - PyMuPDF text blocks, pages, fonts, bounding boxes, and two-column ordering;
   - recurring headers, footers, and isolated page numbers suppressed.
3. **Evidence parsing**
   - PDF, XLSX/XLSM, DOCX, CSV/TSV, JSON, Markdown, and text;
   - hidden workbook sheets and cached values retained in inventory.
4. **Bibliographic reconstruction**
   - title, ordered authors, author-role notes, DOI, journal, publication dates,
     article type, license, and author keywords.
   - if enabled, DOI-only Crossref repair fills bibliographic gaps without
     sending paper text.
5. **Universal design classification**
   - deterministic lexical and structural scoring;
   - no embeddings or model inference.
6. **Evidence compilation and repair**
   - methods, populations, tests, thresholds, major results, nulls,
     limitations, related work, and glossary assembled from explicit source
     evidence and validated table layouts.
7. **Contract compilation**
   - exact 11-key YAML and exact eight H2 sections.
8. **Fail-closed QA**
   - schema, authorship, metadata, scientific boundaries, quantitative anchors,
     length, density, evidence parsing, and profile validation.
9. **Retrieval regression**
   - deterministic BM25 tests against full English research questions.
10. **Automatic retry**
   - up to four evidence-budget passes; the first candidate clearing every hard
     gate and the 0.95 score threshold is returned.

## Trust boundary

The Markdown is not certified merely because it was generated. `SOURCE_READY`
requires all hard gates. The QA report is the
machine-readable audit trail; operational details never enter the source
Markdown.
