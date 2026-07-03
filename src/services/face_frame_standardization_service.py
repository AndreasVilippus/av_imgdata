#!/usr/bin/env python3
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock, Thread
from typing import Any, Dict, List

from handler.photos_handler import PhotosLookupCache
from models.bbox import BoundingBox
from services.bbox_normalizer import to_bbox_dict, to_xywh
from services.face_detector import FaceDetectorUnavailable
from services.face_frame_matcher import frame_metrics, match_decision
from services.face_frame_standardizer import build_target_frame, normalize_profile, normalize_strategy


class FaceFrameStandardizationService:
    ACTION = "standardize_face_frames"
    FINDING_TYPE = "face_frame_standardization"
    SOURCE_FORMATS = {"PHOTOS", "ACD", "MICROSOFT", "MWG_REGIONS"}
    SELECTION_MODES = {"review_all", "safe_matches"}
    OPERATION_MODES = {"immediate", "save_only", "findings"}

    def __init__(self, backend: Any):
        self.backend = backend
        self._detector = None
        self._detector_key = None
        self._active_findings: Dict[str, Dict[str, Any]] = {}
        self._active_findings_lock = RLock()

    @staticmethod
    def normalize_options(options: Any) -> Dict[str, Any]:
        source = dict(options) if isinstance(options, dict) else {}
        insightface = source.get("insightface") if isinstance(source.get("insightface"), dict) else source
        raw_sources = source.get("sources")
        explicit_sources = isinstance(raw_sources, (dict, list))
        if isinstance(raw_sources, dict):
            sources = [key for key, enabled in raw_sources.items() if enabled]
        elif isinstance(raw_sources, list):
            sources = raw_sources
        else:
            sources = []
        source_aliases = {
            "photos": "PHOTOS",
            "acd": "ACD",
            "acdsee": "ACD",
            "acdsee_xmp": "ACD",
            "microsoft": "MICROSOFT",
            "microsoft_xmp": "MICROSOFT",
            "mwg": "MWG_REGIONS",
            "mwg_regions": "MWG_REGIONS",
        }
        source_formats = {
            source_aliases.get(str(item or "").strip().lower(), str(item or "").strip().upper())
            for item in sources
        }
        source_formats.intersection_update(FaceFrameStandardizationService.SOURCE_FORMATS)
        if not explicit_sources:
            include_metadata = bool(source.get("include_metadata", True))
            if include_metadata:
                source_formats.update({"ACD", "MICROSOFT", "MWG_REGIONS"})
            if bool(source.get("include_photos", True)):
                source_formats.add("PHOTOS")
        selection_mode = str(source.get("selection_mode") or "review_all").strip().lower()
        if selection_mode not in FaceFrameStandardizationService.SELECTION_MODES:
            selection_mode = "review_all"
        operation_mode = str(source.get("operation_mode") or "immediate").strip().lower()
        if operation_mode not in FaceFrameStandardizationService.OPERATION_MODES:
            operation_mode = "immediate"
        det_size = insightface.get("det_size") if isinstance(insightface.get("det_size"), list) else [640, 640]
        return {
            "mode": "preview",
            "target": "preview",
            "changed_since_days": max(0, int(source.get("changed_since_days") or 0)),
            "profile": normalize_profile(source.get("frame_profile") or source.get("profile")),
            "strategy": normalize_strategy(source.get("strategy")),
            "selection_mode": selection_mode,
            "operation_mode": operation_mode,
            "source_formats": sorted(source_formats),
            "include_metadata": bool(source_formats.intersection({"ACD", "MICROSOFT", "MWG_REGIONS"})),
            "include_photos": "PHOTOS" in source_formats,
            "det_size": [
                max(64, int(det_size[0] if len(det_size) > 0 else 640)),
                max(64, int(det_size[1] if len(det_size) > 1 else 640)),
            ],
            "det_thresh": max(0.0, min(1.0, float(insightface.get("det_thresh", 0.5)))),
            "max_num": max(0, int(insightface.get("max_num") or 0)),
            "min_width_ratio": max(0.0, float(insightface.get("min_face_width_ratio", insightface.get("min_width_ratio", 0.0)) or 0.0)),
            "min_height_ratio": max(0.0, float(insightface.get("min_face_height_ratio", insightface.get("min_height_ratio", 0.0)) or 0.0)),
            "min_area_ratio": max(0.0, float(insightface.get("min_face_area_ratio", insightface.get("min_area_ratio", 0.0)) or 0.0)),
            "safe_iou": max(0.0, min(1.0, float(source.get("safe_iou", 0.65)))),
            "review_iou": max(0.0, min(1.0, float(source.get("review_iou", 0.30)))),
            "safe_center_delta": max(0.0, min(1.0, float(source.get("safe_center_delta", 0.08)))),
            "safe_size_delta": max(0.0, min(1.0, float(source.get("safe_size_delta", 0.50)))),
            "resume_existing": bool(source.get("resume_existing", False)),
        }

    def start(
        self,
        *,
        user_key: str,
        cookies: Dict[str, str],
        base_url: str,
        options: Any,
    ) -> Dict[str, Any]:
        normalized = self.normalize_options(options)
        if normalized["operation_mode"] == "findings":
            findings = self.findings(operation_mode="findings")
            entries = findings.get("entries") if isinstance(findings.get("entries"), list) else []
            self._set_progress(
                user_key,
                running=False,
                finished=True,
                operation_id="",
                phase="review_required" if entries else "finished",
                message_key="cleanup:face_frames_review_required" if entries else "cleanup:face_frames_findings_empty",
                message="Manual review required for saved face-frame findings." if entries else "No saved face-frame findings.",
                findings_count=len(entries),
                options=normalized,
            )
            return self.backend.getCleanupProgress(user_key, self.ACTION)
        if not normalized.get("resume_existing"):
            self._clear_active_findings(user_key)
        operation_id = f"cleanup-{self.ACTION}-{hashlib.sha256(str(datetime.now(timezone.utc)).encode()).hexdigest()[:16]}"
        self._set_progress(
            user_key,
            running=True,
            finished=False,
            stop_requested=False,
            operation_id=operation_id,
            message_key="cleanup:face_frames_preparing",
            message="Face-frame preview is being prepared.",
            options=normalized,
        )
        worker = Thread(
            target=self._run,
            kwargs={
                "user_key": user_key,
                "cookies": dict(cookies),
                "base_url": base_url,
                "options": normalized,
            },
            daemon=True,
        )
        state_key = self.backend._cleanupStateKey(user_key, self.ACTION)
        self.backend.runtime_state.values("cleanup_threads")[state_key] = worker
        worker.start()
        return self.backend.getCleanupProgress(user_key, self.ACTION)

    def _active_key(self, user_key: str) -> str:
        return str(user_key or "").strip() or "default"

    def _read_active_findings(self, user_key: str) -> Dict[str, Any]:
        with self._active_findings_lock:
            current = self._active_findings.get(self._active_key(user_key), {})
            return dict(current) if isinstance(current, dict) else {}

    def _write_active_findings(self, user_key: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        current = dict(payload) if isinstance(payload, dict) else {}
        with self._active_findings_lock:
            self._active_findings[self._active_key(user_key)] = current
        return dict(current)

    def _clear_active_findings(self, user_key: str) -> None:
        with self._active_findings_lock:
            self._active_findings.pop(self._active_key(user_key), None)

    def findings(self, *, user_key: str = "", operation_mode: str = "") -> Dict[str, Any]:
        mode = str(operation_mode or "").strip().lower()
        if mode == "immediate":
            return self._read_active_findings(user_key)
        reader = getattr(self.backend.file_analysis, "readCheckFindings", None)
        findings = reader(self.FINDING_TYPE) if callable(reader) else {}
        if mode in {"findings", "save_only"}:
            return findings if isinstance(findings, dict) else {}
        active = self._read_active_findings(user_key)
        return active or (findings if isinstance(findings, dict) else {})

    def _read_working_findings(self, *, user_key: str, operation_mode: str) -> Dict[str, Any]:
        if str(operation_mode or "").strip().lower() == "immediate":
            return self._read_active_findings(user_key)
        return self.findings(operation_mode="findings")

    def _write_working_findings(self, *, user_key: str, operation_mode: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        if str(operation_mode or "").strip().lower() == "immediate":
            return self._write_active_findings(user_key, payload)
        self.backend.file_analysis.writeCheckFindings(self.FINDING_TYPE, payload)
        return payload

    def update_selection(self, *, item_id: str, selected: bool, user_key: str = "", operation_mode: str = "findings") -> Dict[str, Any]:
        normalized_id = str(item_id or "").strip()
        mode = str(operation_mode or "findings").strip().lower()
        lock = self._active_findings_lock if mode == "immediate" else self.backend.file_analysis.lockCheckFindings(self.FINDING_TYPE)
        with lock:
            payload = self._read_working_findings(user_key=user_key, operation_mode=mode)
            entries = payload.get("entries") if isinstance(payload.get("entries"), list) else []
            updated = False
            for entry in entries:
                if str(entry.get("item_id") or "") != normalized_id:
                    continue
                entry["selection_state"] = "selected" if selected else "skipped"
                if not selected:
                    entry["write_state"] = "skipped"
                updated = True
                break
            if updated:
                payload["entries"] = entries
                self._write_working_findings(user_key=user_key, operation_mode=mode, payload=payload)
        return {"updated": updated, "item_id": normalized_id, "selected": bool(selected)}

    @staticmethod
    def _open_entries(entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return [
            entry for entry in entries
            if str(entry.get("write_state") or "pending").strip().lower() == "pending"
            and str(entry.get("selection_state") or "review").strip().lower() == "review"
        ]

    @staticmethod
    def _resume_comparable_options(options: Dict[str, Any]) -> Dict[str, Any]:
        comparable = dict(options) if isinstance(options, dict) else {}
        comparable.pop("resume_existing", None)
        return comparable

    @staticmethod
    def _prepare_automatic_selections(entries: List[Dict[str, Any]]) -> None:
        writable_formats = {"PHOTOS", "ACD", "MICROSOFT", "MWG_REGIONS"}
        for entry in entries:
            if str(entry.get("write_state") or "pending").strip().lower() != "pending":
                continue
            source_frame = entry.get("source_frame") if isinstance(entry.get("source_frame"), dict) else {}
            match = entry.get("match") if isinstance(entry.get("match"), dict) else {}
            is_safe_writable = (
                str(match.get("decision") or "").strip().lower() == "safe"
                and str(source_frame.get("source_format") or "").strip().upper() in writable_formats
            )
            entry["selection_state"] = "selected" if is_safe_writable else "review"

    def sync_review_progress(self, *, user_key: str, operation_mode: str = "immediate") -> Dict[str, Any]:
        status_mode = "findings" if str(operation_mode or "").strip().lower() == "findings" else "scan"
        findings = self._read_working_findings(user_key=user_key, operation_mode=operation_mode)
        entries = findings.get("entries") if isinstance(findings.get("entries"), list) else []
        open_entries = self._open_entries(entries)
        current_entry = open_entries[0] if open_entries else {}
        total_count = len(entries)
        open_count = len(open_entries)
        processed_count = max(0, total_count - open_count)
        written_count = sum(1 for entry in entries if str(entry.get("write_state") or "").strip().lower() == "written")
        errors_count = sum(1 for entry in entries if str(entry.get("write_state") or "").strip().lower() == "failed")
        status = self.backend._buildStatusPayload(
            operation="cleanup",
            action=self.ACTION,
            mode=status_mode,
            phase="review_required" if open_entries else "finished",
            progress=self.backend._buildStatusProgress(
                kind="entries",
                current=processed_count,
                total=total_count,
                title_key="checks:label_list_entries",
                fallback_title="Entries",
                primary_label_key="checks:label_index",
                fallback_primary_label="Entry",
                secondary_label_key="checks:label_entries_remaining",
                fallback_secondary_label="remaining",
            ),
            counters=[
                self.backend._buildStatusCounter("findings", value=open_count, label_key="cleanup:label_findings", fallback_label="Findings", show_when_zero=True),
                self.backend._buildStatusCounter("written", value=written_count, label_key="cleanup:label_written", fallback_label="Written", show_when_zero=True),
                self.backend._buildStatusCounter("errors", value=errors_count, label_key="cleanup:label_errors", fallback_label="Errors"),
            ],
        )
        return self.backend._setCleanupProgress(
            user_key,
            action=self.ACTION,
            running=False,
            finished=True,
            phase="review_required" if open_entries else "finished",
            message_key="cleanup:face_frames_review_required" if open_entries else "cleanup:face_frames_finished",
            message="Manual review required for the next face-frame finding." if open_entries else "Face-frame preview finished.",
            current_path=str(current_entry.get("image_path") or ""),
            findings_count=open_count,
            written_count=written_count,
            errors_count=errors_count,
            status=status,
        )

    def apply_selected(
        self,
        *,
        selected_item_ids: Any = None,
        user_key: str = "",
        operation_mode: str = "findings",
        cookies: Any = None,
        base_url: str = "",
    ) -> Dict[str, Any]:
        requested_ids = {
            str(item or "").strip()
            for item in list(selected_item_ids or [])
            if str(item or "").strip()
        }
        mode = str(operation_mode or "findings").strip().lower()
        lock = self._active_findings_lock if mode == "immediate" else self.backend.file_analysis.lockCheckFindings(self.FINDING_TYPE)
        with lock:
            payload = self._read_working_findings(user_key=user_key, operation_mode=mode)
            entries = payload.get("entries") if isinstance(payload.get("entries"), list) else []
            written_count = 0
            skipped_count = 0
            errors_count = 0
            for entry in entries:
                item_id = str(entry.get("item_id") or "").strip()
                if requested_ids:
                    selected = item_id in requested_ids
                else:
                    selected = str(entry.get("selection_state") or "").strip().lower() == "selected"
                if not selected or str(entry.get("write_state") or "").strip().lower() == "written":
                    continue
                source_frame = entry.get("source_frame") if isinstance(entry.get("source_frame"), dict) else {}
                source_format = str(source_frame.get("source_format") or "").strip().upper()
                if source_format not in {"PHOTOS", "ACD", "MICROSOFT", "MWG_REGIONS"}:
                    entry["write_state"] = "locked"
                    entry["warnings"] = [*list(entry.get("warnings") or []), "unknown_target_not_writable"]
                    skipped_count += 1
                    continue
                target = entry.get("target_frame") if isinstance(entry.get("target_frame"), dict) else {}
                target_bbox = target.get("bbox") if isinstance(target.get("bbox"), dict) else {}
                try:
                    x1 = float(target_bbox["x1"])
                    y1 = float(target_bbox["y1"])
                    x2 = float(target_bbox["x2"])
                    y2 = float(target_bbox["y2"])
                except (KeyError, TypeError, ValueError):
                    entry["write_state"] = "failed"
                    entry["warnings"] = [*list(entry.get("warnings") or []), "invalid_target_frame"]
                    errors_count += 1
                    continue
                replacement = {
                    "name": str(source_frame.get("name") or ""),
                    "source": "insightface",
                    "source_format": "INSIGHTFACE",
                    "x": (x1 + x2) / 2,
                    "y": (y1 + y2) / 2,
                    "w": x2 - x1,
                    "h": y2 - y1,
                }
                try:
                    if source_format == "PHOTOS":
                        result = self.backend.replacePhotosFacePosition(
                            user_key=user_key,
                            cookies=dict(cookies or {}),
                            base_url=base_url,
                            image_path=str(entry.get("image_path") or ""),
                            face_data=source_frame,
                            source_face_data=replacement,
                        )
                    else:
                        result = self.backend.replaceMetadataFacePosition(
                            image_path=str(entry.get("image_path") or ""),
                            face_data=source_frame,
                            source_face_data=replacement,
                        )
                except Exception as exc:
                    result = {"updated": False, "warning": f"{type(exc).__name__}: {exc}"}
                if result.get("updated"):
                    entry["write_state"] = "written"
                    written_count += 1
                else:
                    entry["write_state"] = "failed"
                    entry["warnings"] = [*list(entry.get("warnings") or []), str(result.get("warning") or "write_failed")]
                    errors_count += 1
            payload["entries"] = entries
            payload["written_count"] = written_count
            payload["skipped_count"] = skipped_count
            payload["errors_count"] = errors_count
            self._write_working_findings(user_key=user_key, operation_mode=mode, payload=payload)
        return {
            "written_count": written_count,
            "skipped_count": skipped_count,
            "errors_count": errors_count,
            "findings": payload,
        }

    def _status(self, *, phase: str, files_scanned: int, total_files: int, findings_count: int, selected_count: int, written_count: int, errors_count: int) -> Dict[str, Any]:
        backend = self.backend
        return backend._buildStatusPayload(
            operation="cleanup",
            action=self.ACTION,
            mode="scan",
            phase=phase,
            progress=backend._buildStatusProgress(
                kind="files",
                current=files_scanned,
                total=total_files,
                title_key="cleanup:label_images",
                fallback_title="Images",
                primary_label_key="cleanup:label_scanned",
                fallback_primary_label="scanned",
                secondary_label_key="cleanup:label_files_remaining",
                fallback_secondary_label="remaining",
            ),
            counters=[
                backend._buildStatusCounter("checked", value=files_scanned, label_key="cleanup:label_checked_count", fallback_label="Checked", show_when_zero=True),
                backend._buildStatusCounter("findings", value=findings_count, label_key="cleanup:label_findings", fallback_label="Findings", show_when_zero=True),
                backend._buildStatusCounter("automatic", value=selected_count, label_key="cleanup:label_automatic", fallback_label="Automatic", show_when_zero=True),
                backend._buildStatusCounter("written", value=written_count, label_key="cleanup:label_corrected", fallback_label="Corrected", show_when_zero=True),
                backend._buildStatusCounter("errors", value=errors_count, label_key="cleanup:label_errors", fallback_label="Errors"),
            ],
        )

    def _set_progress(self, user_key: str, **updates: Any) -> None:
        files_scanned = int(updates.get("files_scanned") or 0)
        total_files = int(updates.get("total_files") or 0)
        findings_count = int(updates.get("findings_count") or 0)
        selected_count = int(updates.get("selected_count") or 0)
        written_count = int(updates.get("written_count") or 0)
        errors_count = int(updates.get("errors_count") or 0)
        phase = str(updates.pop("phase", "") or ("running" if updates.get("running") else "finished"))
        updates.setdefault("files_scanned", files_scanned)
        updates.setdefault("total_files", total_files)
        updates.setdefault("findings_count", findings_count)
        updates.setdefault("selected_count", selected_count)
        updates.setdefault("written_count", written_count)
        updates.setdefault("errors_count", errors_count)
        updates.setdefault("current_path", "")
        updates["action"] = self.ACTION
        updates["status"] = self._status(
            phase=phase,
            files_scanned=files_scanned,
            total_files=total_files,
            findings_count=findings_count,
            selected_count=selected_count,
            written_count=written_count,
            errors_count=errors_count,
        )
        self.backend._setCleanupProgress(user_key, **updates)

    @staticmethod
    def _detection_box(detection: Dict[str, Any]) -> BoundingBox:
        bbox = detection["bbox"]
        return BoundingBox(float(bbox["x1"]), float(bbox["y1"]), float(bbox["x2"]), float(bbox["y2"]))

    @staticmethod
    def _finding_id(path: str, source_format: str, source_index: int) -> str:
        raw = f"{path}\0{source_format}\0{source_index}".encode("utf-8")
        return hashlib.sha256(raw).hexdigest()

    def _prepared_detector(self, options: Dict[str, Any]) -> Any:
        backend = self.backend
        detector_key = (
            backend._faceProcessorRuntimeKey() if hasattr(backend, "_faceProcessorRuntimeKey") else ("python",),
            backend._configuredInsightFaceModelName(),
            str(backend._configuredInsightFaceModelRoot()),
            tuple(options["det_size"]),
            options["det_thresh"],
            options["max_num"],
            options["min_width_ratio"],
            options["min_height_ratio"],
            options["min_area_ratio"],
        )
        if self._detector is not None and self._detector_key == detector_key:
            return self._detector
        create_detector = getattr(backend, "_createFaceDetector", None)
        if not callable(create_detector):
            raise FaceDetectorUnavailable("native face processor is required")
        detector = create_detector(
            model_name=detector_key[1],
            model_root=backend._configuredInsightFaceModelRoot(),
            det_size=detector_key[3],
            det_thresh=options["det_thresh"],
            max_num=options["max_num"],
            min_width_ratio=options["min_width_ratio"],
            min_height_ratio=options["min_height_ratio"],
            min_area_ratio=options["min_area_ratio"],
        )
        prepare_detector = getattr(detector, "prepare", None)
        if callable(prepare_detector):
            prepare_detector()
        self._detector = detector
        self._detector_key = detector_key
        return detector

    def _run(self, *, user_key: str, cookies: Dict[str, str], base_url: str, options: Dict[str, Any]) -> None:
        backend = self.backend
        storage_mode = str(options.get("operation_mode") or "immediate").strip().lower()
        persist_findings = storage_mode == "save_only"
        active_findings = storage_mode == "immediate"
        resume_existing = bool(options.get("resume_existing", False))
        if resume_existing and active_findings:
            previous = self._read_active_findings(user_key)
        elif resume_existing and persist_findings:
            previous = self.findings(operation_mode="save_only")
        else:
            previous = {}
        previous_entries = previous.get("entries") if resume_existing and isinstance(previous.get("entries"), list) else []
        resolved_ids = {
            str(entry.get("item_id") or "")
            for entry in previous_entries
            if str(entry.get("write_state") or "").strip().lower() in {"written", "skipped"}
        }
        entries: List[Dict[str, Any]] = [] if options["operation_mode"] == "save_only" else list(previous_entries)
        if options["selection_mode"] == "safe_matches":
            self._prepare_automatic_selections(entries)
        errors: List[Dict[str, str]] = []
        files_scanned = 0
        try:
            self._set_progress(
                user_key,
                running=True,
                finished=False,
                phase="listing_files",
                message_key="cleanup:face_frames_listing_files",
                message="Building image list.",
                options=options,
            )
            shared_folder = backend.core.getSharedFolder(
                user_key=user_key,
                cookies=cookies,
                base_url=base_url,
                folder_name="photo",
            )
            paths = backend.checks_workflow.get_candidate_paths(
                user_key=user_key,
                check_type=self.FINDING_TYPE,
                shared_folder=shared_folder or "",
                changed_since_days=options["changed_since_days"],
                use_cache=True,
            )
            total_files = len(paths)
            previous_options = previous.get("options") if isinstance(previous.get("options"), dict) else {}
            can_resume = (
                resume_existing
                and options["operation_mode"] == "immediate"
                and str(previous.get("status") or "").strip().lower() == "review_required"
                and self._resume_comparable_options(previous_options) == self._resume_comparable_options(options)
            )
            start_index = max(0, int(previous.get("scan_next_path_index") or 0)) if can_resume else 0
            start_index = min(start_index, total_files)
            files_scanned = start_index
            self._set_progress(
                user_key,
                running=True,
                finished=False,
                phase="preparing_detector",
                message_key="cleanup:face_frames_preparing_detector",
                message="Preparing InsightFace detection model.",
                files_scanned=files_scanned,
                total_files=total_files,
                options=options,
            )
            detector = self._prepared_detector(options)
            photos_cache = PhotosLookupCache()
            for index, path in enumerate(paths[start_index:], start=start_index):
                if backend._shouldStopCleanup(user_key, self.ACTION):
                    break
                files_scanned = index + 1
                try:
                    sources = []
                    if options["include_metadata"]:
                        metadata_faces = backend._readImageMetadata(path, include_unnamed_acd=True).faces
                        sources.extend(
                            face for face in metadata_faces
                            if str(face.source_format or "").strip().upper() in options["source_formats"]
                        )
                    if options["include_photos"]:
                        sources.extend(backend._loadPhotoFacesForImage(
                            user_key=user_key,
                            cookies=cookies,
                            base_url=base_url,
                            shared_folder=shared_folder or "",
                            image_path=path,
                            photos_lookup_cache=photos_cache,
                        ))
                    detections = detector.detect(Path(path))
                    detection_boxes = [self._detection_box(item) for item in detections]
                    for source_index, source in enumerate(sources):
                        if not detection_boxes:
                            break
                        best = max(detection_boxes, key=lambda item: frame_metrics(source.bbox, item)["iou"])
                        metrics = frame_metrics(source.bbox, best)
                        decision = match_decision(
                            metrics,
                            safe_iou=options["safe_iou"],
                            review_iou=options["review_iou"],
                            safe_center_delta=options["safe_center_delta"],
                            safe_size_delta=options["safe_size_delta"],
                        )
                        target = build_target_frame(
                            source.bbox,
                            best,
                            strategy=options["strategy"],
                            profile=options["profile"],
                        )
                        target_delta = frame_metrics(source.bbox, target)
                        if target_delta["iou"] >= 0.999999:
                            continue
                        item_id = self._finding_id(path, source.source_format, source_index)
                        if item_id in resolved_ids or any(str(entry.get("item_id") or "") == item_id for entry in entries):
                            continue
                        auto_selected = (
                            options["selection_mode"] == "safe_matches"
                            and decision == "safe"
                            and str(source.source_format or "").strip().upper() in {"PHOTOS", "ACD", "MICROSOFT", "MWG_REGIONS"}
                        )
                        entries.append({
                            "item_id": item_id,
                            "image_path": path,
                            "source_frame": {
                                "source": source.source,
                                "source_format": source.source_format,
                                "name": source.name,
                                "face_id": getattr(source, "face_id", None),
                                "person_id": getattr(source, "person_id", None),
                                "item_id": getattr(source, "item_id", None),
                                **to_xywh(source.bbox),
                                "bbox": to_bbox_dict(source.bbox),
                                "orientation": getattr(source, "orientation", None),
                            },
                            "insightface_frame": {
                                "bbox": to_bbox_dict(best),
                                "score": detections[detection_boxes.index(best)].get("score"),
                                "det_size": options["det_size"],
                            },
                            "target_frame": {
                                "bbox": to_bbox_dict(target),
                                "profile": options["profile"],
                                "strategy": options["strategy"],
                            },
                            "match": {
                                **metrics,
                                "center_distance": metrics["center_delta"],
                                "score": detections[detection_boxes.index(best)].get("score"),
                                "decision": decision,
                            },
                            "target_delta": target_delta,
                            "selection_state": (
                                "selected" if auto_selected else "review"
                            ),
                            "write_state": "pending",
                            "target": "preview",
                            "origin": {"value": "unknown", "confidence": "unknown"},
                            "warnings": [],
                        })
                except Exception as exc:
                    errors.append({"image_path": path, "error": f"{type(exc).__name__}: {exc}"})
                payload = {
                    "finding_type": self.FINDING_TYPE,
                    "mode": options["operation_mode"],
                    "target": "preview",
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                    "options": options,
                    "entries": entries,
                    "errors": errors,
                    "status": "running",
                    "scan_next_path_index": index + 1,
                    "total_files": total_files,
                }
                if persist_findings:
                    backend.file_analysis.writeCheckFindings(self.FINDING_TYPE, payload)
                elif active_findings:
                    self._write_active_findings(user_key, payload)
                apply_result = {"written_count": 0, "errors_count": 0}
                if active_findings and options["selection_mode"] == "safe_matches":
                    apply_result = self.apply_selected(
                        user_key=user_key,
                        operation_mode="immediate",
                        cookies=cookies,
                        base_url=base_url,
                    )
                    payload = apply_result.get("findings") if isinstance(apply_result.get("findings"), dict) else payload
                    entries = payload.get("entries") if isinstance(payload.get("entries"), list) else entries
                open_entries = self._open_entries(entries)
                self._set_progress(
                    user_key,
                    running=not (options["operation_mode"] == "immediate" and bool(open_entries)),
                    finished=options["operation_mode"] == "immediate" and bool(open_entries),
                    phase="review_required" if options["operation_mode"] == "immediate" and open_entries else "running",
                    message_key="cleanup:face_frames_review_required" if options["operation_mode"] == "immediate" and open_entries else "cleanup:face_frames_scanning",
                    message="Manual review required for the next face-frame finding." if options["operation_mode"] == "immediate" and open_entries else "Scanning face frames.",
                    current_path=path,
                    files_scanned=files_scanned,
                    total_files=total_files,
                    findings_count=len(open_entries),
                    selected_count=sum(1 for entry in entries if entry.get("selection_state") == "selected"),
                    written_count=sum(1 for entry in entries if entry.get("write_state") == "written"),
                    errors_count=len(errors) + int(apply_result.get("errors_count") or 0),
                    options=options,
                )
                if options["operation_mode"] == "immediate" and open_entries:
                    break
            stopped = backend._shouldStopCleanup(user_key, self.ACTION)
            payload = {
                "finding_type": self.FINDING_TYPE,
                "mode": options["operation_mode"],
                "target": "preview",
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "options": options,
                "entries": entries,
                "errors": errors,
                "scan_next_path_index": files_scanned,
                "total_files": total_files,
            }
            if persist_findings:
                backend.file_analysis.writeCheckFindings(self.FINDING_TYPE, payload)
            elif active_findings:
                self._write_active_findings(user_key, payload)
            apply_result = {"written_count": 0, "skipped_count": 0, "errors_count": 0}
            if active_findings and not stopped and options["selection_mode"] == "safe_matches":
                apply_result = self.apply_selected(
                    user_key=user_key,
                    operation_mode="immediate",
                    cookies=cookies,
                    base_url=base_url,
                )
                payload = apply_result.get("findings") if isinstance(apply_result.get("findings"), dict) else payload
                entries = payload.get("entries") if isinstance(payload.get("entries"), list) else entries
            open_entries = self._open_entries(entries)
            review_required = options["operation_mode"] == "immediate" and bool(open_entries)
            payload["status"] = "review_required" if review_required else ("stopped" if stopped else "finished")
            if persist_findings:
                backend.file_analysis.writeCheckFindings(self.FINDING_TYPE, payload)
            elif active_findings:
                self._write_active_findings(user_key, payload)
            self._set_progress(
                user_key,
                running=False,
                finished=True,
                stop_requested=stopped,
                phase="stopped" if stopped else ("review_required" if review_required else "finished"),
                message_key="cleanup:progress_stopped" if stopped else ("cleanup:face_frames_review_required" if review_required else "cleanup:face_frames_finished"),
                message="Face-frame preview stopped." if stopped else ("Manual review required for the next face-frame finding." if review_required else "Face-frame preview finished."),
                files_scanned=files_scanned,
                total_files=total_files,
                findings_count=len(open_entries),
                selected_count=sum(1 for entry in entries if entry.get("selection_state") == "selected"),
                written_count=sum(1 for entry in entries if entry.get("write_state") == "written"),
                errors_count=len(errors) + sum(1 for entry in entries if entry.get("write_state") == "failed"),
                options=options,
            )
        except Exception as exc:
            errors.append({"image_path": "", "error": f"{type(exc).__name__}: {exc}"})
            payload = {
                "finding_type": self.FINDING_TYPE,
                "mode": "preview",
                "target": "preview",
                "options": options,
                "entries": entries,
                "errors": errors,
            }
            if persist_findings:
                backend.file_analysis.writeCheckFindings(self.FINDING_TYPE, payload)
            elif active_findings:
                self._write_active_findings(user_key, payload)
            self._set_progress(
                user_key,
                running=False,
                finished=True,
                phase="failed",
                message_key="cleanup:face_frames_failed",
                message=f"Face-frame preview failed: {exc}",
                files_scanned=files_scanned,
                total_files=0,
                findings_count=len(entries),
                selected_count=sum(1 for entry in entries if entry.get("selection_state") == "selected"),
                written_count=0,
                errors_count=len(errors),
                options=options,
            )
