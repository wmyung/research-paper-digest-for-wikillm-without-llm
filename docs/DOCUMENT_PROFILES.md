# Document profiles

The eight level-2 headings of a WikiLLM source record are fixed. What belongs
under them is not: a study protocol has no results to report, an editorial has
an argument rather than a study design, and a correction notice is not a paper
at all. A document profile records that difference.

Profiles live in `apps/paper-digest/src/paper_digest/documents.py`. The module
is deliberately dependency-free — the evidence ledger, the QA layer and the
compiler all read it, so it sits below them in the import graph.

## What a profile decides

| Field | Effect |
|---|---|
| `applicable_targets` | Which digest sections may be filled at all. A protocol excludes `results`, so its Results section states that the document type reports no findings instead of inventing them. |
| `subheadings` | The H3 label each section carries, so a review reads "Search, eligibility, appraisal, and synthesis" where an empirical study reads "Design, data, measurements, and analysis". |
| `slots` | The evidence a complete record of this document type should contain. These drive `evidence-coverage.json`. |
| `strong_signals` / `weak_signals` | Weighted lexical evidence for classification. Title evidence outweighs body evidence, because a paper *about* systematic reviews is full of systematic-review vocabulary without being one. |
| `category_bias` | Study-design slugs this document type usually carries, used to break ties in `taxonomy.py`. |

## The ten profiles

- `empirical_research` — the default: a study with a design, a population and findings.
- `systematic_review_meta_analysis` — recognised from its own methods (`we searched`, PROSPERO, screening in duplicate), not from its subject matter.
- `methods_tool` — a method, model or software contribution, benchmarked against baselines.
- `study_protocol` — planned work; `results` is not applicable.
- `narrative_review` — themes and an organising framework rather than pooled estimates.
- `case_report` — presentation, investigations, management, outcome.
- `guideline_consensus` — a reporting standard or consensus statement; its "results" are recommendations and items.
- `editorial_commentary` — a position and its evidence base.
- `letter_response_correspondence` — short by nature; a thin record is expected rather than a defect.
- `excluded_non_paper` — corrections, errata, retraction notices; recorded, not digested as independent studies.

## Adding a profile

1. Add a `DocumentProfile` to `PROFILES` with its slots, sub-headings and signals.
2. Prefer signals that describe *what the document did* over signals that
   describe *what it is about*. `\bwe systematically searched\b` is a good
   signal; `\bsystematic review\b` is not, because it matches every paper on the
   subject.
3. Add a classification test to `tests/test_documents_and_coverage.py` that
   includes at least one near-miss the profile must **not** claim.
4. Add slot tests covering `covered`, `absent_in_source` and `not_applicable`.

## Extending the design taxonomy

`taxonomy.py` carries the `category` frontmatter slug, which is a study-design
label rather than a document type. Add classification terms and source-selection
cues, never paper identifiers or paper-specific expected facts. Strong terms are
scored far above weak ones and title occurrences far above body occurrences.

Any extension must include synthetic tests for positive selection, negative
selection, sign/exponent/reference-group preservation, null or uncertainty
retention, evidence-page coverage, duplicate limits, and full-question BM25
retrieval. Real papers and outputs remain private opt-in E2E inputs and must not
be committed; `tests/synthetic.py` builds publisher-shaped PDFs for anything a
fixture is needed for.
