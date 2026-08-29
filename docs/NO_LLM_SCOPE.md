# No-LLM scope and evidence boundary

The runtime does not load or call a generative, embedding, reranking,
vision-language, or local inference model. It uses document parsers, OCR,
regular expressions, finite scoring rules, a standard-library LexRank
implementation, arithmetic checks, and BM25.

This applies identically to the CLI, localhost web app, MCP stdio server,
sidecar API, and Firecrawl overlay. The MCP server exposes a deterministic tool;
it does not call the host model and returns artifact paths rather than sending
paper text over a separate network channel.

The only optional outbound request is `GET https://api.crossref.org/works/{doi}`.
It sends the public DOI alone and uses returned registry metadata for title,
authors, journal, dates, volume, issue, and pages. `--offline` disables it. Paper
text, supplements, generated Markdown, credentials, and user data are never sent.

## What "grounded" means here

Every prose sentence in the output is a span of the source PDF, normalised for
line breaks and stripped of citation markers, and nothing else. There is no
paraphrase, no synthesis across two locations, and no inferred implication.

That is checked rather than asserted. After compilation, `grounding.py` reduces
both the digest and the extracted source to their alphanumeric skeleton and
requires every emitted sentence to appear in the source; a sentence that does
not is a hard QA error. Sentences the compiler writes itself — "the source
states no limitation, caveat or boundary condition", the glossary fallback — are
declared by the profile, excluded from that check, and counted in the report so
their number is visible.

The consequence is a real and deliberate limit. A rule-based compiler cannot
write the sentence an expert reader would write, because that sentence usually
combines an abstract, a table cell and a figure legend into one clause that
appears nowhere in the paper. What it can do is select the source's own best
sentences, keep the numbers attached to their comparisons, refuse to fill a gap
it cannot evidence, and prove afterwards that it invented nothing.

## Failure is reported, not hidden

The compiler retries with larger evidence budgets when a candidate misses the
quality gate. It never creates a missing scientific result. When a corrupt or
incomplete input cannot provide the required evidence, the program still writes
a candidate MD, a QA report and both ledgers, but leaves the status
`NOT_SOURCE_READY`; this is not represented as success. A section with no
qualifying evidence carries an explicit statement that the source contains none,
rather than an empty heading.
