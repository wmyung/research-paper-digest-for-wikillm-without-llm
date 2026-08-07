# Compatibility Baseline

The overlay was checked against the Firecrawl `main` route and Compose layout
visible on 2026-08-07:

- monorepo API source under `apps/api`;
- v2 router at `apps/api/src/routes/v2.ts`;
- existing multipart parsing based on `multer`;
- existing `/v2/parse` and `/v2/parse/upload-url` route region;
- Compose API service named `api`;
- shared Compose network named `backend`.

Because `main` is mutable, the installer verifies the parse import and route
anchors before editing. If either is absent, it stops without modifying the
router. Review the upstream diff and update the installer tests before changing
anchors.
