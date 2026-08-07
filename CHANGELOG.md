# Changelog

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
