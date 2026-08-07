# Firecrawl Integration

## Added files

```text
apps/api/src/controllers/v2/paper-digest.ts
apps/paper-digest/**
docker-compose.paper-digest.yml
```

## Route

The installer adds:

```ts
v2Router.post(
  "/paper-digest",
  authMiddleware(RateLimiterMode.Scrape, { allowKeyless: true }),
  countryCheck,
  checkCreditsMiddleware(1),
  paperDigestUploadMiddleware,
  wrap(paperDigestController),
);
```

The controller accepts `files` as a repeated multipart field and `file` as a
single-file compatibility alias. It forwards the original MIME type and
filename to the Python sidecar using Node's native `fetch`, `FormData`, and
`Blob` implementations, so no new JavaScript package is required.

## Environment variables

- `PAPER_DIGEST_SERVICE_URL`: default
  `http://paper-digest:8088/v1/digest`.
- `PAPER_DIGEST_TIMEOUT_MS`: default `300000`.

The sidecar can use DOI-only Crossref metadata repair by default. Set
`"enable_doi_metadata": false` in request options for an offline run.

## Upgrade behavior

The installer relies on two small route anchors. If an upstream Firecrawl
change removes either anchor, installation stops with an error. This is
intentional: silently patching the wrong route is less safe than requiring a
human review. The installer is idempotent and creates a one-time
`v2.ts.paper-digest.bak` unless `--no-backup` is supplied.
