# Changelog

## 2.0.0

Rebuilt the three stages that determine digest quality — layout analysis,
bibliographic resolution, and evidence selection — and made grounding a checked
property rather than a design intention.

### Layout analysis (new `parsers/layout.py`)

- Reading order now comes from column bands found in an x-coverage histogram,
  not from PDF content-stream order. Narrow blocks are no longer pulled into a
  neighbouring column.
- Running heads and feet are detected by cross-page recurrence with digits
  masked, so a footer carrying the journal name and a page number is recognised
  as furniture — and mined for the journal name.
- Repository and accepted-manuscript cover sheets are detected and excluded.
  Previously a White Rose deposit banner could be read as the article title.
- The body font size is estimated twice: the first modal size is skewed by dense
  reference and table text, so it is re-measured from blocks the first pass
  called body and the page re-classified.
- Table zones are anchored to a `Table`/`Box` caption, which keeps multi-page
  checklists and data tables out of the prose.
- Front matter above the abstract is zoned into title, byline, and affiliations;
  article-type labels such as `RESEARCH ARTICLE` are separated from the title.
- Chart axis labels, legend keys, decorations, and reference lists are tagged and
  excluded from prose.

### Bibliographic resolution

- Every field records the source that resolved it, the page, and a verbatim
  excerpt, written to `*.metadata-evidence.json`.
- New `citation.py` parses publisher self-citations — PLOS `Citation:`, Elsevier
  `Please cite this article as:`, repository `Article:` — for title, journal,
  volume, issue, pages, article number and DOI.
- Journal names are recovered from running heads. The hardcoded list of journal
  names is gone.
- New `authors.py` strips ORCID icon glyphs, superscript affiliation keys and
  contribution symbols without touching names, keeps particles such as
  `van den` and `de`, and attributes footnote roles to authors through their
  byline markers.
- Publication dates follow an explicit priority: online > published > issue >
  accepted.

### Document profiles and selection

- Ten document profiles (`documents.py`) decide which digest sections apply,
  what sub-heading each carries, and which evidence slots exist. A study
  protocol no longer produces a Results section.
- The design taxonomy is separate from the document profile, and the profile
  breaks ties: a reporting guideline about systematic reviews is now categorised
  as a reporting guideline.
- New `features.py` describes each candidate sentence with deterministic probes
  and rejects glossary definitions, checklist instructions, interview
  quotations, unbalanced quote fragments, column splices, figure-legend
  descriptions and publisher boilerplate.
- New `selection.py` scores candidates per target, adds a standard-library
  LexRank centrality signal, and selects by maximal-marginal-relevance under a
  word budget. Target order stops a limitation from reappearing as a
  contribution.
- A section with source material but no matching cue phrase is filled from its
  source section and says so in the report, instead of being silently empty.
- The glossary emits only definitions the source states. The filler gloss
  "An author-supplied or deterministically selected indexing term" is gone.

### Quality assurance

- `qa.py` is now a registry of independent checks; each reports `pass` or `fail`
  under `checks.check_status`.
- **New hard gate:** every prose sentence must be a verbatim span of the
  extracted source, verified after compilation on the alphanumeric skeleton of
  both texts. Compiler-authored notes are declared and counted separately.
- **New hard gates:** unchecked evidence slots, checklist and table rows in the
  prose, and sentences repeated across sections.
- The body-length floor is now relative to the source, so a short paper is no
  longer failed for being short.
- Quantitative anchors are profile-aware: guidelines, editorials, protocols and
  correspondence are judged on plain numeric anchors rather than effect sizes.
- New diagnostics: abstract numbers that never reappear elsewhere in the source,
  and the proportion of result units that are self-contained retrieval units.
- Paper-specific regexes accumulated for one GWAS paper were removed in favour
  of structural detection.

### Artifacts and tooling

- Each run now writes `*.metadata-evidence.json` and `*.evidence-coverage.json`
  beside the Markdown and QA report.
- New `scripts/benchmark.py` measures certification rate, grounding, coverage,
  density and retrieval over a corpus, and can compare each record against a
  reference Markdown file on title, DOI, author overlap, numeric recall and
  per-section token F1.
- New `tests/synthetic.py` builds publisher-shaped PDFs — cover sheet, running
  head, two-column body, superscript byline, small-print table under its
  caption, reference list — so layout analysis is tested end to end without
  committing anyone's paper. The suite grew from 24 to 92 tests.
- A malformed byline degrades to `NOT_SOURCE_READY` instead of raising.
- Two documents that resolve to the same filename stem — which happens when
  neither yields an author or a year — no longer overwrite each other in a batch
  run. Re-running the same paper still replaces its own record in place.
- Suspended hyphens (`author- and index-level`) survive de-hyphenation.

## 1.3.1

- Documented the primary economic and throughput case for deterministic paper
  ingestion: zero per-paper LLM-token cost and no inference queue latency.
- Repaired discretionary PDF line-break hyphens without changing real
  compounds.
- Added fail-closed detection for caption fragments, publisher subheadings,
  authorship boilerplate, incomplete statistics, and soft-hyphen artifacts.
- Added generic extraction-quality regression tests based only on synthetic
  text.

## 1.3.0

- Named the project WikiLLM Paper Digest and documented the
  `research-paper-digest-for-wikillm-without-LLM` purpose.
- Added a private localhost web app with drag-and-drop conversion and artifact
  downloads.
- Added a standards-based MCP 2.0 stdio server for local agent use.
- Unified CLI, web, MCP, sidecar API, and Firecrawl overlay on the same compiler
  and quality contract.
- Added product metadata, discovery keywords, privacy boundaries, and explicit
  Firecrawl inspiration and Joonan WikiLLM workflow references.

## 1.2.0

- Replaced paper-specific profiles with one deterministic universal compiler.
- Added multi-pass evidence repair, OCR fallback, DOI-only metadata repair, and
  page-grounded evidence ledgers.
- Raised the certification threshold to 0.95 and made retrieval regression a
  hard gate.
- Removed real-paper outputs, facts, fixtures, and paper-specific examples from
  the repository; private E2E inputs are environment-only.
- Preserved the Firecrawl overlay, archive guards, fixed Markdown contract, and
  no-LLM runtime audit.
