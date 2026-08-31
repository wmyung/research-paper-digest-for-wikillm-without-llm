# State machine and leases

Recommended states:

```text
DISCOVERED -> PROGRAM_RUNNING -> PROGRAM_VALID -> COMMIT_QUEUED
                           |-> REPAIR_QUEUED -> REPAIR_RUNNING -> VALIDATED
                                                   |-> MODEL_QUEUED -> MODEL_RUNNING -> VALIDATED
VALIDATED -> COMMIT_QUEUED -> COMMITTING -> READBACK_VERIFIED
```

Destination preflight may move an item directly to `EXISTING_DESTINATION_PRESERVED` before repair or model work. Repeat the same check after the commit coordinator acquires its lock. Terminal non-success states are `EXISTING_DESTINATION_PRESERVED`, `EXCLUDED_SOURCE_DEFECT`, `HELD_EXTERNAL_DEPENDENCY`, and `FAILED_TERMINAL`.

Use a transactional queue. A claim returns an opaque lease token and expiry. Heartbeats extend only the matching live token. Completion requires current identity, fingerprint, stage, owner, token, and readable generation/validation evidence. Expired workers cannot publish results. A reclaimer moves expired work back to its queue and records the claim without consuming a generation attempt.

Use separate daily counters for discovered candidates, claims, evidence-backed generation attempts, validation attempts, registration attempts, and verified commits. A retryable release without completed artifacts consumes no generation attempt. Enforce one active task per model worker and one external commit coordinator. The commit idempotency key should bind stable identity, source hash, artifact hash, and validation contract version. The destination row/version lock, preservation checks, artifact creation, and commit must share one outer transaction; a client-side preflight alone cannot close an in-flight race. If the ingest that opened this transaction created an untouched placeholder, discard only that exact returned ID inside the transaction before promotion; never infer replaceability from a generic queued status.
