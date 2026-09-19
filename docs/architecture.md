# Architecture

## Contract

The pipeline is intentionally read-only:

```text
Router → MemoryBackend → Judge → Decision → optional renderer
```

### Router

Returns source identifiers. The core intersects them with `allowed_sources` before any backend call. Unknown, duplicate, excess, or malformed sources are ignored or rejected.

### MemoryBackend

Retrieves bounded candidates from one source. A failure in one source is reduced to its exception type and does not discard candidates already obtained from another source.

### Judge

Returns one finite score in `[0, 1]` for every candidate ID and no unknown IDs. Malformed output fails closed: the decision contains no selected memory.

### Admission policy

The best candidate must meet both:

- `score >= score_threshold`;
- `best_score - runner_up >= min_margin`.

The primary pool is judged first. The pool expands at most once, up to `max_candidates`, after an abstention.

### Hermes adapter

- `off`: no work;
- `shadow`: bounded background observation, no context returned;
- `active`: synchronous decision; injection still requires the separate `injection_enabled` flag.

The package registers no retention tool and no post-turn hook.

## Deadline model

The core computes one monotonic deadline and passes the remaining budget to every adapter call. Adapters are responsible for using cancellation-capable clients and terminating work when their timeout expires. The core does not hide abandoned network threads behind a successful timeout.

## Failure policy

Routing failures, malformed candidates, judge failures, and deadline exhaustion mean no injection. Each backend response is validated atomically: one malformed candidate invalidates that response and stops admission. Retrieval transport failures are isolated per source: one failed source is recorded by exception type, while valid candidates from another allowlisted source may still be judged and selected. The surrounding agent remains available because the Hermes adapter returns an empty context on abstention/error and only admits context after a validated `selected` decision.
