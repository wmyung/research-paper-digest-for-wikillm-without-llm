# No-LLM scope and evidence boundary

The runtime does not load or call a generative, embedding, reranking,
vision-language, or local inference model. It uses document parsers, OCR,
regular expressions, finite scoring rules, arithmetic checks, and BM25.

This applies identically to the CLI, localhost web app, MCP stdio server,
sidecar API, and Firecrawl overlay. The MCP server exposes a deterministic tool;
it does not call the host model and returns artifact paths rather than sending
paper text over a separate network channel.

The only optional outbound request is `GET https://api.crossref.org/works/{doi}`.
It sends the public DOI alone and uses returned registry metadata for title,
authors, journal, dates, volume, issue, and pages. `--offline` disables it. Paper
text, supplements, generated Markdown, credentials, and user data are never sent.

The compiler retries with larger evidence budgets when a candidate misses the
quality gate. It never creates a missing scientific result. Every accepted
scientific statement is copied from a page-addressable source sentence. When a
corrupt or incomplete input cannot provide the required evidence, the program
still writes a candidate MD and QA report but leaves status
`NOT_SOURCE_READY`; this is not represented as success.
