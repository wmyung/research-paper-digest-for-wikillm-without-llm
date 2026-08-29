# Evidence ledgers

Every run writes four artifacts beside each other:

```text
<stem>.md                        the WikiLLM source record
<stem>.qa.json                   the full quality report
<stem>.metadata-evidence.json    where each bibliographic value came from
<stem>.evidence-coverage.json    which evidence slots the source covers
```

The two ledgers mirror the records an LLM-assisted workflow keeps beside a
digest, so a deterministic record and a model-written one can be audited the
same way.

## `metadata-evidence.json`

```json
{
  "schema_version": "2.0",
  "pdf_filename": "spruijt-2019-implementation-of-latent-tuberculosis-infection.pdf",
  "status": "SOURCE_READY",
  "fields": [
    {
      "field": "journal",
      "value": "PLoS ONE",
      "source": "publisher citation string",
      "page": null,
      "source_excerpt": "Spruijt I, Erkens C, … (2019) Implementation of latent tuberculosis …"
    }
  ]
}
```

Each entry answers one question: *why does the frontmatter say this?* `source`
names the resolution path that won — layout title block, publisher citation
string, running head, publisher DOI field, PDF document information, or the
Crossref DOI registry — and `source_excerpt` is the verbatim text it was read
from. A field with no entry was not resolved, and QA warns about it.

## `evidence-coverage.json`

```json
{
  "schema_version": "2.0",
  "document_profile": "empirical_research",
  "coverage_ratio": 1.0,
  "slots": [
    {
      "id": "primary_result_with_effect_size",
      "md_heading": "4. Key Results and Benchmarks",
      "applicable": true,
      "status": "covered",
      "evidence_locations": [
        {"section": "Results", "page": 5, "matched": "95 % CI", "source_excerpt": "…"}
      ]
    }
  ],
  "major_tables": ["Table 1. Characteristics of clients screened for LTBI."],
  "major_figures": ["Fig 1. Flowchart of screening and treatment results."]
}
```

Slot status is one of:

- `covered` — the source contains matching text, and the locations are recorded;
- `absent_in_source` — the slot applies to this document type but the source
  says nothing that matches. This is reported, never filled in;
- `not_applicable` — an optional slot for this document type with no match;
- `unchecked` — never emitted by this pipeline, and a hard QA error if it ever is.

## Reading the ledgers

A low `coverage_ratio` is a statement about the *source*, not about the
compiler. A protocol has no results; a correspondence piece has no methods. The
profile decides which slots apply, so compare `covered_slots` against
`applicable_slots` rather than against the total.
