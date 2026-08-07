# Patch note

`firecrawl-v2-paper-digest.patch` shows the minimal route change against the
current Firecrawl v2 route shape. It does not contain the Python sidecar.
Use `scripts/apply-firecrawl-overlay.py` as the supported installer because it
copies all required files, is idempotent, makes a route backup, and fails when
upstream anchors have changed.
