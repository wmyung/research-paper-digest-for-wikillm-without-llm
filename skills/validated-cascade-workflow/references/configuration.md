# Configuration

Keep policy outside the workflow engine. A minimal configuration has these fields:

```yaml
workflow:
  strict: true
  max_deterministic_rounds: 3
  model_fallback_enabled: true
  commit_requires_readback: true
identity:
  fields: [identifier, version]
  hash_algorithm: sha256
workers:
  model_concurrency: 4
  lease_ttl_seconds: 1800
  heartbeat_seconds: 600
stages:
  program: {adapter: "package.ProgramAdapter"}
  deterministic_repair: {adapter: "package.RepairAdapter"}
  language_model_fallback:
    adapter: "package.ModelAdapter"
    model: "configured-model"
    max_attempts: 2
    input_policy: "allowlisted-only"
  validation: {adapter: "package.ValidatorAdapter", threshold: 0.95}
  commit: {adapter: "package.CommitAdapter"}
  readback: {adapter: "package.ReadbackAdapter"}
```

Worker count, thresholds, retry limits, formats, providers, models, commands, and destinations are configuration. The model stage may be disabled. Never encode a specific provider or domain into the generic skill.
