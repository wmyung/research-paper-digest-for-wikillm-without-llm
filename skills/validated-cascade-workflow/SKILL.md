---
name: validated-cascade-workflow
description: Use when a reproducible artifact workflow should preserve valid program output, apply deterministic repair to failures, use a language model only for residual eligible cases, validate every artifact fail-closed, and commit only after verified readback. Suitable for documents, data, code, or other evidence-bound artifacts; model, format, validator, worker count, and destination are adapters rather than fixed assumptions.
---

# Validated Cascade Workflow

Build a cost-aware recovery cascade around an existing program. The invariant is `program -> deterministic repair -> optional language model -> validation -> commit -> readback`, with identity, hashes, evidence, and terminal state recorded at every boundary.

## Start

1. Read [references/adapter-contract.md](references/adapter-contract.md) and define source, artifact, validator, commit, and readback adapters.
2. Read [references/configuration.md](references/configuration.md) and lock the quality gates, retry limits, concurrency, and allowed model inputs.
3. Create a private run directory. Keep source data, generated artifacts, receipts, and machine-specific state out of a public skill or repository.
4. Bind each work item to a stable identity plus input hashes. Retries must reuse that fingerprint.

## Run the cascade

1. Run the existing program once. Preserve a validated result unchanged.
2. Batch-read the destination before spending model effort. If the same identity/version already has a valid committed artifact or a protected in-flight commit, record `EXISTING_DESTINATION_PRESERVED`; do not regenerate, replace, or supersede it. Fail closed on identity matches with conflicting source hashes.
3. Classify a failure before spending model effort. Exclude or hold wrong, incomplete, corrupted, inaccessible, or out-of-scope sources.
4. Apply deterministic repairs first: schema normalization, field completion from trusted inputs, evidence-linked reassignment, deduplication, index regeneration, and validator-directed structural repair.
5. Revalidate after each accepted repair. Stop a repair loop that does not reduce hard failures or improve the configured monotone objective.
6. Permit language-model fallback only for eligible residual failures. Give it allowlisted inputs, exact failed gates, an output schema, and a bounded objective. A configured model is optional; never assume a provider or model name.
7. Settle model work only from readable source-gate, generation, and validator artifacts. A claim or retryable release is not a generation attempt, and no worker may declare validation, fallback admission, or terminal failure from prose alone.
8. Parse model output as an untrusted proposal. Rebuild evidence and provenance deterministically, then run the same validator used for program output. Retry the cheaper model stage once when evidence shows a repairable validation failure; admit an expensive source fallback only when a structured gap assessment proves that the allowlisted input cannot supply the missing evidence.
9. Commit only a validated artifact. Serialize external commits, use an idempotency key derived from identity and artifact hashes, repeat the destination-preservation gate inside the commit transaction, and verify the stored result by readback. A placeholder created by the same ingest operation may be replaced only by exact ID, while untouched and inside that same transaction; all pre-existing or progressed destination work remains protected.

## Parallel operation

Use atomic claims with expiring leases. Cap workers from configuration, heartbeat before one-third of the lease TTL, reject stale-token commits, and let only one coordinator perform external writes. A worker owns one model task at a time. Read [references/state-machine.md](references/state-machine.md) before implementing a queue.

## Fail closed

Score alone never authorizes commit. Block on identity or hash mismatch, unsupported values, invalid evidence, prohibited inputs, placeholder content, missing provenance, validator errors, duplicate-policy violations, or readback mismatch. Record source defects, external holds, retry exhaustion, and validation failure as distinct terminal outcomes.

## Finish

Report program passes, deterministic recoveries, model claims, evidence-backed generation attempts, model recoveries, expensive-fallback admissions, existing-destination preservations, exclusions, holds, validated artifacts, verified commits, retries, duplicate suppressions, elapsed time, and per-stage cost. Distinguish local validation from verified destination state.
