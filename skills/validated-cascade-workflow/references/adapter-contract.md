# Adapter contract

The core workflow knows nothing about document format, source type, model provider, or destination. Supply these adapters.

## Source adapter

- Resolve canonical identity and source version.
- Inventory allowlisted inputs and compute SHA-256 hashes.
- Detect wrong, incomplete, corrupted, inaccessible, or out-of-scope sources.
- Expose evidence locators appropriate to the medium: page, row, time range, line, object path, or revision.

It must not generate the final artifact, call a model, or commit.

## Artifact adapter

- Parse program and repair outputs.
- Enforce the artifact schema and split it into evidence-bearing units.
- Write atomically and compute the final artifact hash.

## Validator adapter

Always check schema, identity, provenance, required files, evidence coverage, unsupported structured values, duplicate policy, and prohibited placeholders. Add domain gates without weakening the common gates.

## Commit and readback adapters

- Batch-read destination identity, source hash, valid committed versions, and protected in-flight commits before repair or model admission.
- Preserve any valid committed or protected in-flight destination state unless an explicit replacement policy is part of the locked configuration.
- Accept only a validated artifact and a stable idempotency key.
- Serialize external writes and repeat the preservation check while holding the destination lock in the same outer transaction as the commit.
- Read back identity, version, status, and hashes from the destination.
- Treat a command exit, upload completion, or local receipt as incomplete until readback matches.
