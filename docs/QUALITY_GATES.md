# Quality Gates

`SOURCE_READY` is fail-closed. A weighted score is reported for diagnosis, but
no score can override a hard error. Each gate below belongs to one check in the
`paper_digest.qa.CHECKS` registry, and every check reports `pass` or `fail`
under `checks.check_status`.

## Contract gates (`schema`)

- exact 11-key YAML sequence;
- exact eight H2 headings and order;
- non-empty title, authors, year, DOI, category, and PDF filename.

## Metadata gates (`metadata`, `authors`)

- journal or publication venue resolved;
- a publication date or year resolved;
- ordered author list resolved, with every author required at or below the
  configured threshold — a compacted list there is a hard error;
- above the threshold the full list is still preferred and is compacted only
  when it would exceed the character budget; the compaction rule must then be
  stated in `Author notes`, and the complete list is retained in the QA sidecar;
- `pdf_path` and `pdf_filename` must agree; with `--verify-pdf-path` the
  canonical PDF must exist at the declared path;
- declared and parsed author counts agree;
- 2-6 research fields and 6-15 retrieval keywords;
- complete `Classification metadata` labels;
- warnings when a core field has no recorded source evidence, when the byline is
  truncated with `et al.`, or when the publication date came from a label other
  than online publication.

## Grounding gates (`grounding`)

- every prose sentence must be a verbatim span of the extracted source, verified
  after compilation on the alphanumeric skeleton of both texts;
- selection strips citation brackets and `(Table 1)` references from inside a
  sentence, so a sentence whose 5-grams are almost all present also counts as
  grounded; a paraphrase or an altered number does not;
- compiler-authored notes are declared by the profile and counted separately.

## Evidence-coverage gates (`coverage`, `evidence`)

- the resolved document profile's evidence slots are all resolved — an unchecked
  slot is a hard error;
- at least half of the applicable slots covered by the source;
- a required slot with no supporting text is reported as `absent_in_source`,
  which is a warning, not an invented value;
- at least ten page-grounded evidence units, none ending at an incomplete text
  boundary.

## Scientific-content gates (`quantitative`, `content`)

- statistical anchors for quantitative designs, plain numeric anchors for
  guidelines, editorials, protocols and correspondence, which legitimately
  report counts rather than estimates;
- a null, uncertainty, or boundary statement retained for quantitative designs;
- limitations, related work, and glossary present;
- a warning when fewer than 40% of result and contribution units are
  self-contained retrieval units naming entity, population, comparison,
  direction and magnitude.

## Integrity gates (`process_leak`, `duplication`, `numeric_consistency`)

- no processing-state, validator, placeholder, or parser-error text;
- no soft-hyphen extraction artifacts;
- no checklist or table rows in the prose;
- no exact duplicate prose units and no sentence repeated across sections;
- headline numbers in the abstract that never reappear elsewhere in the source
  are surfaced as a warning to cross-check against the tables.

## Section-density gates (`section_density`)

Each section must carry its own weight, not just the body as a whole. The floors
follow the WikiLLM source-record standard:

| Section | Floor |
|---|---:|
| One-line Summary | 20 words (30-100 preferred, >140 fails) |
| 1. Document Information | 120 words (>750 fails as audit-heavy) |
| 2. Key Contributions | 100 words, 3-7 explicit items |
| 3. Methodology and Architecture | 300 words |
| 4. Key Results and Benchmarks | 400 words |
| 5. Limitations and Future Work | 150 words |
| 6. Related Work | 80 words |
| 7. Glossary | 60 words, at least 5 entries |

A section below its floor is an **error** when the source could have supplied
the words, and a **warning** naming the shortfall when it could not. The
compiler records, per target, how many quotable words the source offers, so the
two cases are distinguishable rather than conflated: a three-page reporting
guideline has no 300-word methods passage to quote, and saying so is the honest
outcome.

The glossary is the one section measured by completeness rather than length. If
it already lists every term the source defines, a word shortfall is a warning —
padding it would mean inventing glosses the paper never wrote.

## Retrieval-density gates (`density`, `retrieval`)

- a source-relative body floor: `max(400, min(min_body_words, 12% of the source))`,
  because a short source cannot yield a long record;
- hard maximum 6,000 words;
- preferred prose unit maximum 220 words, hard maximum 350;
- digest-to-source ratio warned outside 0.05-0.80;
- at least ten full-question BM25 regressions, all passing in the top ten.

The default score threshold is 0.95. Up to four repair passes increase evidence
budgets and rerun the complete gate set. A hard error always prevents
`SOURCE_READY`, regardless of weighted score.
