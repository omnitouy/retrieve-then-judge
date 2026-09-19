from __future__ import annotations

import threading

from retrieve_then_judge.config import Settings
from retrieve_then_judge.hermes import HermesPreCallAdapter
from retrieve_then_judge.protocols import Candidate, Decision
from retrieve_then_judge.shadow import BoundedShadowRunner


class Service:
    def __init__(self, decision):
        self.decision = decision
        self.calls = []

    def run(self, query: str):
        self.calls.append(query)
        return self.decision


def selected_decision():
    return Decision(
        outcome="selected",
        selected=Candidate("c1", "useful memory", "docs", 0.9),
        scores={"c1": 0.9},
        candidate_count=1,
        fallback_used=False,
    )


def test_shadow_hook_never_injects_selected_memory():
    service = Service(selected_decision())
    adapter = HermesPreCallAdapter(service, Settings(mode="shadow", network_enabled=True))
    result = adapter.pre_llm_call(user_message="question", session_id="s", turn_id="t")
    assert "useful memory" not in result.get("context", "")


def test_active_hook_injects_only_when_explicitly_enabled():
    service = Service(selected_decision())
    off = HermesPreCallAdapter(service, Settings(mode="active", network_enabled=True))
    assert "context" not in off.pre_llm_call(user_message="question")

    on = HermesPreCallAdapter(
        service,
        Settings(mode="active", network_enabled=True, injection_enabled=True),
    )
    result = on.pre_llm_call(user_message="question")
    assert "useful memory" in result["context"]


def test_shadow_runner_bounds_inflight_work_and_recovers_slots():
    gate = threading.Event()
    started = []

    def work(value):
        started.append(value)
        gate.wait(1)

    runner = BoundedShadowRunner(max_inflight=2)
    assert runner.submit(work, 1) is True
    assert runner.submit(work, 2) is True
    assert runner.submit(work, 3) is False
    gate.set()
    runner.join(timeout=2)
    assert runner.submit(lambda: None) is True
    runner.join(timeout=2)
    assert sorted(started) == [1, 2]


def test_shadow_worker_exception_is_contained(monkeypatch):
    leaked = []
    monkeypatch.setattr(
        threading,
        "excepthook",
        lambda args: leaked.append(str(args.exc_value)),
    )

    def fail():
        raise RuntimeError("private adapter detail")

    runner = BoundedShadowRunner(max_inflight=1)
    assert runner.submit(fail) is True
    runner.join(timeout=2)
    assert leaked == []
    assert runner.submit(lambda: None) is True
    runner.join(timeout=2)
