# retrieve-then-judge

[![CI](https://github.com/omnitouy/retrieve-then-judge/actions/workflows/ci.yml/badge.svg)](https://github.com/omnitouy/retrieve-then-judge/actions/workflows/ci.yml)

A small, read-only context gate for AI-agent memory:

```text
current message
    ↓
route to allowlisted sources
    ↓
retrieve bounded candidates
    ↓
judge direct usefulness
    ↓
threshold + margin
    ├── clear winner → admit one bounded memory
    └── uncertain    → abstain
```

The project separates four jobs that are often collapsed into one model call:

- the **router** chooses allowed memory sources;
- the **backend** retrieves candidates;
- the **judge** scores direct usefulness for the current turn;
- the **agent** reasons and acts.

It does not write memories, classify post-turn learning, or execute tools.

> **Status: experimental.** The architecture and failure paths are tested with synthetic data. A real deployment is still running in shadow mode; this repository does not claim production validation or improved real-world recall.

## Why add a judge after retrieval?

A memory backend answers “what looks related to this query?” A context gate answers a different question: “which returned item is useful enough to spend the agent’s attention on right now?”

`retrieve-then-judge` adds an admission policy around retrieval:

- one candidate at most;
- minimum score and winner margin;
- one bounded fallback expansion;
- explicit abstention;
- source allowlists;
- fail-closed validation and fail-open agent behavior;
- shadow execution with bounded concurrency;
- optional content-free metrics.

## Safe defaults

```python
from retrieve_then_judge import Settings

settings = Settings()
assert settings.network_enabled is False
assert settings.injection_enabled is False
assert settings.mode == "shadow"
```

No outbound work occurs until `network_enabled=True`. No memory is injected until both `mode="active"` and `injection_enabled=True` are set explicitly.

## Minimal usage

Implement three small interfaces:

```python
from retrieve_then_judge import Candidate, RetrieveThenJudge, Settings

class Router:
    def route(self, query):
        return ["docs"]

class Backend:
    def retrieve(self, query, source, limit, timeout):
        return [Candidate("m1", "A synthetic memory", source, 0.82)]

class Judge:
    def score(self, query, candidates, timeout):
        return {candidate.id: 0.91 for candidate in candidates}

service = RetrieveThenJudge(
    Router(),
    Backend(),
    Judge(),
    Settings(network_enabled=True, allowed_sources=("docs",)),
)

decision = service.run("What did we decide?")
print(decision.outcome)  # selected or abstain
```

Adapters own their network clients and **must cancel or terminate work when the supplied timeout expires**. The core passes a shared remaining deadline but cannot forcibly cancel arbitrary synchronous adapter code.

## Hermes integration

The package contains a thin `pre_llm_call` adapter:

```python
from retrieve_then_judge.config import Settings
from retrieve_then_judge.hermes import HermesPreCallAdapter, register_hooks

settings = Settings(
    mode="shadow",
    network_enabled=True,
    injection_enabled=False,
    allowed_sources=("docs",),
)
adapter = HermesPreCallAdapter(service, settings)

# Inside your Hermes plugin register(ctx):
register_hooks(ctx, adapter)
```

Shadow mode runs observations through a bounded worker pool and never returns memory context. When every shadow slot is occupied, new observations are deliberately dropped rather than queued; applications that need coverage metrics can count failed `submit()` calls without recording content. Active mode admits one candidate only after both score and margin checks.

## Privacy boundary

A configured judge normally receives:

- the current user message, bounded by `max_query_chars`;
- candidate IDs;
- bounded candidate text.

This reference implementation never sends recent conversation history automatically. It ships no vendor adapter and performs no network access by itself. See [docs/privacy.md](docs/privacy.md) before connecting a hosted judge.

## Prompt-injection boundary

Retrieved memories are untrusted data. The renderer:

- serializes content as JSON;
- escapes `<`, `>`, and `&` so candidate text cannot close its data wrapper;
- labels the payload as data, never instructions;
- bounds admitted text.

This reduces delimiter escape. It does **not** make semantic prompt injection impossible; the downstream model must still treat retrieved text as untrusted. See [docs/threat-model.md](docs/threat-model.md).

## Synthetic evidence

The design originated from an isolated experiment with 40 synthetic memories and 8 queries:

- retrieval surfaced the target in 7/8 cases;
- the judge chose correctly in 7/7 cases where the target was present;
- no incorrect candidate was finally admitted;
- one missing target became an abstention.

These figures motivated the architecture; they are not production claims.

## Development

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e '.[dev]'
pytest
ruff check .
```

The test suite covers disabled-by-default networking, score and margin gates, fallback expansion, source isolation, malformed responses, structured rendering, content-free audit events, and bounded shadow concurrency.

## Repository map

```text
src/retrieve_then_judge/
  config.py       validated, conservative settings
  protocols.py    replaceable interfaces and data types
  core.py         read-only orchestration and admission policy
  render.py       bounded structured context rendering
  audit.py        optional content-free event builder
  shadow.py       bounded asynchronous observation
  hermes.py       thin Hermes pre-call adapter

docs/
  architecture.md
  privacy.md
  threat-model.md
```

## License

MIT. See [LICENSE](LICENSE).
