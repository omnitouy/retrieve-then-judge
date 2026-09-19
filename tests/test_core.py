from __future__ import annotations

import math

from retrieve_then_judge.config import Settings
from retrieve_then_judge.core import RetrieveThenJudge, select_candidate
from retrieve_then_judge.protocols import Candidate


class Router:
    def __init__(self, sources=("docs",)):
        self.sources = sources
        self.calls = 0

    def route(self, query: str):
        self.calls += 1
        return self.sources


class Backend:
    def __init__(self, rows=None, failures=None):
        self.rows = rows or {}
        self.failures = failures or {}
        self.calls = []

    def retrieve(self, query: str, source: str, limit: int, timeout: float):
        self.calls.append((query, source, limit, timeout))
        if source in self.failures:
            raise self.failures[source]
        return self.rows.get(source, [])


class Judge:
    def __init__(self, scores_by_size):
        self.scores_by_size = scores_by_size
        self.calls = []

    def score(self, query: str, candidates, timeout: float):
        self.calls.append((query, tuple(c.id for c in candidates), timeout))
        value = self.scores_by_size[len(candidates)]
        if isinstance(value, Exception):
            raise value
        return value


def candidate(identifier: str, text: str, source: str = "docs", score: float = 0.5):
    return Candidate(id=identifier, text=text, source=source, retrieval_score=score)


def test_selection_requires_threshold_and_margin():
    assert select_candidate({"a": 0.84, "b": 0.40}, threshold=0.65, min_margin=0.12) == "a"
    assert select_candidate({"a": 0.60, "b": 0.10}, threshold=0.65, min_margin=0.12) is None
    assert select_candidate({"a": 0.84, "b": 0.75}, threshold=0.65, min_margin=0.12) is None


def test_default_configuration_makes_zero_network_calls():
    router, backend, judge = Router(), Backend(), Judge({})
    result = RetrieveThenJudge(router, backend, judge, Settings()).run("hello")
    assert result.outcome == "disabled"
    assert router.calls == 0
    assert backend.calls == []
    assert judge.calls == []


def test_primary_abstention_expands_once_to_fallback_pool():
    rows = [candidate(f"c{i}", f"memory {i}", score=1 - i / 100) for i in range(1, 8)]
    service = RetrieveThenJudge(
        Router(),
        Backend({"docs": rows}),
        Judge({5: {f"c{i}": 0.2 for i in range(1, 6)}, 7: {**{f"c{i}": 0.1 for i in range(1, 7)}, "c7": 0.9}}),
        Settings(network_enabled=True, allowed_sources=("docs",)),
    )
    result = service.run("question")
    assert result.outcome == "selected"
    assert result.selected.id == "c7"
    assert result.fallback_used is True


def test_one_failed_source_does_not_discard_a_successful_source():
    service = RetrieveThenJudge(
        Router(("docs", "archive")),
        Backend({"docs": [candidate("good", "useful")]}, {"archive": TimeoutError("late")}),
        Judge({1: {"good": 0.9}}),
        Settings(network_enabled=True, allowed_sources=("docs", "archive")),
    )
    result = service.run("question")
    assert result.selected.id == "good"
    assert result.retrieval_errors == {"archive": "TimeoutError"}


def test_unlisted_source_is_never_called():
    backend = Backend({"private": [candidate("x", "secret", source="private")]})
    service = RetrieveThenJudge(
        Router(("private",)), backend, Judge({}),
        Settings(network_enabled=True, allowed_sources=("docs",)),
    )
    result = service.run("question")
    assert result.outcome == "abstain"
    assert backend.calls == []


def test_malformed_router_output_fails_closed_without_backend_call():
    backend = Backend()
    service = RetrieveThenJudge(
        Router((["not-hashable"],)), backend, Judge({}),
        Settings(network_enabled=True, allowed_sources=("docs",)),
    )
    result = service.run("question")
    assert result.outcome == "error"
    assert result.selected is None
    assert result.error_type == "InvalidRouterResponse"
    assert backend.calls == []


def test_malformed_or_non_finite_judge_output_fails_closed():
    rows = [candidate("a", "one"), candidate("b", "two")]
    judge = Judge({2: {"a": math.nan, "b": 2.0}})
    service = RetrieveThenJudge(
        Router(), Backend({"docs": rows}), judge,
        Settings(network_enabled=True, allowed_sources=("docs",), primary_candidates=2),
    )
    result = service.run("question")
    assert result.outcome == "error"
    assert result.selected is None
    assert result.error_type == "InvalidJudgeResponse"


def test_candidate_text_is_bounded_before_judging():
    long_text = "x" * 5000
    rows = [candidate("a", long_text)]
    judge = Judge({1: {"a": 0.9}})
    service = RetrieveThenJudge(
        Router(), Backend({"docs": rows}), judge,
        Settings(network_enabled=True, allowed_sources=("docs",), max_candidate_chars=128),
    )
    result = service.run("question")
    assert result.selected is not None
    assert len(result.selected.text) == 128


def test_late_judge_response_cannot_be_selected_after_deadline():
    import time

    class LateJudge:
        def score(self, query, candidates, timeout):
            time.sleep(0.15)
            return {candidate.id: 0.9 for candidate in candidates}

    service = RetrieveThenJudge(
        Router(), Backend({"docs": [candidate("a", "memory")]}), LateJudge(),
        Settings(
            network_enabled=True,
            allowed_sources=("docs",),
            deadline_seconds=0.1,
        ),
    )
    result = service.run("question")
    assert result.outcome == "error"
    assert result.selected is None
    assert result.error_type == "TimeoutError"


def test_non_string_candidate_id_is_rejected_without_crashing():
    malformed = Candidate(id=["not", "a", "string"], text="memory", source="docs")  # type: ignore[arg-type]
    service = RetrieveThenJudge(
        Router(), Backend({"docs": [malformed]}), Judge({}),
        Settings(network_enabled=True, allowed_sources=("docs",)),
    )
    result = service.run("question")
    assert result.outcome == "error"
    assert result.selected is None
    assert result.error_type == "InvalidCandidateResponse"


def test_deadline_expiry_during_lazy_score_validation_prevents_selection():
    import time
    from collections.abc import Mapping

    class LazyScores(Mapping):
        def __getitem__(self, key):
            return 0.9

        def __iter__(self):
            time.sleep(0.15)
            yield "a"

        def __len__(self):
            return 1

    class LazyJudge:
        def score(self, query, candidates, timeout):
            return LazyScores()

    service = RetrieveThenJudge(
        Router(), Backend({"docs": [candidate("a", "memory")]}), LazyJudge(),
        Settings(network_enabled=True, allowed_sources=("docs",), deadline_seconds=0.1),
    )
    result = service.run("question")
    assert result.outcome == "error"
    assert result.selected is None
    assert result.error_type == "TimeoutError"


def test_malformed_candidate_invalidates_the_entire_retrieval_response():
    malformed = Candidate(id=["not", "a", "string"], text="bad", source="docs")  # type: ignore[arg-type]
    judge = Judge({1: {"good": 0.9}})
    service = RetrieveThenJudge(
        Router(),
        Backend({"docs": [candidate("good", "useful"), malformed]}),
        judge,
        Settings(network_enabled=True, allowed_sources=("docs",)),
    )
    result = service.run("question")
    assert result.outcome == "error"
    assert result.selected is None
    assert result.error_type == "InvalidCandidateResponse"
    assert judge.calls == []
