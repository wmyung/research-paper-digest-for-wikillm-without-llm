# Changelog

## 2.2.0

Stage 1 recompiles the whole digest with a larger evidence budget and never
reads the QA report, so a record that fails structurally is unchanged by all
four of its passes. This release adds a second stage that reads the failing
gates instead.

### Stage-2 diagnosis-driven repair (`repair.py`)

- Ten operators, one per failing gate: drop leaked, repeated or ungrounded
  units; refill or reallocate an underdeveloped section; correct the
  Key Contributions band; recover quantitative anchors; restore a boundary
  statement; trim density; and repair a failing retrieval question.
- Operators amend the *selection* and the digest is rebuilt from it by the new
  `UniversalProfile.render`, so the prose, both ledgers and the retrieval
  questions stay consistent and every unit remains a verbatim source span. A
  repair therefore cannot break the grounding gate.
- `reallocate_units` revisits Stage 1's irrevocable first-claim rule: a sentence
  moves to a section under its floor from one above its own when it scores for
  both. This is the repair Stage 1 structurally cannot make.
- Acceptance is monotone: a proposal is discarded if it makes any previously
  passing check fail or introduces a new gate failure, and accepted only if it
  strictly improves `(fewer errors, higher raw score, fewer warnings)`. Gate
  identity ignores the measurements an error quotes, so a partial repair of a
  section reads as progress rather than as a new failure.
- When no single operator helps, each operator blocked by a regression is
  retried paired with one follow-up and the pair is judged as one atomic move.
- `qa.stage2` records every accepted and rejected proposal with the reason.
- A shortfall the source cannot fill, or one fillable only with near-duplicate
  prose, is left standing; the record stays `NOT_SOURCE_READY`.

### Score reporting

- `raw_quality_score` is reported alongside `quality_score`. The published score
  is clamped to `threshold - 0.01` for every record carrying a hard error, which
  collapses an entire failing benchmark onto one value and makes it useless for
  ranking near misses. Stage 2 and triage use the unclamped score.

### Options

- `enable_stage2` (default true), `stage2_min_score` (default 0.70) and
  `stage2_max_rounds` (default 3).

### Repository

- Renamed from `research-paper-digest-for-wikillm-without-llm` to
  `wikillm-digest-noLLM`. GitHub redirects the previous URL, and the old name is
  kept as a discovery keyword in both READMEs. The product name
  ("WikiLLM Paper Digest"), the Python distribution (`wikillm-paper-digest`) and
  the `paper-digest` commands are unchanged.

## 2.1.0

Aligned the record with the LLM Wiki source-record standard published in
`wmyung/paper-to-llm-wiki-digest`, measured by running that project's own
`validate_source_md.py` and `audit_source_density.py` against this compiler's
output. A representative empirical paper went from two hard failures to none.

### Per-section density gates

- New `section_density` check enforcing the standard's per-section word floors,
  the 3-7 range for Key Contributions, the five-entry minimum for the Glossary,
  and the one-paragraph rule for the One-line Summary.
- A section below its floor is an error only when the source could have supplied
  the words. The compiler now records, per target, how many quotable words the
  source offers, so a short paper is reported as a source limitation rather than
  failed for a deficiency in the paper.
- A glossary listing every term the source defines is complete even when short;
  the shortfall is a warning, because padding it would mean inventing glosses.

### Cue-anchored passage expansion

- A limitations passage is contiguous prose: authors signal it once and then
  continue. Sentences beside a cue-matching sentence, inside the same paragraph,
  are now taken with it. This fills thin sections without loosening what a cue
  means, and every added sentence is still verbatim source text.

### Limitations recall

- Impersonal and third-person limitation language is recognised: "cannot be
  excluded", "is limited by", "was restricted to", "should be interpreted",
  "misclassification", "no causal".
- A sentence's position within its section is scored, because a limitations
  passage sits at the end of a Discussion.

### Glossary recall

- Reverse-order definitions — "IGRA (interferon gamma release assay)" — are now
  recognised alongside "interferon gamma release assay (IGRA)".
- An embedded acronym contributes all its letters, so "latent TB infection"
  correctly abbreviates to LTBI rather than LTI.
- "also known as", "that is" and "i.e." aliases are captured.
- Recurring acronyms the source never expands are named as such instead of being
  silently dropped. Speaker codes and table keys such as `PHS1` are excluded.

### Authorship and provenance

- Above the author threshold the full list is still preferred and is compacted
  only when it would exceed the character budget; the rule is then stated in
  `Author notes` and the complete list is retained in the QA sidecar.
- A compacted list at or below the threshold is a hard error.
- `pdf_path` and `pdf_filename` must agree, and `--verify-pdf-path` requires the
  canonical PDF to exist at the declared path.

### Retrieval density

- Prose units are packed to 110 words rather than 170, matching the reference
  records, which average about 45 words per unit and never exceed 110.

### Release packaging

- `scripts/build-release.py` no longer packages `node_modules`, `.git`,
  `.github` or `.DS_Store`. The archive was 4.5 MB across 236 files; it is now
  215 KB across 103.
- The output directory defaults to `dist/` beside the repository rather than an
  absolute `/mnt/data` path that existed only on one machine.
- A new `--name` option decides the archive name, so a checkout sitting in a
  directory with a different name still produces correctly named archives.

### Tests

- The synthetic fixture is now a realistic 1,700-word paper with a full
  acronym set, so the end-to-end test exercises the density gates rather than
  passing on a stub.
- New `tests/test_release_archive.py` covers what the release archive may and
  may not contain. Suite: 113 tests.

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
