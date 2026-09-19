from __future__ import annotations

import math
import uuid
from datetime import UTC, datetime

from .protocols import Decision


def build_event(decision: Decision, *, query: str) -> dict[str, object]:
    del query  # Raw content is deliberately excluded.
    ranked = sorted(decision.scores.values(), reverse=True)
    top_score = ranked[0] if ranked else None
    margin = ranked[0] - ranked[1] if len(ranked) > 1 else top_score
    error_types = sorted(set(decision.retrieval_errors.values()))
    return {
        "schema": "retrieve-then-judge-event-v1",
        "event_id": uuid.uuid4().hex,
        "recorded_at": datetime.now(UTC).isoformat(),
        "outcome": decision.outcome,
        "candidate_count": decision.candidate_count,
        "selected": decision.selected is not None,
        "top_score": round(top_score, 6) if top_score is not None and math.isfinite(top_score) else None,
        "margin": round(margin, 6) if margin is not None and math.isfinite(margin) else None,
        "fallback_used": decision.fallback_used,
        "retrieval_error_types": error_types,
        "error_type": decision.error_type,
    }
