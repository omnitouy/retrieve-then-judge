from __future__ import annotations

from typing import Any

from .config import Settings
from .core import RetrieveThenJudge
from .render import render_memory_data
from .shadow import BoundedShadowRunner


def _message_text(value: Any) -> str:
    if isinstance(value, str):
        return " ".join(value.split())
    if isinstance(value, list):
        parts = []
        for item in value:
            if isinstance(item, dict) and item.get("type") in {"text", "input_text"}:
                parts.append(str(item.get("text") or ""))
        return " ".join(" ".join(parts).split())
    return ""


class HermesPreCallAdapter:
    """Thin pre-call adapter. It never registers retention or post-turn hooks."""

    def __init__(
        self,
        service: RetrieveThenJudge,
        settings: Settings,
        shadow_runner: BoundedShadowRunner | None = None,
    ) -> None:
        self.service = service
        self.settings = settings
        self.shadow_runner = shadow_runner or BoundedShadowRunner(
            settings.shadow_max_inflight
        )

    def pre_llm_call(self, **runtime: Any) -> dict[str, str]:
        message = _message_text(runtime.get("user_message"))
        if not message or self.settings.mode == "off":
            return {}
        if self.settings.mode == "shadow":
            self.shadow_runner.submit(self.service.run, message)
            return {}
        if not self.settings.injection_enabled:
            return {}
        decision = self.service.run(message)
        if decision.outcome != "selected" or decision.selected is None:
            return {}
        return {
            "context": render_memory_data(
                decision.selected,
                max_chars=self.settings.max_context_chars,
            )
        }


def register_hooks(ctx: Any, adapter: HermesPreCallAdapter) -> None:
    ctx.register_hook("pre_llm_call", adapter.pre_llm_call)
