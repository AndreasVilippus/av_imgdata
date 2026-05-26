#!/usr/bin/env python3
from typing import Any, Dict, List, Optional


class StatusPayloadBuilder:
    CHECK_TYPES = {"dimension_issues", "duplicate_faces", "position_deviations", "name_conflicts"}

    @classmethod
    def normalize_checks_type(cls, check_type: Any) -> str:
        normalized = str(check_type or "").strip().lower()
        return normalized if normalized in cls.CHECK_TYPES else "dimension_issues"

    @staticmethod
    def derive_phase(
        *,
        running: Any = False,
        finished: Any = False,
        stop_requested: Any = False,
        message_key: str = "",
        status: str = "",
    ) -> str:
        normalized_status = str(status or "").strip().lower()
        normalized_message = str(message_key or "").strip().lower()
        if normalized_status in {"failed", "error"} or "failed" in normalized_message or "error" in normalized_message:
            return "failed"
        if normalized_status in {"blocked"} or "blocked" in normalized_message:
            return "blocked"
        if bool(stop_requested) or normalized_status in {"stopping"} or "stopping" in normalized_message:
            return "stopping" if bool(running) else "stopped"
        if "empty" in normalized_message or normalized_status in {"empty"}:
            return "empty"
        if bool(finished) or normalized_status in {"finished", "done", "saved"}:
            return "finished"
        if "preparing" in normalized_message or "listing" in normalized_message:
            return "preparing"
        if bool(running):
            return "running"
        return "idle"

    @staticmethod
    def to_int(value: Any) -> int:
        try:
            return max(0, int(value))
        except Exception:
            return 0

    def counter(
        self,
        key: str,
        *,
        value: Any,
        label_key: str = "",
        fallback_label: str = "",
        show_when_zero: bool = False,
    ) -> Dict[str, Any]:
        return {
            "key": str(key or "").strip(),
            "value": self.to_int(value),
            "label_key": str(label_key or "").strip(),
            "fallback_label": str(fallback_label or "").strip(),
            "show_when_zero": bool(show_when_zero),
        }

    def progress(
        self,
        *,
        kind: str,
        current: Any = 0,
        total: Any = 0,
        title_key: str = "",
        fallback_title: str = "",
        primary_label_key: str = "",
        fallback_primary_label: str = "",
        secondary_label_key: str = "",
        fallback_secondary_label: str = "",
    ) -> Dict[str, Any]:
        return {
            "kind": str(kind or "").strip(),
            "current": self.to_int(current),
            "total": self.to_int(total),
            "title_key": str(title_key or "").strip(),
            "fallback_title": str(fallback_title or "").strip(),
            "primary_label_key": str(primary_label_key or "").strip(),
            "fallback_primary_label": str(fallback_primary_label or "").strip(),
            "secondary_label_key": str(secondary_label_key or "").strip(),
            "fallback_secondary_label": str(fallback_secondary_label or "").strip(),
        }

    def payload(
        self,
        *,
        operation: str,
        action: str,
        mode: str,
        phase: str,
        save_only: bool = False,
        progress: Optional[Dict[str, Any]] = None,
        counters: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        visible_counters: List[Dict[str, Any]] = []
        for counter in counters or []:
            if not isinstance(counter, dict):
                continue
            if self.to_int(counter.get("value")) > 0 or bool(counter.get("show_when_zero")):
                visible_counters.append(counter)
        return {
            "schema_version": 1,
            "operation": str(operation or "").strip(),
            "action": str(action or "").strip(),
            "mode": str(mode or "").strip(),
            "phase": str(phase or "").strip(),
            "save_only": bool(save_only),
            "progress": progress if isinstance(progress, dict) else {},
            "counters": visible_counters,
        }

    def checks_payload(
        self,
        *,
        check_type: str,
        source_mode: str,
        phase: str,
        save_only: bool = False,
        files_scanned: Any = 0,
        total_files: Any = 0,
        findings_count: Any = 0,
        resolved_count: Any = 0,
        ignored_count: Any = 0,
        skipped_count: Any = 0,
        errors_count: Any = 0,
        entries_current: Any = 0,
        entries_total: Any = 0,
        stored_findings_count: Any = 0,
        transferred_count: Any = 0,
        **_ignored: Any,
    ) -> Dict[str, Any]:
        del stored_findings_count, transferred_count
        normalized_type = self.normalize_checks_type(check_type)
        mode = str(source_mode or "").strip().lower() or "scan"
        counters: List[Dict[str, Any]] = []
        if mode == "findings":
            status_progress = self.progress(kind="entries", current=entries_current, total=entries_total, title_key="checks:label_list_entries", fallback_title="Einträge", primary_label_key="checks:label_index", fallback_primary_label="Eintrag", secondary_label_key="checks:label_entries_remaining", fallback_secondary_label="verbleibend")
            for key, value, label_key, fallback in (("resolved", resolved_count, "checks:counter_resolved", "Aufgelöst"), ("ignored", ignored_count, "checks:counter_ignored", "Ignoriert"), ("skipped", skipped_count, "checks:counter_skipped", "Übersprungen"), ("errors", errors_count, "checks:counter_errors", "Fehler")):
                if self.to_int(value) > 0:
                    counters.append(self.counter(key, value=value, label_key=label_key, fallback_label=fallback))
        else:
            status_progress = self.progress(kind="files", current=files_scanned, total=total_files, title_key="checks:label_images", fallback_title="Bilder", primary_label_key="checks:label_scanned", fallback_primary_label="geprüft", secondary_label_key="checks:label_remaining", fallback_secondary_label="verbleibend")
            if save_only:
                counters.append(self.counter("findings", value=findings_count, label_key="checks:counter_findings", fallback_label="Funde", show_when_zero=True))
            else:
                for key, value, label_key, fallback in (("findings", findings_count, "checks:counter_findings", "Funde"), ("resolved", resolved_count, "checks:counter_resolved", "Aufgelöst"), ("ignored", ignored_count, "checks:counter_ignored", "Ignoriert"), ("skipped", skipped_count, "checks:counter_skipped", "Übersprungen"), ("errors", errors_count, "checks:counter_errors", "Fehler")):
                    if self.to_int(value) > 0:
                        counters.append(self.counter(key, value=value, label_key=label_key, fallback_label=fallback))
        return self.payload(operation="checks", action=normalized_type, mode=mode, phase=phase, save_only=save_only, progress=status_progress, counters=counters)

    def face_match_payload(
        self,
        *,
        action: str,
        source_mode: str = "scan",
        phase: str = "running",
        save_only: bool = False,
        progress_kind: str = "",
        current: Any = 0,
        total: Any = 0,
        findings_count: Any = 0,
        transferred_count: Any = 0,
        skipped_count: Any = 0,
        errors_count: Any = 0,
        created_count: Any = 0,
        assigned_count: Any = 0,
        updated_count: Any = 0,
        **_ignored: Any,
    ) -> Dict[str, Any]:
        normalized_action = str(action or "").strip().lower()
        mode = str(source_mode or "").strip().lower() or "scan"
        kind = str(progress_kind or "").strip().lower()
        if not kind:
            kind = "entries" if mode == "findings" else "persons"
        title_by_kind = {
            "entries": ("face_match:label_list_entries", "Einträge"),
            "files": ("face_match:label_files", "Dateien"),
            "images": ("face_match:label_images", "Bilder"),
            "persons": ("face_match:label_persons", "Personen"),
            "faces": ("face_match:label_faces", "Gesichter"),
            "metadata_faces": ("face_match:label_metadata_faces", "Metadaten-Gesichter"),
            "target_faces": ("face_match:label_target_faces", "Ziel-Gesichter"),
        }
        title_key, fallback_title = title_by_kind.get(kind, ("face_match:label_progress", "Fortschritt"))
        status_progress = self.progress(kind=kind, current=current, total=total, title_key=title_key, fallback_title=fallback_title, primary_label_key="face_match:label_checked", fallback_primary_label="geprüft", secondary_label_key="face_match:label_remaining", fallback_secondary_label="verbleibend")
        counters: List[Dict[str, Any]] = []
        if mode == "findings":
            for key, value, label_key, fallback in (("transferred", transferred_count, "face_match:counter_transferred", "Übertragen"), ("skipped", skipped_count, "face_match:counter_skipped", "Übersprungen"), ("errors", errors_count, "face_match:counter_errors", "Fehler")):
                if self.to_int(value) > 0:
                    counters.append(self.counter(key, value=value, label_key=label_key, fallback_label=fallback))
        elif save_only:
            counters.append(self.counter("findings", value=findings_count, label_key="face_match:counter_findings", fallback_label="Funde", show_when_zero=True))
        else:
            for key, value, label_key, fallback in (("transferred", transferred_count, "face_match:counter_transferred", "Übertragen"), ("skipped", skipped_count, "face_match:counter_skipped", "Übersprungen"), ("created", created_count, "face_match:counter_created", "Erstellt"), ("assigned", assigned_count, "face_match:counter_assigned", "Zugewiesen"), ("updated", updated_count, "face_match:counter_updated", "Geändert"), ("errors", errors_count, "face_match:counter_errors", "Fehler")):
                if self.to_int(value) > 0:
                    counters.append(self.counter(key, value=value, label_key=label_key, fallback_label=fallback))
        return self.payload(operation="face_match", action=normalized_action, mode=mode, phase=phase, save_only=save_only, progress=status_progress, counters=counters)
