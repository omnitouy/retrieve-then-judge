from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True, slots=True)
class Candidate:
    id: str
    text: str
    source: str
    retrieval_score: float = 0.0


@dataclass(slots=True)
class Decision:
    outcome: str
    selected: Candidate | None = None
    scores: dict[str, float] = field(default_factory=dict)
    candidate_count: int = 0
    fallback_used: bool = False
    retrieval_errors: dict[str, str] = field(default_factory=dict)
    error_type: str | None = None


class Router(Protocol):
    def route(self, query: str) -> Sequence[str]: ...


class MemoryBackend(Protocol):
    def retrieve(
        self, query: str, source: str, limit: int, timeout: float
    ) -> Sequence[Candidate]: ...


class Judge(Protocol):
    def score(
        self, query: str, candidates: Sequence[Candidate], timeout: float
    ) -> Mapping[str, float]: ...


class AuditSink(Protocol):
    def emit(self, event: Mapping[str, object]) -> None: ...
