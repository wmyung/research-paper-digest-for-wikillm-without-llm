# State machine and leases

Recommended states:

```text
DISCOVERED -> PROGRAM_RUNNING -> PROGRAM_VALID -> COMMIT_QUEUED
                           |-> REPAIR_QUEUED -> REPAIR_RUNNING -> VALIDATED
                                                   |-> MODEL_QUEUED -> MODEL_RUNNING -> VALIDATED
VALIDATED -> COMMIT_QUEUED -> COMMITTING -> READBACK_VERIFIED
```

Terminal non-success states are `EXCLUDED_SOURCE_DEFECT`, `HELD_EXTERNAL_DEPENDENCY`, and `FAILED_TERMINAL`.

Use a transactional queue. A claim returns an opaque lease token and expiry. Heartbeats extend only the matching live token. Completion requires current identity, fingerprint, stage, owner, and token. Expired workers cannot publish results. A reclaimer moves expired work back to its queue and records the attempt.

Use separate daily counters for discovered candidates, model attempts, and commits. A retry consumes an attempt counter but not a new-candidate counter. Enforce one active task per model worker and one external commit coordinator. The commit idempotency key should bind stable identity, source hash, artifact hash, and validation contract version.
