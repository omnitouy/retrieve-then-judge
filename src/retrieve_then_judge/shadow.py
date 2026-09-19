from __future__ import annotations

import threading
import time
from collections.abc import Callable
from typing import Any


class BoundedShadowRunner:
    def __init__(self, max_inflight: int = 2) -> None:
        if max_inflight < 1:
            raise ValueError("max_inflight must be positive")
        self._slots = threading.BoundedSemaphore(max_inflight)
        self._threads: set[threading.Thread] = set()
        self._lock = threading.Lock()

    def submit(self, function: Callable[..., Any], *args: Any, **kwargs: Any) -> bool:
        if not self._slots.acquire(blocking=False):
            return False

        def _run() -> None:
            try:
                function(*args, **kwargs)
            except Exception:  # noqa: BLE001 - shadow failures must stay contained
                return
            finally:
                self._slots.release()
                with self._lock:
                    self._threads.discard(threading.current_thread())

        thread = threading.Thread(target=_run, daemon=True, name="retrieve-then-judge-shadow")
        with self._lock:
            self._threads.add(thread)
        try:
            thread.start()
        except Exception:
            with self._lock:
                self._threads.discard(thread)
            self._slots.release()
            raise
        return True

    def join(self, timeout: float | None = None) -> None:
        deadline = None if timeout is None else time.monotonic() + timeout
        while True:
            with self._lock:
                threads = tuple(self._threads)
            if not threads:
                return
            for thread in threads:
                remaining = None if deadline is None else max(0.0, deadline - time.monotonic())
                thread.join(remaining)
            if deadline is not None and time.monotonic() >= deadline:
                return
