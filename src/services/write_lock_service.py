from contextlib import contextmanager
from threading import Lock
from typing import Any, Callable, Dict, Optional


class WriteLockService:
    def __init__(self, conflict_error_factory: Callable[[str, str, Optional[Dict[str, Any]]], Exception]):
        self._conflict_error_factory = conflict_error_factory
        self._locks: Dict[str, Lock] = {}
        self._locks_lock = Lock()

    @contextmanager
    def acquire(
        self,
        key: str,
        *,
        phase: str,
        context: Optional[Dict[str, Any]] = None,
    ):
        normalized_key = str(key or "").strip()
        if not normalized_key:
            yield
            return

        with self._locks_lock:
            lock = self._locks.get(normalized_key)
            if lock is None:
                lock = Lock()
                self._locks[normalized_key] = lock

        if not lock.acquire(blocking=False):
            conflict_error_factory = self._conflict_error_factory
            raise conflict_error_factory(normalized_key, phase, context)

        try:
            yield
        finally:
            lock.release()
