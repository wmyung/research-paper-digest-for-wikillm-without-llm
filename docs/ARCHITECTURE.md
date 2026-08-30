# Architecture

## Interface paths

```text
CLI paper-digest -----------\
Local web app GET / ---------+-> sidecar POST /v1/digest --\
MCP digest_research_paper ---+-----------------------------+-> deterministic evidence compiler
Firecrawl POST /v2/paper-digest -> guarded internal proxy --/              |
                                                                          +-> Markdown + QA JSON
                                                                          +-> metadata-evidence.json
                                                                          +-> evidence-coverage.json
```

The CLI and MCP server read only explicitly supplied local paths. The local web
app binds to `127.0.0.1` by default and handles uploads in per-request temporary
directories. The Firecrawl API performs authentication, country checks, and
one-credit accounting before proxying the evidence bundle. The Python sidecar is
not published to the host by the supplied Compose file; it is reachable only on
the Firecrawl `backend` network.

## Compiler stages

1. **Inventory and canonical selection** (`inventory.py`)
   - resolve files and nested ZIPs; hash and deduplicate;
   - classify full paper versus supplements;
   - require a readable canonical PDF.
2. **Layout analysis** (`parsers/layout.py`)
   - column bands from an x-coverage histogram, so reading order follows the
     page rather than the content stream;
   - running heads and feet from cross-page recurrence with digits masked;
   - repository and accepted-manuscript cover sheets detected and excluded;
   - a two-pass body-font estimate: the first modal size is skewed by dense
     reference and table text, so it is re-measured from blocks the first pass
     called body and the page is re-classified;
   - display matter separated from prose: captions, table zones anchored to a
     `Table`/`Box` caption, reference lists, affiliations, chart labels, and
     publisher `Label: value` fields;
   - front matter zoned above the abstract into title, byline, and affiliations.
3. **Evidence parsing** (`parsers/`)
   - PDF, XLSX/XLSM, DOCX, CSV/TSV, JSON, Markdown, and text;
   - hidden workbook sheets and cached values retained in inventory;
   - page-level OCR fallback when a page has no usable text layer.
4. **Bibliographic reconstruction** (`metadata.py`, `citation.py`, `authors.py`)
   - each field resolved from ranked deterministic sources and recorded with the
     page and verbatim excerpt it came from;
   - publisher self-citations (`Citation:`, `Please cite this article as:`,
     repository `Article:`) parsed for title, journal, volume, issue, pages and
     DOI;
   - journal name recovered from the running head when no citation is printed;
   - byline markup stripped without touching names — ORCID icon glyphs,
     superscript affiliation keys, contribution symbols — while name particles
     such as `van den` and `de` survive;
   - footnote roles attributed to authors through their byline markers;
   - publication date chosen by priority: online > published > issue > accepted;
   - if enabled, DOI-only Crossref repair fills gaps without sending paper text.
5. **Document profile and design classification** (`documents.py`, `taxonomy.py`)
   - one of ten document profiles decides which digest targets apply, what
     sub-heading each section carries, and which evidence slots a complete
     record of this document type should cover;
   - a study-design slug is scored separately, with the document profile
     breaking ties — a reporting guideline *about* systematic reviews is not
     itself a systematic review.
6. **Evidence selection** (`features.py`, `selection.py`)
   - every candidate sentence is described by deterministic feature probes:
     effect size, comparison, direction, population, novelty, limitation,
     method, null result, definition, instruction, quotation, splice;
   - a LexRank centrality score over an idf-weighted overlap graph, implemented
     with the standard library alone, supplies document-level importance;
   - targets are filled by maximal-marginal-relevance under a word budget, in an
     order that stops a limitation from reappearing as a contribution;
   - a section with source material but no matching cue phrase is filled from
     its source section and the record says so.
7. **Contract compilation** (`compiler.py`)
   - exact 11-key YAML and exact eight H2 sections.
8. **Fail-closed QA** (`qa.py`)
   - a registry of independent checks; adding a diagnostic means appending to
     `CHECKS`.
9. **Retrieval regression** (`retrieval.py`)
   - deterministic BM25 tests against full English research questions.
10. **Stage-1 automatic retry** (`pipeline.py`)
   - up to four evidence-budget passes; the first candidate clearing every hard
     gate and the score threshold is returned;
   - the retry never reads the QA report, so a record that fails structurally
     is unchanged by it.
11. **Stage-2 diagnosis-driven repair** (`repair.py`)
   - runs on the best Stage-1 candidate when it still fails and its unclamped
     score is at or above `stage2_min_score`;
   - reads the failing gates and applies one targeted operator per gate to the
     *selection*, then rebuilds the digest, both ledgers and the retrieval
     questions from the amended selection through `UniversalProfile.render`;
   - because every unit stays a verbatim source span, a repair cannot break the
     grounding gate;
   - a proposal is discarded when it makes any previously passing check fail or
     introduces a new gate failure, and accepted only when it strictly improves
     `(fewer errors, higher raw score, fewer warnings)`;
   - `qa.stage2` records every accepted and rejected proposal.

## Grounding by construction

Every prose sentence in the digest is a lightly normalised span of the extracted
source. That is not a claim about the compiler's intentions: `grounding.py`
re-derives it after compilation by reducing both the digest and the source to
their alphanumeric skeleton and requiring each emitted sentence to appear in the
source. Sentences the compiler wrote itself — absence notes, the glossary
fallback — are declared by the profile and audited separately, so the count of
authored sentences is visible rather than assumed.

## Trust boundary

The Markdown is not certified merely because it was generated. `SOURCE_READY`
requires all hard gates. The QA report and the two ledgers are the
machine-readable audit trail; operational details never enter the source
Markdown.
