# WikiLLM Paper Digest

**Research paper digest for WikiLLM without an LLM — CLI, local web app, and MCP server.**

[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-3776AB.svg)](https://www.python.org/)
[![No LLM](https://img.shields.io/badge/LLM-not%20required-0a6b52.svg)](docs/NO_LLM_SCOPE.md)
[![Quality gate](https://img.shields.io/badge/SOURCE__READY-%E2%89%A595%25-7a4f01.svg)](docs/QUALITY_GATES.md)
[![License: AGPL v3](https://img.shields.io/badge/License-AGPL%20v3-blue.svg)](LICENSE)

WikiLLM Paper Digest turns a research-paper PDF and optional supplements into
grounded, searchable WikiLLM source Markdown. It uses deterministic layout
analysis, OCR, document profiles, feature-based extractive evidence ranking with
LexRank centrality, automatic repair passes, a post-hoc verbatim grounding audit,
and BM25 retrieval regression—without a generative model, embedding model,
reranker, VLM, model API key, or GPU.

It is inspired by **[Firecrawl](https://github.com/firecrawl/firecrawl)** and
includes an optional Firecrawl v2 overlay. It is built to produce source files
for the workflow described in **[joonan30's WikiLLM research-paper
gist](https://gist.github.com/joonan30/cbce305684d079dbe9a3fbaefe4e3959)**.
This project is independent and is not an official Firecrawl or WikiLLM
distribution.

The repository contains no research papers, paper-derived Markdown, patient
data, personal examples, credentials, or user-specific fixtures.

## Optional validated recovery cascade

The deterministic compiler remains model-free. For residual failures, the
repository also includes the portable
[`validated-cascade-workflow`](skills/validated-cascade-workflow/SKILL.md)
skill. It preserves valid program output, tries deterministic repair first,
uses a configured language model only for eligible residual cases, and requires
the same fail-closed validation plus commit readback. The skill is
model-neutral and artifact-neutral; paper-specific rules belong in adapters.

Glossary QA rejects numbered placeholders such as `Term 1`. A syntactically
long list of extracted prose is not accepted as a semantic glossary.

---

## Why This Is Needed: Stop Paying an LLM for Every Paper

Using an LLM to digest papers one at a time has two compounding costs. Every
long PDF, supplement, retry, and validation pass consumes more tokens, while
serial inference, rate limits, model queues, and network round trips make large
collections slow to ingest. The same corpus can also produce different source
records after a model or prompt change.

WikiLLM Paper Digest moves that repetitive ingestion stage to a deterministic,
local compiler. It uses **zero LLM tokens**, can run offline, supports parallel
and batch execution, and produces the same Markdown contract through CLI, web,
MCP, and Firecrawl. The machine-readable QA report and page evidence ledger make
each accepted record auditable before it enters WikiLLM.

| Per-paper LLM digestion | WikiLLM Paper Digest |
|---|---|
| Token cost grows with pages, supplements, and retries | Zero LLM-token cost for PDF ingestion |
| Inference queues and API round trips slow large batches | Local deterministic processing; parallelizable |
| Output can drift with prompts and model versions | Reproducible rules, schema, and hard gates |
| Validation often requires another model pass | Built-in 0.95 fail-closed QA and BM25 regression |

This does not pretend that rules can make unsupported semantic judgments. It
extracts and validates source-grounded records, fails visibly when evidence is
insufficient, and reserves expensive LLM work for tasks where it adds more
value: cross-paper synthesis, hypothesis generation, and genuinely ambiguous
review.

---

## Three Ways to Use It

| User | Interface | Command or endpoint |
|---|---|---|
| Human in a terminal | CLI | `paper-digest` |
| Human in a browser | Private local web app | `paper-digest-web --open` |
| AI agent | MCP stdio tool | `paper-digest-mcp` |
| Firecrawl deployment | Authenticated HTTP overlay | `POST /v2/paper-digest` |

All interfaces call the same deterministic compiler and return the same
Markdown contract and QA evidence.

---

## Quick Start

```bash
git clone git@github.com:wmyung/wikillm-digest-noLLM.git
cd wikillm-digest-noLLM
python3 -m venv .venv
.venv/bin/python -m pip install -e "apps/paper-digest[dev]"
```

### 1. Human CLI

```bash
.venv/bin/paper-digest paper.pdf -o output
.venv/bin/paper-digest paper.pdf fulltext.xml supplement.pdf tables.xlsx -o output
.venv/bin/paper-digest --offline paper.pdf -o output
.venv/bin/paper-digest paper.pdf -o output --source-ready-threshold 0.8 --stage2-max-rounds 3
```

Every run writes four audit files; a failed run writes one additional repair
packet:

- `*.md` — the grounded WikiLLM source Markdown candidate;
- `*.qa.json` — the score, hard-gate checks, retrieval regressions, and exact
  unresolved gaps;
- `*.metadata-evidence.json` — for each bibliographic value, where it came from,
  on which page, and the verbatim excerpt it was read from;
- `*.evidence-coverage.json` — which evidence slots of the resolved document
  profile the source actually covers, and which it does not.
- `*.luna-repair-input.json` (`NOT_SOURCE_READY` only) — JSON-first failure
  diagnosis, page-addressable source sections and scored grounded candidate IDs.

An optional small-model review remains outside this package. Give that model the
repair-input JSON instead of the full PDF, have it return only a
`luna_repair_plan_v1` file, then rerun with `--repair-plan plan.json`. The
compiler accepts no supplied prose: it validates the DOI and PDF SHA-256 and can
only assign candidates that it extracted and grounded itself.

See [Evidence Ledgers](docs/EVIDENCE_LEDGERS.md) for how to read the last two.

The process exits `0` only for `SOURCE_READY`; an uncertified result exits `2`
while still writing both artifacts.

#### Throughput

Roughly **2-3 seconds per paper** on one core for an ordinary journal article
with a text layer, so about **1,500 papers per hour per core**. Papers are
independent, so this scales with cores: a 10-core laptop reaches five figures an
hour.

Two things make it much slower. A scanned page falls back to OCR and costs
seconds *per page*. A several-hundred-page book costs tens of seconds. A mixed
corpus of articles, scans and books measured about 10 seconds per document.

### 2. Private Local Web App

```bash
.venv/bin/paper-digest-web --open
```

Then open <http://127.0.0.1:8088/>. Drop the canonical PDF and any supplements,
run the conversion, and download Markdown plus its QA report. The default bind
address is localhost, responses are `no-store`, and uploaded files live only in
a per-request temporary directory.

### 3. AI Agent over MCP

Add this stdio server to an MCP-compatible host:

```json
{
  "mcpServers": {
    "wikillm-paper-digest": {
      "command": "/absolute/path/to/.venv/bin/paper-digest-mcp"
    }
  }
}
```

The server exposes one deliberately narrow tool:

```text
digest_research_paper(
  input_paths: ["/absolute/path/paper.pdf", ...],
  output_dir: "/absolute/path/output",
  offline: false,
  profile: "auto",
  source_ready_threshold: 0.95,
  enable_stage2: true,
  stage2_min_score: 0.70,
  stage2_max_rounds: 3
)
```

It returns artifact paths, status, quality score, and QA errors. It does not
send paper content to the agent host or any external inference service. Agents
must treat only `SOURCE_READY` as certified.

---

## What “without an LLM” Means

| Capability | Implementation |
|---|---|
| Reading order | Column bands from an x-coverage histogram, not content-stream order |
| Running heads, cover sheets | Cross-page recurrence with digits masked; repository cover sheets detected and excluded |
| Tables, captions, references | Caption-anchored table zones and a two-pass body-font estimate keep display matter out of the prose |
| Title, byline, affiliations | Front-matter zoning above the abstract; ORCID glyphs and superscript keys stripped without touching names |
| Journal, dates, DOI | Publisher self-citations, running heads and labelled fields, each recorded with its page and excerpt |
| Scanned pages | Local Tesseract OCR fallback |
| Document routing | Ten document profiles decide which sections apply and which evidence slots exist |
| Study-design routing | Weighted lexical scoring, with the document profile breaking ties |
| Sentence importance | Standard-library LexRank over an idf-weighted overlap graph |
| Digest writing | Extractive selection by maximal-marginal-relevance under a word budget |
| Fabrication control | Post-hoc verbatim grounding audit over the alphanumeric skeleton |
| Thin sections | Cue-anchored passage expansion: the paragraph around a cue is taken whole |
| Missing coverage | Up to four deterministic repair passes, then an explicit statement of absence |
| Stalled records | Stage-2 repair: one targeted operator per failing gate, under a monotone acceptance rule |
| Retrieval validation | BM25 full-question regression suite |
| Bibliographic repair | Optional DOI-only Crossref lookup |
| LLM, embedding, VLM calls | None |

The optional Crossref request contains only a public DOI. `--offline` or
`offline: true` disables it. DOI repair is enabled by default so valid papers
with sparse cover-page metadata can complete the same quality gate. Paper text, supplements, generated Markdown,
credentials, and user data are never sent to Crossref.

Tesseract's OCR engine may use its own trained recognition data; it is not a
generative LLM and performs no network inference.

---

## Quality Contract

The compiler does not claim success because it produced text. `SOURCE_READY`
requires every hard gate and a quality score of at least `0.95`.

The threshold and Stage-2 window can be configured consistently through CLI,
HTTP options, or MCP. Lowering the threshold never suppresses a hard error;
any error still forces `NOT_SOURCE_READY`.

- exact 11-key YAML frontmatter and eight required H2 sections;
- per-section word floors, with a shortfall attributed to the source when the
  source genuinely cannot supply it;
- **every prose sentence verified as a verbatim span of the source**, checked
  after compilation rather than assumed;
- a page-addressable evidence ledger and a per-slot coverage ledger;
- authorship and bibliographic consistency checks, each value traced to its page;
- methods, results, null-result, and limitation boundaries;
- source-relative length, density, paragraph, duplicate, and cross-section
  repetition checks;
- no checklist rows, table cells, figure legends, or interview quotations in the
  prose;
- at least ten full research-question BM25 regressions;
- no invented value when the source does not contain the required evidence.

When a damaged or evidence-poor input still cannot pass after repair, the
program completes the Markdown candidate and QA report but returns
`NOT_SOURCE_READY` with exact gaps. It never disguises that state as success.
See [Quality Gates](docs/QUALITY_GATES.md) and [No-LLM Scope](docs/NO_LLM_SCOPE.md).

---

## WikiLLM Source Contract

```text
title, authors, year, doi, category, pdf_path, pdf_filename,
source_collection, source_format, text_extractor, text_extracted_date

## One-line Summary
## 1. Document Information
## 2. Key Contributions
## 3. Methodology and Architecture
## 4. Key Results and Benchmarks
## 5. Limitations and Future Work
## 6. Related Work
## 7. Glossary
```

The output is designed to be placed in the `sources/` stage of the linked
WikiLLM research-paper workflow before category, overview, and concept
synthesis.

---

## Firecrawl Integration

Apply the guarded overlay to a compatible self-hosted Firecrawl checkout:

```bash
python scripts/apply-firecrawl-overlay.py /path/to/firecrawl
cd /path/to/firecrawl
docker compose -f docker-compose.yaml -f docker-compose.paper-digest.yml up --build
```

```bash
curl -X POST http://localhost:3002/v2/paper-digest \
  -H "Authorization: Bearer fc-YOUR-KEY" \
  -F "files=@paper.pdf" \
  -F 'options={"profile":"auto","strict":true,"enable_doi_metadata":false}'
```

HTTP `200` means `SOURCE_READY`. HTTP `422` contains the completed Markdown
candidate and exact QA gaps. Raw Markdown is returned only for certified
output. See [Firecrawl Integration](docs/FIRECRAWL_INTEGRATION.md).

---

## Verification

```bash
.venv/bin/ruff check --config apps/paper-digest/pyproject.toml apps/paper-digest/src tests scripts
.venv/bin/ruff format --check --config apps/paper-digest/pyproject.toml apps/paper-digest/src tests scripts
.venv/bin/pytest -q
.venv/bin/python scripts/no-llm-audit.py .
.venv/bin/python scripts/validate-release.py
```

The test suite builds publisher-shaped PDFs in `tests/synthetic.py` — repository
cover sheet, running head, two-column body, superscript byline, small-print table
under its caption, reference list — so layout analysis is exercised end to end
without committing anyone's paper.

### Measuring quality on your own corpus

```bash
.venv/bin/python scripts/benchmark.py /path/to/pdfs --offline --markdown
.venv/bin/python scripts/benchmark.py /path/to/pdfs --reference /path/to/reference-md --out report.json
```

Without `--reference` the report covers certification rate, grounding ratio,
evidence coverage, digest-to-source ratio, and retrieval pass rate. With
`--reference` it additionally compares each record against a reference Markdown
file — for example one written with an LLM — on title and DOI agreement, author
overlap, numeric recall, and per-section token F1. The comparison is string and
token arithmetic; no model is involved.

Private E2E inputs can be supplied through `PAPER_DIGEST_E2E_PDF` and related
environment variables. They are processed locally and never copied into this
repository.

---

## Architecture

```text
CLI ───────────────┐
Local Web App ─────┼──> deterministic paper compiler ──> Markdown + QA JSON
MCP Agent Tool ────┤       layout / OCR / evidence / repair / BM25 gates
Firecrawl Overlay ─┘
```

### Compatibility with the LLM Wiki source-record standard

The output targets the `sources/` stage of
[joonan30's LLM Wiki workflow](https://gist.github.com/joonan30/cbce305684d079dbe9a3fbaefe4e3959)
and is checked against the reference standard published in
[paper-to-llm-wiki-digest](https://github.com/wmyung/paper-to-llm-wiki-digest).
Records produced here pass that project's `validate_source_md.py
--require-classification` and `audit_source_density.py`.

One divergence is deliberate. Where the reference validator treats a section
below its floor as a hard error, this compiler first measures how many quotable
words the source actually offers for that section. When the source cannot supply
the floor — a short reporting guideline with a 240-word development section, for
example — the record is certified with an explicit warning naming the shortfall
and its cause, rather than failed for a deficiency in the paper. Everything the
source *can* supply is still required.

See [Architecture](docs/ARCHITECTURE.md), [Document Profiles](docs/DOCUMENT_PROFILES.md),
[Evidence Ledgers](docs/EVIDENCE_LEDGERS.md), [Quality Gates](docs/QUALITY_GATES.md),
[Compatibility](docs/COMPATIBILITY.md), and [Profile Authoring](docs/PROFILE_AUTHORING.md).

---

## Keywords for Discovery

`wikillm-digest-noLLM`, `research-paper-digest-for-wikillm-without-LLM`, `research paper PDF to
Markdown`, `PDF to Markdown without LLM`, `WikiLLM paper digest`, `WikiLLM
sources`, `academic paper parser`, `scientific paper extraction`, `deterministic
PDF extraction`, `offline paper digest`, `local-first research tools`, `no LLM
document processing`, `grounded Markdown`, `evidence-based paper summary`,
`extractive paper digest`, `paper OCR`, `Tesseract academic PDF`, `PyMuPDF paper
parser`, `BM25 research retrieval`, `research knowledge base`, `AI agent paper
tool`, `MCP paper server`, `MCP research tool`, `Codex paper tool`, `Claude paper
tool`, `Firecrawl paper PDF`, `Firecrawl PDF to Markdown`, `Joonan WikiLLM`,
`LLM Wiki for scientists`, `research paper knowledge ingestion`, `quality-gated
Markdown`, `SOURCE_READY`, `Crossref metadata`, `paper supplements parser`,
`private paper processing`, `local research paper web app`, `paper digest CLI`

---

## License

AGPL-3.0-only. Firecrawl is separately licensed; see
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

---

*WikiLLM Paper Digest — grounded research-paper Markdown, without an LLM.*
