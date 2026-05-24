#!/usr/bin/env python3
from time import monotonic
from typing import Any, Callable, Dict


class FaceMatchMutationService:
    def __init__(self, backend: Any, debug_logger: Callable[..., None]):
        self.backend = backend
        self._debug_logger = debug_logger

    def _debugLog(self, event: str, **fields: Any) -> None:
        logger = self._debug_logger
        try:
            logger(event, **fields)
        except Exception:
            pass

    def apply_photo_face_assignment(
        self,
        *,
        user_key: str,
        cookies: Dict[str, str],
        base_url: str,
        face_id: int,
        person_id: int,
        person_name: str,
        save_mapping: bool = False,
        source_name: Any = "",
    ) -> Dict[str, Any]:
        started = monotonic()
        normalized_person_name = str(person_name or "").strip()
        self._debugLog(
            "face_match_assignment_start",
            face_id=face_id,
            person_id=person_id,
            save_mapping=bool(save_mapping),
            source_name_present=bool(str(source_name or "").strip()),
        )
        assign_started = monotonic()
        result = self.backend.assignMatchedFaceToKnownPerson(
            user_key=user_key,
            cookies=cookies,
            base_url=base_url,
            face_id=face_id,
            person_id=person_id,
            person_name=normalized_person_name,
        )
        self._debugLog(
            "face_match_assignment_phase",
            phase="photos_assign",
            duration_ms=round((monotonic() - assign_started) * 1000, 2),
            face_id=face_id,
            person_id=person_id,
        )
        findings_started = monotonic()
        findings_update = self.backend.removeFaceMatchFindingEntry(
            face_id=face_id,
            increment_transferred_count=True,
        )
        self._debugLog(
            "face_match_assignment_phase",
            phase="findings_remove",
            duration_ms=round((monotonic() - findings_started) * 1000, 2),
            face_id=face_id,
            findings_count=int(findings_update.get("count") or 0) if isinstance(findings_update, dict) else None,
            transferred_count=int(findings_update.get("transferred_count") or 0) if isinstance(findings_update, dict) else None,
        )
        mapping_started = monotonic()
        mapping_saved = False
        normalized_source_name = str(source_name or "").strip()
        if save_mapping and normalized_source_name and normalized_person_name:
            mapping_saved = self.backend.saveNameMapping(
                source_name=normalized_source_name,
                target_name=normalized_person_name,
            )
        self._debugLog(
            "face_match_assignment_phase",
            phase="mapping_save",
            duration_ms=round((monotonic() - mapping_started) * 1000, 2),
            requested=bool(save_mapping),
            saved=bool(mapping_saved),
        )
        self._debugLog(
            "face_match_assignment_end",
            duration_ms=round((monotonic() - started) * 1000, 2),
            face_id=face_id,
            person_id=person_id,
            mapping_saved=bool(mapping_saved),
        )
        return {
            "face_id": face_id,
            "person_id": person_id,
            "result": result,
            "findings_update": findings_update,
            "mapping_saved": mapping_saved if save_mapping else False,
        }

    def apply_photo_face_person_creation(
        self,
        *,
        user_key: str,
        cookies: Dict[str, str],
        base_url: str,
        face_id: int,
        person_name: str,
        save_mapping: bool = False,
        source_name: Any = "",
    ) -> Dict[str, Any]:
        started = monotonic()
        normalized_person_name = str(person_name or "").strip()
        self._debugLog(
            "face_match_create_person_start",
            face_id=face_id,
            save_mapping=bool(save_mapping),
            source_name_present=bool(str(source_name or "").strip()),
        )
        create_started = monotonic()
        result = self.backend.resolveOrCreatePhotosPersonForExistingFace(
            user_key=user_key,
            cookies=cookies,
            base_url=base_url,
            image_path="",
            face_id=face_id,
            person_name=normalized_person_name,
            create_missing_person=True,
        )
        self._debugLog(
            "face_match_create_person_phase",
            phase="photos_resolve_or_create",
            duration_ms=round((monotonic() - create_started) * 1000, 2),
            face_id=face_id,
            operation=result.get("operation") if isinstance(result, dict) else "",
            target_person_id=(result.get("target_person") or {}).get("id") if isinstance(result, dict) and isinstance(result.get("target_person"), dict) else None,
        )
        findings_started = monotonic()
        findings_update = self.backend.removeFaceMatchFindingEntry(
            face_id=face_id,
            increment_transferred_count=True,
        )
        self._debugLog(
            "face_match_create_person_phase",
            phase="findings_remove",
            duration_ms=round((monotonic() - findings_started) * 1000, 2),
            face_id=face_id,
            findings_count=int(findings_update.get("count") or 0) if isinstance(findings_update, dict) else None,
            transferred_count=int(findings_update.get("transferred_count") or 0) if isinstance(findings_update, dict) else None,
        )
        mapping_started = monotonic()
        mapping_saved = False
        normalized_source_name = str(source_name or "").strip()
        if save_mapping and normalized_source_name and normalized_person_name:
            mapping_saved = self.backend.saveNameMapping(
                source_name=normalized_source_name,
                target_name=normalized_person_name,
            )
        self._debugLog(
            "face_match_create_person_phase",
            phase="mapping_save",
            duration_ms=round((monotonic() - mapping_started) * 1000, 2),
            requested=bool(save_mapping),
            saved=bool(mapping_saved),
        )
        person_id = (result.get("target_person") or {}).get("id") if isinstance(result, dict) and isinstance(result.get("target_person"), dict) else None
        self._debugLog(
            "face_match_create_person_end",
            duration_ms=round((monotonic() - started) * 1000, 2),
            face_id=face_id,
            person_id=person_id,
            mapping_saved=bool(mapping_saved),
        )
        return {
            "face_id": face_id,
            "person_id": person_id,
            "person_name": normalized_person_name,
            "result": result,
            "findings_update": findings_update,
            "mapping_saved": mapping_saved if save_mapping else False,
        }
