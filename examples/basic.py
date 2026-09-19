from retrieve_then_judge import Candidate, RetrieveThenJudge, Settings


class ExampleRouter:
    def route(self, query: str):
        return ("example",)


class ExampleBackend:
    def retrieve(self, query: str, source: str, limit: int, timeout: float):
        return (Candidate("example-1", "Synthetic memory only", source, 0.8),)


class ExampleLocalJudge:
    def score(self, query: str, candidates, timeout: float):
        return {candidate.id: 0.9 for candidate in candidates}


service = RetrieveThenJudge(
    ExampleRouter(),
    ExampleBackend(),
    ExampleLocalJudge(),
    Settings(network_enabled=True, allowed_sources=("example",)),
)

print(service.run("Example question").outcome)
