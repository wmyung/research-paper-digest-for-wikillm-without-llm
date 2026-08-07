# WikiLLM Paper Digest

**Research paper digest for WikiLLM without an LLM — CLI, local web app, and MCP server.**

[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-3776AB.svg)](https://www.python.org/)
[![No LLM](https://img.shields.io/badge/LLM-not%20required-0a6b52.svg)](docs/NO_LLM_SCOPE.md)
[![Quality gate](https://img.shields.io/badge/SOURCE__READY-%E2%89%A595%25-7a4f01.svg)](docs/QUALITY_GATES.md)
[![License: AGPL v3](https://img.shields.io/badge/License-AGPL%20v3-blue.svg)](LICENSE)

WikiLLM Paper Digest turns a research-paper PDF and optional supplements into
grounded, searchable WikiLLM source Markdown. It uses deterministic layout
parsing, OCR, section rules, extractive evidence ranking, automatic repair
passes, and BM25 retrieval regression—without a generative model, embedding
model, reranker, VLM, model API key, or GPU.

It is inspired by **[Firecrawl](https://github.com/firecrawl/firecrawl)** and
includes an optional Firecrawl v2 overlay. It is built to produce source files
for the workflow described in **[joonan30's WikiLLM research-paper
gist](https://gist.github.com/joonan30/cbce305684d079dbe9a3fbaefe4e3959)**.
This project is independent and is not an official Firecrawl or WikiLLM
distribution.

The repository contains no research papers, paper-derived Markdown, patient
data, personal examples, credentials, or user-specific fixtures.

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
git clone git@github.com:wmyung/research-paper-digest-for-wikillm-without-llm.git
cd research-paper-digest-for-wikillm-without-llm
python3 -m venv .venv
.venv/bin/python -m pip install -e "apps/paper-digest[dev]"
```

### 1. Human CLI

```bash
.venv/bin/paper-digest paper.pdf -o output
.venv/bin/paper-digest paper.pdf supplement.pdf tables.xlsx -o output
.venv/bin/paper-digest --offline paper.pdf -o output
```

Every run writes two files:

- `*.md` — the grounded WikiLLM source Markdown candidate;
- `*.qa.json` — the score, hard-gate checks, retrieval regressions, and exact
  unresolved gaps.

The process exits `0` only for `SOURCE_READY`; an uncertified result exits `2`
while still writing both artifacts.

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
  profile: "auto"
)
```

It returns artifact paths, status, quality score, and QA errors. It does not
send paper content to the agent host or any external inference service. Agents
must treat only `SOURCE_READY` as certified.

---

## What “without an LLM” Means

| Capability | Implementation |
|---|---|
| Layout and reading order | PyMuPDF blocks, coordinates, fonts, two-column rules |
| Scanned pages | Local Tesseract OCR fallback |
| Study-design routing | Finite lexical and structural scoring |
| Digest writing | Extractive, page-grounded evidence selection |
| Missing coverage | Up to four deterministic repair passes |
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

- exact 11-key YAML frontmatter and eight required H2 sections;
- page-addressable evidence ledger;
- authorship and bibliographic consistency checks;
- methods, results, null-result, and limitation boundaries;
- length, density, paragraph, exact-duplicate, and near-duplicate checks;
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
.venv/bin/ruff check apps/paper-digest/src tests scripts
.venv/bin/ruff format --check apps/paper-digest/src tests scripts
.venv/bin/pytest -q
.venv/bin/python scripts/no-llm-audit.py .
.venv/bin/python scripts/validate-release.py
```

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

See [Architecture](docs/ARCHITECTURE.md), [Compatibility](docs/COMPATIBILITY.md),
and [Profile Authoring](docs/PROFILE_AUTHORING.md).

---

## Keywords for Discovery

`research-paper-digest-for-wikillm-without-LLM`, `research paper PDF to
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
