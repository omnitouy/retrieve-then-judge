from __future__ import annotations

import math
import time
from collections.abc import Mapping, Sequence

from .audit import build_event
from .config import Settings
from .protocols import AuditSink, Candidate, Decision, Judge, MemoryBackend, Router


class InvalidJudgeResponse(ValueError):
    pass


class InvalidRouterResponse(ValueError):
    pass


class InvalidCandidateResponse(ValueError):
    pass


def select_candidate(
    scores: Mapping[str, float], *, threshold: float, min_margin: float
) -> str | None:
    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    if not ranked or ranked[0][1] < threshold:
        return None
    runner_up = ranked[1][1] if len(ranked) > 1 else 0.0
    if ranked[0][1] - runner_up < min_margin:
        return None
    return ranked[0][0]


class RetrieveThenJudge:
    """Read-only orchestration. Adapters must honor the timeout they receive."""

    def __init__(
        self,
        router: Router,
        backend: MemoryBackend,
        judge: Judge,
        settings: Settings,
        audit_sink: AuditSink | None = None,
    ) -> None:
        self.router = router
        self.backend = backend
        self.judge = judge
        self.settings = settings
        self.audit_sink = audit_sink

    def _finish(self, decision: Decision, query: str) -> Decision:
        if self.settings.audit_enabled and self.audit_sink is not None:
            try:
                self.audit_sink.emit(build_event(decision, query=query))
            except Exception:  # noqa: BLE001 - metrics must never affect the agent
                return decision
        return decision

    def _remaining(self, deadline: float, cap: float) -> float:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("pipeline deadline exhausted")
        return min(cap, remaining)

    @staticmethod
    def _clean_candidate(candidate: Candidate, source: str, max_chars: int) -> Candidate | None:
        if (
            not isinstance(candidate, Candidate)
            or candidate.source != source
            or not isinstance(candidate.id, str)
            or not candidate.id
            or len(candidate.id) > 128
        ):
            return None
        text = " ".join(str(candidate.text).split())[:max_chars]
        try:
            retrieval_score = float(candidate.retrieval_score)
        except (TypeError, ValueError):
            return None
        if not text or not math.isfinite(retrieval_score):
            return None
        return Candidate(candidate.id, text, source, retrieval_score)

    @staticmethod
    def _validate_scores(
        raw: Mapping[str, float], candidates: Sequence[Candidate]
    ) -> dict[str, float]:
        expected = {candidate.id for candidate in candidates}
        if set(raw) != expected:
            raise InvalidJudgeResponse("judge IDs do not match candidate IDs")
        scores: dict[str, float] = {}
        for candidate_id, value in raw.items():
            try:
                score = float(value)
            except (TypeError, ValueError) as error:
                raise InvalidJudgeResponse("judge score is not numeric") from error
            if not math.isfinite(score) or not 0.0 <= score <= 1.0:
                raise InvalidJudgeResponse("judge score must be finite and between 0 and 1")
            scores[candidate_id] = score
        return scores

    def run(self, query: str) -> Decision:
        settings = self.settings
        if settings.mode == "off" or not settings.network_enabled:
            return self._finish(Decision(outcome="disabled"), str(query))

        cleaned_query = " ".join(str(query).split())[: settings.max_query_chars]
        if not cleaned_query:
            return self._finish(Decision(outcome="abstain"), cleaned_query)
        deadline = time.monotonic() + settings.deadline_seconds

        try:
            routed = tuple(self.router.route(cleaned_query))
        except Exception as error:  # noqa: BLE001 - adapter boundary must fail closed
            return self._finish(
                Decision(outcome="error", error_type=type(error).__name__), cleaned_query
            )

        allowed = set(settings.allowed_sources)
        sources: list[str] = []
        for source in routed:
            if not isinstance(source, str):
                return self._finish(
                    Decision(outcome="error", error_type="InvalidRouterResponse"),
                    cleaned_query,
                )
            if source in allowed and source not in sources:
                sources.append(source)
            if len(sources) >= settings.max_sources:
                break

        retrieval_errors: dict[str, str] = {}
        rows: list[Candidate] = []
        for source in sources:
            try:
                timeout = self._remaining(deadline, settings.retrieval_timeout_seconds)
                received = self.backend.retrieve(
                    cleaned_query, source, settings.max_candidates, timeout
                )
                source_rows: list[Candidate] = []
                for candidate in received:
                    clean = self._clean_candidate(candidate, source, settings.max_candidate_chars)
                    if clean is None:
                        raise InvalidCandidateResponse("backend returned a malformed candidate")
                    source_rows.append(clean)
                rows.extend(source_rows)
            except InvalidCandidateResponse:
                return self._finish(
                    Decision(outcome="error", error_type="InvalidCandidateResponse"),
                    cleaned_query,
                )
            except Exception as error:  # noqa: BLE001 - isolate each backend
                retrieval_errors[source] = type(error).__name__

        rows.sort(key=lambda candidate: candidate.retrieval_score, reverse=True)
        deduped: list[Candidate] = []
        seen_ids: set[str] = set()
        seen_text: set[str] = set()
        for candidate in rows:
            if candidate.id in seen_ids or candidate.text in seen_text:
                continue
            seen_ids.add(candidate.id)
            seen_text.add(candidate.text)
            deduped.append(candidate)
            if len(deduped) >= settings.max_candidates:
                break

        if not deduped:
            return self._finish(
                Decision(
                    outcome="abstain",
                    candidate_count=0,
                    retrieval_errors=retrieval_errors,
                ),
                cleaned_query,
            )

        primary = deduped[: settings.primary_candidates]
        fallback_used = False
        try:
            timeout = self._remaining(deadline, settings.judge_timeout_seconds)
            raw_scores = self.judge.score(cleaned_query, primary, timeout)
            self._remaining(deadline, settings.judge_timeout_seconds)
            scores = self._validate_scores(raw_scores, primary)
            self._remaining(deadline, settings.judge_timeout_seconds)
            selected_id = select_candidate(
                scores,
                threshold=settings.score_threshold,
                min_margin=settings.min_margin,
            )
            self._remaining(deadline, settings.judge_timeout_seconds)
            if selected_id is None and len(deduped) > len(primary):
                fallback_used = True
                timeout = self._remaining(deadline, settings.judge_timeout_seconds)
                raw_scores = self.judge.score(cleaned_query, deduped, timeout)
                self._remaining(deadline, settings.judge_timeout_seconds)
                scores = self._validate_scores(raw_scores, deduped)
                self._remaining(deadline, settings.judge_timeout_seconds)
                selected_id = select_candidate(
                    scores,
                    threshold=settings.score_threshold,
                    min_margin=settings.min_margin,
                )
                self._remaining(deadline, settings.judge_timeout_seconds)
        except Exception as error:  # noqa: BLE001 - failed judge means no injection
            return self._finish(
                Decision(
                    outcome="error",
                    candidate_count=len(deduped),
                    fallback_used=fallback_used,
                    retrieval_errors=retrieval_errors,
                    error_type=type(error).__name__,
                ),
                cleaned_query,
            )

        selected = next(
            (candidate for candidate in deduped if candidate.id == selected_id), None
        )
        return self._finish(
            Decision(
                outcome="selected" if selected else "abstain",
                selected=selected,
                scores=scores,
                candidate_count=len(deduped),
                fallback_used=fallback_used,
                retrieval_errors=retrieval_errors,
            ),
            cleaned_query,
        )
