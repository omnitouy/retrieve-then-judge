from __future__ import annotations

import re
from dataclasses import dataclass

_SOURCE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


@dataclass(frozen=True, slots=True)
class Settings:
    mode: str = "shadow"
    network_enabled: bool = False
    injection_enabled: bool = False
    audit_enabled: bool = False
    allowed_sources: tuple[str, ...] = ()
    primary_candidates: int = 5
    max_candidates: int = 10
    max_sources: int = 2
    score_threshold: float = 0.65
    min_margin: float = 0.12
    deadline_seconds: float = 25.0
    retrieval_timeout_seconds: float = 12.0
    judge_timeout_seconds: float = 8.0
    max_query_chars: int = 4_000
    max_candidate_chars: int = 1_600
    max_context_chars: int = 1_200
    shadow_max_inflight: int = 2

    def __post_init__(self) -> None:
        if self.mode not in {"off", "shadow", "active"}:
            raise ValueError("mode must be off, shadow, or active")
        if not 1 <= self.primary_candidates <= self.max_candidates <= 20:
            raise ValueError("candidate limits must satisfy 1 <= primary <= max <= 20")
        if not 1 <= self.max_sources <= 8:
            raise ValueError("max_sources must be between 1 and 8")
        if not 0.0 <= self.score_threshold <= 1.0:
            raise ValueError("score_threshold must be between 0 and 1")
        if not 0.0 <= self.min_margin <= 1.0:
            raise ValueError("min_margin must be between 0 and 1")
        if not 0.1 <= self.deadline_seconds <= 25.0:
            raise ValueError("deadline_seconds must be between 0.1 and 25")
        if self.retrieval_timeout_seconds <= 0 or self.judge_timeout_seconds <= 0:
            raise ValueError("network timeouts must be positive")
        if self.max_query_chars < 1 or self.max_candidate_chars < 1 or self.max_context_chars < 1:
            raise ValueError("text limits must be positive")
        if not 1 <= self.shadow_max_inflight <= 32:
            raise ValueError("shadow_max_inflight must be between 1 and 32")
        if len(set(self.allowed_sources)) != len(self.allowed_sources):
            raise ValueError("allowed_sources must not contain duplicates")
        if any(not _SOURCE_RE.fullmatch(source) for source in self.allowed_sources):
            raise ValueError("allowed_sources contains an unsafe identifier")
