#!/usr/bin/env python3
from threading import Lock, RLock
from typing import Any, Dict, Iterable, Optional, Tuple

from services.runtime_operation_service import RuntimeOperationService
from services.status_payload_builder import StatusPayloadBuilder


class RuntimeStateService:
    def __init__(
        self,
        *,
        runtime_operations: RuntimeOperationService,
        status_builder: StatusPayloadBuilder,
        persistence: Optional[Any] = None,
    ):
        self.runtime_operations = runtime_operations
        self.status_builder = status_builder
        self.persistence = persistence
        self._memory: Dict[str, Dict[str, Dict[str, Any]]] = {}
        self._values: Dict[str, Dict[str, Any]] = {}
        self._singletons: Dict[str, Dict[str, Any]] = {}
        self._locks: Dict[str, RLock] = {}
        self._registry_lock = Lock()

    @staticmethod
    def normalize_state_type(state_type: Any) -> str:
        return str(state_type or "").strip().lower()

    def memory(self, state_type: Any) -> Dict[str, Dict[str, Any]]:
        normalized_type = self.normalize_state_type(state_type)
        with self._registry_lock:
            return self._memory.setdefault(normalized_type, {})

    def lock(self, state_type: Any) -> RLock:
        normalized_type = self.normalize_state_type(state_type)
        with self._registry_lock:
            return self._locks.setdefault(normalized_type, RLock())

    def values(self, state_type: Any) -> Dict[str, Any]:
        normalized_type = self.normalize_state_type(state_type)
        with self._registry_lock:
            return self._values.setdefault(normalized_type, {})

    def replace_values(self, state_type: Any, payload: Dict[str, Any]) -> Dict[str, Any]:
        with self.lock(state_type):
            current = self.values(state_type)
            current.clear()
            current.update(dict(payload) if isinstance(payload, dict) else {})
            return current

    def singleton(self, state_type: Any) -> Dict[str, Any]:
        normalized_type = self.normalize_state_type(state_type)
        with self._registry_lock:
            return self._singletons.setdefault(normalized_type, {})

    def replace_singleton(self, state_type: Any, payload: Dict[str, Any]) -> Dict[str, Any]:
        with self.lock(state_type):
            current = self.singleton(state_type)
            current.clear()
            current.update(dict(payload) if isinstance(payload, dict) else {})
            return current

    def get_value(self, state_type: Any, key: Any, default: Any = None) -> Any:
        normalized_key = str(key or "").strip()
        with self.lock(state_type):
            return self.values(state_type).get(normalized_key, default)

    def set_value(self, state_type: Any, key: Any, value: Any) -> Any:
        normalized_key = str(key or "").strip()
        with self.lock(state_type):
            self.values(state_type)[normalized_key] = value
        return value

    def pop_value(self, state_type: Any, key: Any, default: Any = None) -> Any:
        normalized_key = str(key or "").strip()
        with self.lock(state_type):
            return self.values(state_type).pop(normalized_key, default)

    def read_memory(self, state_type: Any, state_key: Any) -> Dict[str, Any]:
        normalized_key = str(state_key or "").strip()
        with self.lock(state_type):
            current = self.memory(state_type).get(normalized_key, {})
            return dict(current) if isinstance(current, dict) else {}

    def write_memory(self, state_type: Any, state_key: Any, payload: Dict[str, Any]) -> Dict[str, Any]:
        normalized_key = str(state_key or "").strip()
        current = dict(payload) if isinstance(payload, dict) else {}
        with self.lock(state_type):
            self.memory(state_type)[normalized_key] = current
        return dict(current)

    def read_persisted(self, state_type: Any, state_key: Any) -> Dict[str, Any]:
        if self.persistence is None:
            return {}
        current = self.persistence.readRuntimeState(str(state_type or ""), str(state_key or ""))
        return dict(current) if isinstance(current, dict) else {}

    def persist(self, state_type: Any, state_key: Any, payload: Dict[str, Any]) -> bool:
        if self.persistence is None:
            return False
        return bool(self.persistence.writeRuntimeState(str(state_type or ""), str(state_key or ""), dict(payload)))

    def read(self, state_type: Any, state_key: Any, *, persisted_first: bool = True) -> Dict[str, Any]:
        if persisted_first:
            current = self.read_persisted(state_type, state_key)
            return current or self.read_memory(state_type, state_key)
        current = self.read_memory(state_type, state_key)
        return current or self.read_persisted(state_type, state_key)

    def write(
        self,
        state_type: Any,
        state_key: Any,
        payload: Dict[str, Any],
        *,
        persist: bool = True,
    ) -> Dict[str, Any]:
        current = self.write_memory(state_type, state_key, payload)
        if persist:
            self.persist(state_type, state_key, current)
        return current

    def first_blocking_progress(
        self,
        candidates: Iterable[Tuple[str, Any]],
        *,
        exclude_operation: Any = "",
    ) -> Optional[Dict[str, Any]]:
        excluded = str(exclude_operation or "").strip().lower()
        for operation, progress in candidates:
            normalized_operation = str(operation or "").strip().lower()
            if not normalized_operation or normalized_operation == excluded:
                continue
            if not self.runtime_operations.is_blocking_running_progress(progress):
                continue
            payload = dict(progress) if isinstance(progress, dict) else {}
            payload.setdefault("operation", normalized_operation)
            return payload
        return None

    def normalize_progress(
        self,
        current: Dict[str, Any],
        *,
        operation: str,
        action: Any = "",
        mode: Any = "",
    ) -> Dict[str, Any]:
        payload = dict(current) if isinstance(current, dict) else {}
        normalized_operation = str(operation or "").strip().lower()
        normalized_action = str(action or payload.get("action") or "").strip().lower()
        normalized_mode = str(mode or payload.get("mode") or payload.get("source_mode") or "scan").strip().lower() or "scan"
        existing_status = payload.get("status")
        existing_status_text = existing_status if isinstance(existing_status, str) else ""
        payload["operation"] = normalized_operation
        payload["action"] = normalized_action
        payload["mode"] = normalized_mode
        derived_phase = self.status_builder.derive_phase(
            running=payload.get("running"),
            finished=payload.get("finished"),
            stop_requested=payload.get("stop_requested"),
            message_key=str(payload.get("message_key") or payload.get("message") or ""),
            status=existing_status_text,
        )
        previous_phase = str(payload.get("phase") or "").strip().lower()
        payload["phase"] = previous_phase if derived_phase == "idle" and previous_phase else derived_phase
        return payload

    def stamp_progress(
        self,
        current: Dict[str, Any],
        *,
        operation: str,
        action: Any = "",
        mode: Any = "",
        operation_discriminator: Any = "",
    ) -> Dict[str, Any]:
        payload = self.normalize_progress(
            current,
            operation=operation,
            action=action,
            mode=mode,
        )
        return self.runtime_operations.stamp_progress(
            payload,
            operation_prefix=operation,
            operation_discriminator=operation_discriminator,
        )
