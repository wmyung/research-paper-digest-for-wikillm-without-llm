# Deterministic extension

See [DOCUMENT_PROFILES.md](DOCUMENT_PROFILES.md) for adding a document profile
or a study design.

Two other extension points exist:

## A new sentence feature

`features.py` holds one deterministic probe per line of evidence a selector
might want — effect size, comparison, direction, population, novelty,
limitation, null result, and the structural probes that reject definitions,
checklist instructions, interview quotations and column splices. Add a compiled
pattern, a field on `SentenceFeatures`, and a line in `extract`. Selection
weights it by name in `selection.SPECS`.

Structural probes belong in `is_structural_noise` only when a match means the
sentence can never be scientific prose; anything softer belongs in a target's
`penalise` map instead.

## A new quality check

`qa.py` is a registry. A check is a function from `QAContext` to `CheckResult`,
returning errors, warnings, measurements and optionally a score component.
Append it to `CHECKS` and, if it should affect the score, give it a weight in
`WEIGHTS`. Nothing else changes.

Any extension must include synthetic tests for positive selection, negative
selection, sign/exponent/reference-group preservation, null or uncertainty
retention, evidence-page coverage, duplicate limits, and full-question BM25
retrieval. Real papers and outputs remain private opt-in E2E inputs and must not
be committed; `tests/synthetic.py` builds publisher-shaped PDFs — cover sheet,
two-column body, superscript byline, small-print table under its caption — for
anything a fixture is needed for.
