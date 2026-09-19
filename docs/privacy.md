# Privacy

## Default behavior

The package has no built-in network client. `network_enabled` defaults to `false`, and the core returns `disabled` before calling the router, backend, or judge.

## Data a hosted judge may receive

When an application supplies a remote judge adapter and explicitly enables networking, the adapter may receive:

- the current message, truncated to `max_query_chars`;
- candidate IDs;
- candidate text, normalized and truncated to `max_candidate_chars`.

The package does not automatically send conversation history, assistant responses, stored credentials, session transcripts, or post-turn learning.

## Metrics

`build_event()` emits:

- a random event ID;
- timestamp;
- outcome and counts;
- score and margin;
- fallback state;
- exception type names.

It excludes raw query text, raw memory text, source identifiers, local paths, credentials, and deterministic content hashes. Applications must opt in to storage by implementing an `AuditSink` and must define their own retention and deletion policy.

## Credentials

Credentials belong in the application’s secret store and should be injected into a concrete adapter. This package does not scan broad dotenv files and does not define a provider-specific environment variable.

## Operator responsibilities

Before enabling a hosted judge:

1. document the provider and endpoint;
2. obtain appropriate consent for external processing;
3. confirm retention and training policies;
4. use HTTPS and protect against configurable-endpoint SSRF;
5. prefer a local judge for sensitive memory.
