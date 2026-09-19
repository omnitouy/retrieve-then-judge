# Threat model

## Protected assets

- current user messages;
- retrieved memories;
- agent instructions and tool authority;
- credentials and local paths;
- service availability.

## Main threats and controls

### Unwanted data egress

**Control:** no bundled network client, networking disabled by default, replaceable local judge, bounded current-message and candidate fields, no automatic recent-history or post-turn transmission.

### Noisy or wrong memory

**Control:** allowlisted sources, score threshold, winner margin, one admitted candidate, bounded fallback, explicit abstention, fail-closed schema validation.

### Prompt injection stored inside memory

**Control:** JSON serialization, delimiter escaping, untrusted-data labeling, context-length bounds. This mitigates structural escape but cannot guarantee that a downstream language model will ignore persuasive malicious content.

### Partial backend failure

**Control:** exceptions are isolated per source and reduced to exception type names. Valid candidates from other sources remain available.

### Resource exhaustion

**Control:** bounded candidate/source counts, one monotonic deadline, and a bounded shadow runner. Network adapters must provide real cancellation; spawning abandoned timeout threads is not accepted as cancellation.

### Sensitive audit trails

**Control:** audit is opt-in and content-free. Events use random IDs rather than stable message/session hashes and omit backend/source identifiers.

## Out of scope

- integrity of a third-party memory store;
- semantic safety of a downstream model;
- authentication for a concrete provider adapter;
- durable memory writes, deletion, or consolidation;
- production-grade distributed scheduling.

## Security invariants

- the core has no write method;
- the Hermes adapter registers only a pre-call hook;
- disabled configuration performs zero outbound calls;
- malformed routing, retrieval, or judge output cannot produce selected context;
- active injection requires two explicit settings.
