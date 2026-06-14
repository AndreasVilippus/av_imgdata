#!/usr/bin/env python3
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from threading import Thread
from typing import Any, Dict, List

from handler.photos_handler import PhotosLookupCache
from models.bbox import BoundingBox
from services.bbox_normalizer import to_bbox_dict
from services.face_detector import InsightFaceDetector
from services.face_frame_matcher import frame_metrics, match_decision
from services.face_frame_standardizer import normalize_profile, target_frame


class FaceFrameStandardizationService:
    ACTION = "standardize_face_frames"
    FINDING_TYPE = "face_frame_standardization"

    def __init__(self, backend: Any):
        self.backend = backend

    @staticmethod
    def normalize_options(options: Any) -> Dict[str, Any]:
        source = dict(options) if isinstance(options, dict) else {}
        insightface = source.get("insightface") if isinstance(source.get("insightface"), dict) else source
        sources = source.get("sources") if isinstance(source.get("sources"), list) else []
        det_size = insightface.get("det_size") if isinstance(insightface.get("det_size"), list) else [640, 640]
        return {
            "mode": "preview",
            "target": "preview",
            "changed_since_days": max(0, int(source.get("changed_since_days") or 0)),
            "profile": normalize_profile(source.get("frame_profile") or source.get("profile")),
            "include_metadata": bool(source.get("include_metadata", not sources or any(item in sources for item in ("acdsee_xmp", "mwg_regions", "metadata")))),
            "include_photos": bool(source.get("include_photos", not sources or "photos" in sources)),
            "det_size": [
                max(64, int(det_size[0] if len(det_size) > 0 else 640)),
                max(64, int(det_size[1] if len(det_size) > 1 else 640)),
            ],
            "det_thresh": max(0.0, min(1.0, float(insightface.get("det_thresh", 0.5)))),
            "max_num": max(0, int(insightface.get("max_num") or 0)),
            "min_width_ratio": max(0.0, float(insightface.get("min_face_width_ratio", insightface.get("min_width_ratio", 0.0)) or 0.0)),
            "min_height_ratio": max(0.0, float(insightface.get("min_face_height_ratio", insightface.get("min_height_ratio", 0.0)) or 0.0)),
            "min_area_ratio": max(0.0, float(insightface.get("min_face_area_ratio", insightface.get("min_area_ratio", 0.0)) or 0.0)),
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

    def findings(self) -> Dict[str, Any]:
        return self.backend.file_analysis.readCheckFindings(self.FINDING_TYPE)

    def _status(self, *, phase: str, files_scanned: int, total_files: int, findings_count: int, errors_count: int) -> Dict[str, Any]:
        backend = self.backend
        return backend._buildStatusPayload(
            operation="cleanup",
            action=self.ACTION,
            mode="preview",
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
                backend._buildStatusCounter("findings", value=findings_count, label_key="cleanup:label_findings", fallback_label="Findings", show_when_zero=True),
                backend._buildStatusCounter("errors", value=errors_count, label_key="cleanup:label_errors", fallback_label="Errors"),
            ],
        )

    def _set_progress(self, user_key: str, **updates: Any) -> None:
        files_scanned = int(updates.get("files_scanned") or 0)
        total_files = int(updates.get("total_files") or 0)
        findings_count = int(updates.get("findings_count") or 0)
        errors_count = int(updates.get("errors_count") or 0)
        phase = str(updates.pop("phase", "") or ("running" if updates.get("running") else "finished"))
        updates["action"] = self.ACTION
        updates["status"] = self._status(
            phase=phase,
            files_scanned=files_scanned,
            total_files=total_files,
            findings_count=findings_count,
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

    def _run(self, *, user_key: str, cookies: Dict[str, str], base_url: str, options: Dict[str, Any]) -> None:
        backend = self.backend
        entries: List[Dict[str, Any]] = []
        errors: List[Dict[str, str]] = []
        files_scanned = 0
        try:
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
                use_cache=False,
            )
            detector = InsightFaceDetector(
                model_name=backend._configuredInsightFaceModelName(),
                model_root=backend._configuredInsightFaceModelRoot(),
                det_size=tuple(options["det_size"]),
                det_thresh=options["det_thresh"],
                max_num=options["max_num"],
                min_width_ratio=options["min_width_ratio"],
                min_height_ratio=options["min_height_ratio"],
                min_area_ratio=options["min_area_ratio"],
            )
            photos_cache = PhotosLookupCache()
            total_files = len(paths)
            for path in paths:
                if backend._shouldStopCleanup(user_key, self.ACTION):
                    break
                files_scanned += 1
                try:
                    sources = []
                    if options["include_metadata"]:
                        sources.extend(backend._readImageMetadata(path, include_unnamed_acd=True).faces)
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
                        decision = match_decision(metrics)
                        target = target_frame(best, profile=options["profile"])
                        target_delta = frame_metrics(source.bbox, target)
                        if target_delta["iou"] >= 0.999999:
                            continue
                        entries.append({
                            "item_id": self._finding_id(path, source.source_format, source_index),
                            "image_path": path,
                            "source_frame": {
                                "source": source.source,
                                "source_format": source.source_format,
                                "name": source.name,
                                "bbox": to_bbox_dict(source.bbox),
                            },
                            "insightface_frame": {
                                "bbox": to_bbox_dict(best),
                                "score": detections[detection_boxes.index(best)].get("score"),
                                "det_size": options["det_size"],
                            },
                            "target_frame": {
                                "bbox": to_bbox_dict(target),
                                "profile": options["profile"],
                            },
                            "match": {
                                **metrics,
                                "center_distance": metrics["center_delta"],
                                "score": detections[detection_boxes.index(best)].get("score"),
                                "decision": decision,
                            },
                            "target_delta": target_delta,
                            "selection_state": "selected" if decision == "safe" else "review",
                            "write_state": "pending",
                            "target": "preview",
                            "origin": {"value": "unknown", "confidence": "unknown"},
                            "warnings": [],
                        })
                except Exception as exc:
                    errors.append({"image_path": path, "error": f"{type(exc).__name__}: {exc}"})
                self._set_progress(
                    user_key,
                    running=True,
                    finished=False,
                    phase="running",
                    message_key="cleanup:face_frames_scanning",
                    message="Scanning face frames.",
                    current_path=path,
                    files_scanned=files_scanned,
                    total_files=total_files,
                    findings_count=len(entries),
                    errors_count=len(errors),
                    options=options,
                )
            stopped = backend._shouldStopCleanup(user_key, self.ACTION)
            payload = {
                "finding_type": self.FINDING_TYPE,
                "mode": "preview",
                "target": "preview",
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "options": options,
                "entries": entries,
                "errors": errors,
            }
            backend.file_analysis.writeCheckFindings(self.FINDING_TYPE, payload)
            self._set_progress(
                user_key,
                running=False,
                finished=True,
                stop_requested=stopped,
                phase="stopped" if stopped else "finished",
                message_key="cleanup:progress_stopped" if stopped else "cleanup:face_frames_finished",
                message="Face-frame preview stopped." if stopped else "Face-frame preview finished.",
                files_scanned=files_scanned,
                total_files=total_files,
                findings_count=len(entries),
                errors_count=len(errors),
                options=options,
            )
        except Exception as exc:
            errors.append({"image_path": "", "error": f"{type(exc).__name__}: {exc}"})
            backend.file_analysis.writeCheckFindings(self.FINDING_TYPE, {
                "finding_type": self.FINDING_TYPE,
                "mode": "preview",
                "target": "preview",
                "options": options,
                "entries": entries,
                "errors": errors,
            })
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
                errors_count=len(errors),
                options=options,
            )
