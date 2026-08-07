# Quality Gates

`SOURCE_READY` is fail-closed. A weighted score is reported for diagnosis, but
no score can override a hard error.

## Contract gates

- exact 11-key YAML sequence;
- exact eight H2 headings and order;
- non-empty title, authors, year, DOI, category, and PDF filename;
- no processing-state, validator, placeholder, or parser-error text in the
  source Markdown.

## Metadata gates

- ordered author list resolved;
- all authors required when count is at or below the configured threshold;
- declared and parsed author counts agree;
- journal and a publication date/year resolved;
- 2-6 research fields and 6-15 retrieval keywords;
- complete `Classification metadata` labels.

## Scientific-content gates

- deterministic study-design classification and page-grounded evidence ledger;
- important null or boundary results retained;
- limitations, related work, and glossary present;
- minimum quantitative-anchor count for quantitative profiles;
- supplied supplements parse without silent failure.

## Retrieval-density gates

- preferred body range 2,000-4,200 words;
- hard maximum 6,000 words;
- preferred prose unit maximum 220 words;
- hard prose unit maximum 350 words;
- duplicate and near-duplicate units audited separately;
- at least ten full-question BM25 regressions, all passing in the top ten.

The default score threshold is 0.95. Up to four repair passes increase evidence
budgets and rerun the complete gate set. A hard error always prevents
`SOURCE_READY`, regardless of weighted score.
