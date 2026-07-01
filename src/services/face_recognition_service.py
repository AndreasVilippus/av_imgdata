#!/usr/bin/env python3
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import RLock, Thread
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

from services.bbox_normalizer import from_photos, to_bbox_dict
from services.face_embedder import InsightFaceEmbedder


class FaceRecognitionService:
    ACTION_BUILD = "recognition_build_profiles"
    ACTION_OUTLIERS = "recognition_check_reference_outliers"
    ACTION_SUGGEST = "recognition_analyze_unknown_faces"
    ACTION_ASSIGNMENT = "recognition_check_person_assignments"
    ACTIONS = {ACTION_BUILD, ACTION_OUTLIERS, ACTION_SUGGEST, ACTION_ASSIGNMENT}
    FINDING_PROFILES = "recognition_profiles"
    FINDING_QUALITY = "recognition_profile_quality"
    FINDING_OUTLIERS = "recognition_reference_outliers"
    FINDING_SUGGESTIONS = "recognition_suggestions"
    FINDING_ASSIGNMENTS = "recognition_person_assignment_suggestions"
    PROFILE_STATE_TYPE = "recognition_profiles"

    def __init__(self, backend: Any):
        self.backend = backend
        self._embedder: Optional[InsightFaceEmbedder] = None
        self._embedder_key = None
        self._image_embedding_cache: Dict[str, List[Dict[str, Any]]] = {}
        self._image_quality_issues: List[Dict[str, Any]] = []
        self._active_findings: Dict[str, Dict[str, Any]] = {}
        self._active_findings_lock = RLock()

    @staticmethod
    def normalize_options(options: Any) -> Dict[str, Any]:
        source = dict(options) if isinstance(options, dict) else {}
        operation_mode = str(source.get("operation_mode") or "immediate").strip().lower()
        if operation_mode not in {"immediate", "save_only", "findings"}:
            operation_mode = "immediate"
        selection_mode = str(source.get("selection_mode") or "review_all").strip().lower()
        if selection_mode not in {"review_all", "safe_only", "exclude_confirmed"}:
            selection_mode = "review_all"
        det_size = source.get("det_size") if isinstance(source.get("det_size"), list) else [640, 640]
        return {
            "operation_mode": operation_mode,
            "selection_mode": selection_mode,
            "include_hidden_persons": bool(source.get("include_hidden_persons")),
            "min_faces_per_person": max(2, int(source.get("min_faces_per_person") or 3)),
            "exclude_outliers": bool(source.get("exclude_outliers", True)),
            "rebuild_all": bool(source.get("rebuild_all")),
            "changed_since_days": max(0, int(source.get("changed_since_days") or 0)),
            "safe_score": max(0.0, min(1.0, float(source.get("safe_score", 0.55)))),
            "review_score": max(0.0, min(1.0, float(source.get("review_score", 0.45)))),
            "min_margin": max(0.0, min(1.0, float(source.get("min_margin", 0.08)))),
            "outlier_similarity_threshold": max(0.0, min(1.0, float(source.get("outlier_similarity_threshold", 0.35)))),
            "min_face_iou": max(0.0, min(1.0, float(source.get("min_face_iou", 0.35)))),
            "det_size": [max(64, int(det_size[0])), max(64, int(det_size[1]))],
            "det_thresh": max(0.0, min(1.0, float(source.get("det_thresh", 0.5)))),
            "max_num": max(0, int(source.get("max_num") or 0)),
            "min_width_ratio": max(0.0, float(source.get("min_width_ratio", 0.015))),
            "min_height_ratio": max(0.0, float(source.get("min_height_ratio", 0.015))),
            "resume_existing": bool(source.get("resume_existing", False)),
            "max_profile_reference_faces_per_person": max(0, int(source.get("max_profile_reference_faces_per_person") or 50)),
        }

    def start(self, *, user_key: str, cookies: Dict[str, str], base_url: str, action: str, options: Any) -> Dict[str, Any]:
        normalized_action = str(action or "").strip().lower()
        normalized = self.normalize_options(options)
        if normalized_action not in self.ACTIONS:
            raise ValueError("unsupported_recognition_action")
        if normalized["operation_mode"] == "findings" and normalized_action != self.ACTION_BUILD:
            return self.sync_review_progress(user_key=user_key, action=normalized_action, operation_mode="findings")
        if normalized_action != self.ACTION_BUILD and not normalized.get("resume_existing"):
            self._clear_active_findings(user_key=user_key, action=normalized_action)
        operation_id = f"cleanup-{normalized_action}-{uuid4().hex}"
        self._set_progress(
            user_key, normalized_action, normalized,
            running=True, finished=False, operation_id=operation_id,
            stop_requested=False,
            phase="preparing", message_key="cleanup:recognition_preparing",
            message="Preparing face recognition.",
        )
        worker = Thread(
            target=self._run,
            kwargs={"user_key": user_key, "cookies": dict(cookies), "base_url": base_url, "action": normalized_action, "options": normalized},
            daemon=True,
        )
        self.backend.runtime_state.values("cleanup_threads")[self.backend._cleanupStateKey(user_key, normalized_action)] = worker
        worker.start()
        return self.backend.getCleanupProgress(user_key, normalized_action)

    def _run(self, *, user_key: str, cookies: Dict[str, str], base_url: str, action: str, options: Dict[str, Any]) -> None:
        failed = False
        try:
            if action == self.ACTION_BUILD:
                self._build_profiles(user_key=user_key, cookies=cookies, base_url=base_url, options=options)
            elif action == self.ACTION_OUTLIERS:
                self._build_outliers(user_key=user_key, options=options)
            elif action == self.ACTION_ASSIGNMENT:
                self._build_assignment_suggestions(user_key=user_key, cookies=cookies, base_url=base_url, options=options)
            else:
                self._build_suggestions(user_key=user_key, cookies=cookies, base_url=base_url, options=options)
        except Exception as exc:
            failed = True
            self._debug_log(
                "recognition_worker_failed",
                action=action,
                error_type=type(exc).__name__,
                error=str(exc),
            )
            self._set_progress(
                user_key, action, options, running=False, finished=True, phase="failed",
                message_key="cleanup:recognition_failed", message=f"Face recognition failed: {type(exc).__name__}: {exc}",
                errors_count=1,
            )
        finally:
            state_key = self.backend._cleanupStateKey(user_key, action) if hasattr(self.backend, "_cleanupStateKey") else ""
            try:
                if state_key:
                    self.backend.runtime_state.values("cleanup_threads").pop(state_key, None)
            except Exception:
                pass
            self._debug_log(
                "recognition_worker_finished",
                action=action,
                failed=failed,
                state_key=state_key,
            )

    def _debug_log(self, event: str, **fields: Any) -> None:
        debug_log = getattr(self.backend, "_debugLog", None)
        if callable(debug_log):
            debug_log(event, **fields)

    @staticmethod
    def _debug_options(options: Dict[str, Any]) -> Dict[str, Any]:
        keys = (
            "operation_mode", "selection_mode", "include_hidden_persons", "min_faces_per_person",
            "exclude_outliers", "rebuild_all", "changed_since_days", "safe_score", "review_score",
            "min_margin", "outlier_similarity_threshold", "min_face_iou", "det_size", "det_thresh",
            "max_num", "min_width_ratio", "min_height_ratio", "resume_existing", "max_profile_reference_faces_per_person",
        )
        return {key: options.get(key) for key in keys if key in options}

    def _should_stop(self, user_key: str, action: str) -> bool:
        try:
            return bool(self.backend._shouldStopCleanup(user_key, action))
        except Exception:
            return False

    def _prepared_embedder(self, options: Dict[str, Any]) -> InsightFaceEmbedder:
        key = (
            self.backend._configuredInsightFaceModelName(),
            str(self.backend._configuredInsightFaceModelRoot()),
            tuple(options["det_size"]), options["det_thresh"], options["max_num"],
            options["min_width_ratio"], options["min_height_ratio"],
            self._recognition_image_max_edge(),
        )
        if self._embedder is not None and self._embedder_key == key:
            self._debug_log(
                "recognition_embedder_reused",
                model_name=key[0],
                model_root=key[1],
                det_size=list(key[2]),
                det_thresh=key[3],
                max_num=key[4],
            )
            return self._embedder
        self._debug_log(
            "recognition_embedder_prepare_start",
            model_name=key[0],
            model_root=key[1],
            det_size=list(key[2]),
            det_thresh=key[3],
            max_num=key[4],
            min_width_ratio=key[5],
            min_height_ratio=key[6],
        )
        embedder = InsightFaceEmbedder(
            model_name=key[0], model_root=self.backend._configuredInsightFaceModelRoot(),
            det_size=key[2], det_thresh=key[3], max_num=key[4],
            min_width_ratio=key[5], min_height_ratio=key[6],
            max_image_edge=self._recognition_image_max_edge(),
        )
        embedder.prepare()
        self._embedder = embedder
        self._embedder_key = key
        self._debug_log(
            "recognition_embedder_prepare_finished",
            model_name=key[0],
            model_root=key[1],
            det_size=list(key[2]),
            det_thresh=key[3],
            max_num=key[4],
        )
        return embedder

    def _model_key(self, options: Dict[str, Any]) -> str:
        return f"{self.backend._configuredInsightFaceModelName()}:{options['det_size'][0]}x{options['det_size'][1]}:det{options['det_thresh']}"

    def _profile_state_key(self, options: Dict[str, Any]) -> str:
        return self._model_key(options).replace(":", "_").replace(".", "_")

    def _recognition_image_max_edge(self) -> int:
        config_service = getattr(self.backend, "config", None)
        try:
            config = config_service.readMergedConfig() if config_service is not None else {}
            files = config.get("files", {}) if isinstance(config.get("files"), dict) else {}
            return max(0, min(20000, int(files.get("RECOGNITION_IMAGE_MAX_EDGE", 4096))))
        except Exception:
            return 4096

    def profiles(self, options: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        normalized = self.normalize_options(options)
        return self.backend.file_analysis.readRuntimeState(self.PROFILE_STATE_TYPE, self._profile_state_key(normalized))

    def _active_key(self, *, user_key: str, action: str) -> str:
        return f"{str(user_key or '').strip() or 'default'}:{str(action or '').strip().lower()}"

    def _read_active_findings(self, *, user_key: str, action: str) -> Dict[str, Any]:
        with self._active_findings_lock:
            current = self._active_findings.get(self._active_key(user_key=user_key, action=action), {})
            return dict(current) if isinstance(current, dict) else {}

    def _write_active_findings(self, *, user_key: str, action: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        current = dict(payload) if isinstance(payload, dict) else {}
        with self._active_findings_lock:
            self._active_findings[self._active_key(user_key=user_key, action=action)] = current
        return dict(current)

    def _clear_active_findings(self, *, user_key: str, action: str) -> None:
        with self._active_findings_lock:
            self._active_findings.pop(self._active_key(user_key=user_key, action=action), None)

    def findings(self, action: str, *, user_key: str = "", operation_mode: str = "") -> Dict[str, Any]:
        mode = str(operation_mode or "").strip().lower()
        if mode == "immediate":
            return self._read_active_findings(user_key=user_key, action=action)
        finding_type = self._finding_type(action)
        findings = self.backend.file_analysis.readCheckFindings(finding_type)
        if mode in {"findings", "save_only"}:
            return findings if isinstance(findings, dict) else {}
        active = self._read_active_findings(user_key=user_key, action=action)
        return active or (findings if isinstance(findings, dict) else {})

    def _finding_type(self, action: str) -> str:
        if action == self.ACTION_OUTLIERS:
            return self.FINDING_OUTLIERS
        if action == self.ACTION_ASSIGNMENT:
            return self.FINDING_ASSIGNMENTS
        return self.FINDING_SUGGESTIONS

    def _item_path(self, *, user_key: str, cookies: Dict[str, str], base_url: str, shared_folder: str, item: Dict[str, Any], folder_cache: Dict[int, str]) -> str:
        try:
            folder_id = int(item.get("folder_id"))
        except (TypeError, ValueError):
            return ""
        filename = str(item.get("filename") or "").strip()
        if not filename:
            return ""
        if folder_id not in folder_cache:
            payload = self.backend.photos.getFotoTeamFolder(user_key=user_key, cookies=cookies, base_url=base_url, id_folder=folder_id)
            folder = payload.get("folder") if isinstance(payload.get("folder"), dict) else payload
            if not isinstance(folder, dict):
                folder = {}
            folder_cache[folder_id] = str(folder.get("name") or "")
        folder_name = folder_cache.get(folder_id, "")
        return self.backend._buildPhotoImagePath(shared_folder, folder_name, filename) if folder_name else ""

    def _record_reference_image_missing(self, *, person: Dict[str, Any], item: Dict[str, Any], image_path: str) -> None:
        issue = {
            "person_id": person.get("id"),
            "person_name": str(person.get("name") or ""),
            "image_id": item.get("id"),
            "folder_id": item.get("folder_id"),
            "filename": item.get("filename"),
            "image_path": image_path,
            "quality": "image_missing",
            "reason": "reference_image_not_found",
        }
        self._image_quality_issues.append(issue)
        if len([entry for entry in self._image_quality_issues if entry.get("quality") == "image_missing"]) <= 20:
            debug_log = getattr(self.backend, "_debugLog", None)
            if callable(debug_log):
                debug_log("recognition_reference_image_missing", **issue)

    def _extract_reference_preview(self, image_path: str) -> Tuple[Optional[bytes], str]:
        decoder = getattr(self.backend, "image_decoder", None)
        if decoder is not None:
            try:
                decoded = decoder.decode_to_jpeg(image_path)
            except Exception as decode_error:
                self._debug_log(
                    "recognition_image_decoder_failed",
                    image_path=image_path,
                    source="image_decoder",
                    error=f"{type(decode_error).__name__}: {decode_error}",
                )
            else:
                if getattr(decoded, "success", False) and getattr(decoded, "image_bytes", b""):
                    return decoded.image_bytes, str(getattr(decoded, "source", "") or "image_decoder")
                error = str(getattr(decoded, "error", "") or "")
                if error and error not in {"image_decoder_extension_not_enabled", "image_decoder_disabled"}:
                    self._debug_log(
                        "recognition_image_decoder_failed",
                        image_path=image_path,
                        source=str(getattr(decoded, "source", "") or "image_decoder"),
                        error=error,
                    )
        try:
            preview = self.backend.files.extractEmbeddedJpegPreview(image_path)
        except Exception as preview_extract_error:
            preview = None
            self._debug_log(
                "recognition_image_preview_extract_failed",
                image_path=image_path,
                source="native",
                error=f"{type(preview_extract_error).__name__}: {preview_extract_error}",
            )
        if preview:
            return preview, "native"

        exiftool = getattr(self.backend, "exiftool_handler", None)
        if exiftool is None:
            return None, ""
        try:
            if hasattr(exiftool, "isEnabled") and not exiftool.isEnabled():
                return None, ""
            if hasattr(exiftool, "isAvailable") and not exiftool.isAvailable():
                return None, ""
            preview = exiftool.extractEmbeddedJpegPreview(image_path)
        except Exception as preview_extract_error:
            self._debug_log(
                "recognition_image_preview_extract_failed",
                image_path=image_path,
                source="exiftool",
                error=f"{type(preview_extract_error).__name__}: {preview_extract_error}",
            )
            return None, ""
        if preview:
            return preview, "exiftool"
        return None, ""

    def _person_references(self, *, user_key: str, cookies: Dict[str, str], base_url: str, shared_folder: str, person: Dict[str, Any], embedder: InsightFaceEmbedder, options: Dict[str, Any], folder_cache: Dict[int, str], progress_context: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        context = dict(progress_context) if isinstance(progress_context, dict) else {}
        action = str(context.get("action") or self.ACTION_BUILD)
        try:
            person_id = int(person.get("id"))
        except (AttributeError, TypeError, ValueError):
            self._debug_log(
                "recognition_person_skipped",
                reason="invalid_person_id",
                raw_person_id=(person or {}).get("id") if isinstance(person, dict) else None,
                person_name=str((person or {}).get("name") or "") if isinstance(person, dict) else "",
            )
            return []
        references: List[Dict[str, Any]] = []
        faces_scanned = 0
        invalid_items = 0
        unreadable_images_before = len([entry for entry in self._image_quality_issues if entry.get("quality") == "image_unreadable"])
        missing_images_before = len([entry for entry in self._image_quality_issues if entry.get("quality") == "image_missing"])
        items = self.backend._listAllPhotoItemsForPerson(user_key=user_key, cookies=cookies, base_url=base_url, person_id=person_id)
        if not isinstance(items, list):
            items = list(items)
        self._debug_log(
            "recognition_person_reference_items_loaded",
            person_id=person_id,
            person_name=str(person.get("name") or ""),
            items_total=len(items),
        )
        resume_after_image_id = 0
        try:
            resume_after_image_id = int(context.get("resume_after_image_id") or 0)
        except (TypeError, ValueError):
            resume_after_image_id = 0
        resume_after_image_seen = not bool(resume_after_image_id)
        reference_limit = int(options.get("max_profile_reference_faces_per_person") or 0) if str(context.get("action") or "") == self.ACTION_BUILD else 0
        reference_limit_reached = False
        for item_index, item in enumerate(items):
            if reference_limit > 0 and len(references) >= reference_limit:
                reference_limit_reached = True
                self._debug_log(
                    "recognition_person_reference_limit_reached",
                    person_id=person_id,
                    person_name=str(person.get("name") or ""),
                    reference_limit=reference_limit,
                    references_count=len(references),
                    items_scanned=item_index,
                    items_total=len(items),
                )
                break
            if self._should_stop(user_key, action):
                self._debug_log(
                    "recognition_person_reference_scan_stop_requested",
                    action=action,
                    person_id=person_id,
                    person_name=str(person.get("name") or ""),
                    items_scanned=item_index,
                    items_total=len(items),
                    references_count=len(references),
                )
                break
            try:
                item_id = int(item.get("id"))
            except (AttributeError, TypeError, ValueError):
                invalid_items += 1
                if invalid_items <= 20:
                    self._debug_log(
                        "recognition_reference_item_skipped",
                        reason="invalid_item_id",
                        person_id=person_id,
                        person_name=str(person.get("name") or ""),
                        raw_item_id=(item or {}).get("id") if isinstance(item, dict) else None,
                        folder_id=(item or {}).get("folder_id") if isinstance(item, dict) else None,
                        filename=(item or {}).get("filename") if isinstance(item, dict) else None,
                    )
                continue
            if not resume_after_image_seen:
                if item_id == resume_after_image_id:
                    resume_after_image_seen = True
                continue
            image_path = self._item_path(user_key=user_key, cookies=cookies, base_url=base_url, shared_folder=shared_folder, item=item, folder_cache=folder_cache)
            if not image_path or not Path(image_path).is_file():
                self._record_reference_image_missing(person=person, item=item, image_path=image_path)
                continue
            if context:
                self._set_progress(
                    user_key, str(context.get("action") or self.ACTION_BUILD), options,
                    running=True, finished=False, phase=str(context.get("phase") or "reading_reference_images"),
                    message_key=str(context.get("message_key") or "cleanup:recognition_reading_reference_images"),
                    message=str(context.get("message") or "Reading recognition reference images."),
                    progress_kind=str(context.get("progress_kind") or "images"), images_scanned=item_index + 1, images_total=len(items),
                    persons_scanned=int(context.get("persons_scanned") or 0), persons_total=int(context.get("persons_total") or 0),
                    profiles_built=int(context.get("profiles_built") or 0), findings_count=int(context.get("findings_count") or 0),
                    faces_scanned=faces_scanned,
                    references_count=len(references),
                    **({"current_name": str(context.get("current_name") or "")} if str(context.get("current_name") or "") else {}),
                )
            if options["changed_since_days"] > 0:
                cutoff = datetime.now(timezone.utc) - timedelta(days=options["changed_since_days"])
                if datetime.fromtimestamp(Path(image_path).stat().st_mtime, timezone.utc) < cutoff:
                    continue
            if image_path not in self._image_embedding_cache:
                try:
                    self._image_embedding_cache[image_path] = embedder.detect_and_embed(Path(image_path))
                except Exception as direct_error:
                    preview, preview_source = self._extract_reference_preview(image_path)
                    if preview:
                        try:
                            self._image_embedding_cache[image_path] = embedder.detect_and_embed_bytes(preview)
                            self._debug_log(
                                "recognition_image_preview_fallback",
                                image_path=image_path,
                                source=preview_source,
                                direct_error=str(direct_error),
                                detected_faces=len(self._image_embedding_cache[image_path]),
                            )
                        except Exception as preview_error:
                            self._image_embedding_cache[image_path] = []
                            self._image_quality_issues.append({
                                "image_path": image_path,
                                "quality": "image_unreadable",
                                "reason": str(preview_error),
                            })
                            self._debug_log(
                                "recognition_image_skipped",
                                image_path=image_path,
                                direct_error=f"{type(direct_error).__name__}: {direct_error}",
                                preview_error=f"{type(preview_error).__name__}: {preview_error}",
                            )
                    else:
                        self._image_embedding_cache[image_path] = []
                        self._image_quality_issues.append({
                            "image_path": image_path,
                            "quality": "image_unreadable",
                            "reason": str(direct_error),
                        })
                        self._debug_log(
                            "recognition_image_skipped",
                            image_path=image_path,
                            direct_error=f"{type(direct_error).__name__}: {direct_error}",
                            preview_error="embedded_jpeg_preview_missing",
                        )
            image_embeddings = self._image_embedding_cache[image_path]
            image_faces = self.backend.photos.list_faceFotoTeamItems(user_key=user_key, cookies=cookies, base_url=base_url, id_item=item_id)
            if not isinstance(image_faces, list):
                image_faces = list(image_faces)
            for face in image_faces:
                if self._should_stop(user_key, action):
                    self._debug_log(
                        "recognition_person_reference_face_loop_stop_requested",
                        action=action,
                        person_id=person_id,
                        person_name=str(person.get("name") or ""),
                        item_id=item_id,
                        faces_scanned=faces_scanned,
                        references_count=len(references),
                    )
                    break
                faces_scanned += 1
                if context:
                    self._set_progress(
                        user_key, str(context.get("action") or self.ACTION_BUILD), options,
                        running=True, finished=False, phase=str(context.get("phase") or "reading_reference_images"),
                        message_key=str(context.get("message_key") or "cleanup:recognition_reading_reference_images"),
                        message=str(context.get("message") or "Reading recognition reference images."),
                        progress_kind=str(context.get("progress_kind") or "images"), images_scanned=item_index + 1, images_total=len(items),
                        persons_scanned=int(context.get("persons_scanned") or 0), persons_total=int(context.get("persons_total") or 0),
                        profiles_built=int(context.get("profiles_built") or 0), findings_count=int(context.get("findings_count") or 0),
                        faces_scanned=faces_scanned,
                        references_count=len(references),
                        **({"current_name": str(context.get("current_name") or "")} if str(context.get("current_name") or "") else {}),
                    )
                try:
                    face_person_id = int(face.get("person_id"))
                    face_id = int(face.get("face_id"))
                    bbox = to_bbox_dict(from_photos(face))
                except (TypeError, ValueError, KeyError):
                    continue
                if face_person_id != person_id:
                    continue
                if not image_embeddings:
                    continue
                matched = max(image_embeddings, key=lambda candidate: embedder._iou(bbox, candidate["bbox"]))
                match_iou = embedder._iou(bbox, matched["bbox"])
                if match_iou < options["min_face_iou"]:
                    continue
                references.append({
                    "face_id": face_id, "image_id": item_id, "image_path": image_path,
                    "bbox": bbox, "embedding": matched["embedding"], "iou": match_iou,
                })
                if context:
                    self._set_progress(
                        user_key, str(context.get("action") or self.ACTION_BUILD), options,
                        running=True, finished=False, phase=str(context.get("phase") or "reading_reference_images"),
                        message_key=str(context.get("message_key") or "cleanup:recognition_reading_reference_images"),
                        message=str(context.get("message") or "Reading recognition reference images."),
                        progress_kind=str(context.get("progress_kind") or "images"), images_scanned=item_index + 1, images_total=len(items),
                        persons_scanned=int(context.get("persons_scanned") or 0), persons_total=int(context.get("persons_total") or 0),
                        profiles_built=int(context.get("profiles_built") or 0), findings_count=int(context.get("findings_count") or 0),
                        faces_scanned=faces_scanned,
                        references_count=len(references),
                        **({"current_name": str(context.get("current_name") or "")} if str(context.get("current_name") or "") else {}),
                    )
        unreadable_images_after = len([entry for entry in self._image_quality_issues if entry.get("quality") == "image_unreadable"])
        missing_images_after = len([entry for entry in self._image_quality_issues if entry.get("quality") == "image_missing"])
        self._debug_log(
            "recognition_person_reference_scan_finished",
            person_id=person_id,
            person_name=str(person.get("name") or ""),
            items_total=len(items),
            invalid_items=invalid_items,
            faces_scanned=faces_scanned,
            references_count=len(references),
            unreadable_images=unreadable_images_after - unreadable_images_before,
            missing_images=missing_images_after - missing_images_before,
            reference_limit=reference_limit,
            reference_limit_reached=reference_limit_reached,
        )
        return references

    @staticmethod
    def _normalize_vector(values: List[float]) -> List[float]:
        magnitude = math.sqrt(sum(float(value) * float(value) for value in values))
        return [float(value) / magnitude for value in values] if magnitude > 0 else []

    @classmethod
    def _centroid(cls, embeddings: List[List[float]]) -> List[float]:
        if not embeddings:
            return []
        size = len(embeddings[0])
        return cls._normalize_vector([sum(vector[index] for vector in embeddings) / len(embeddings) for index in range(size)])

    @staticmethod
    def _similarity(left: List[float], right: List[float]) -> float:
        return sum(float(a) * float(b) for a, b in zip(left, right))

    @classmethod
    def _medoid_index(cls, embeddings: List[List[float]]) -> int:
        if len(embeddings) <= 1:
            return 0
        normalized = [cls._normalize_vector(vector) for vector in embeddings]
        scores = [sum(cls._similarity(current, other) for other in normalized) / len(normalized) for current in normalized]
        return max(range(len(scores)), key=lambda index: scores[index])

    def _persist_profiles_snapshot(
        self,
        *,
        options: Dict[str, Any],
        profiles: List[Dict[str, Any]],
        quality: List[Dict[str, Any]],
        event: str,
        persons_total: int,
        persons_scanned: int,
    ) -> None:
        payload = {
            "model_key": self._model_key(options),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "profiles": profiles,
        }
        quality_entries = list(quality) + list(self._image_quality_issues)
        state_written = self.backend.file_analysis.writeRuntimeState(self.PROFILE_STATE_TYPE, self._profile_state_key(options), payload)
        profiles_written = self.backend.file_analysis.writeCheckFindings(self.FINDING_PROFILES, {
            "finding_type": self.FINDING_PROFILES,
            "entries": [{key: value for key, value in profile.items() if key not in {"centroid_embedding", "references"}} for profile in profiles],
        })
        quality_written = self.backend.file_analysis.writeCheckFindings(self.FINDING_QUALITY, {
            "finding_type": self.FINDING_QUALITY,
            "entries": quality_entries,
        })
        self._debug_log(
            event,
            persons_total=persons_total,
            persons_scanned=persons_scanned,
            profiles_built=len(profiles),
            quality_count=len(quality_entries),
            state_written=bool(state_written),
            profiles_written=bool(profiles_written),
            quality_written=bool(quality_written),
            model_key=payload["model_key"],
        )

    @staticmethod
    def _profile_person_id(profile: Any) -> Optional[int]:
        try:
            value = profile.get("person_id")
            if value is None:
                value = profile.get("id")
            return int(value)
        except (AttributeError, TypeError, ValueError):
            return None

    def _existing_profile_payload(self, options: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        payload = self.profiles(options)
        profiles = payload.get("profiles") if isinstance(payload, dict) else []
        quality_payload = self.backend.file_analysis.readCheckFindings(self.FINDING_QUALITY)
        quality = quality_payload.get("entries") if isinstance(quality_payload, dict) else []
        if not isinstance(profiles, list):
            profiles = []
        if not isinstance(quality, list):
            quality = []
        return (
            [dict(profile) for profile in profiles if isinstance(profile, dict)],
            [dict(entry) for entry in quality if isinstance(entry, dict)],
        )

    def _build_profiles(self, *, user_key: str, cookies: Dict[str, str], base_url: str, options: Dict[str, Any]) -> None:
        self._image_embedding_cache = {}
        self._image_quality_issues = []
        self._debug_log(
            "recognition_profiles_build_start",
            model_key=self._model_key(options),
            profile_state_key=self._profile_state_key(options),
            options=self._debug_options(options),
        )
        self._set_progress(
            user_key, self.ACTION_BUILD, options, running=True, finished=False, phase="preparing_model",
            message_key="cleanup:recognition_preparing_model", message="Preparing InsightFace recognition model.",
        )
        embedder = self._prepared_embedder(options)
        shared_folder = self.backend.core.getSharedFolder(user_key=user_key, cookies=cookies, base_url=base_url, folder_name="photo")
        if not shared_folder:
            self._debug_log("recognition_profiles_shared_folder_missing", folder_name="photo")
            raise RuntimeError("shared_folder_not_found")
        self._debug_log("recognition_profiles_shared_folder_resolved", shared_folder=shared_folder)
        all_persons = self.backend.photos.listFotoTeamPersonKnown(
            user_key=user_key, cookies=cookies, base_url=base_url, show_more=True,
            show_hidden=options["include_hidden_persons"], additional=["thumbnail"],
        )
        existing_profiles: List[Dict[str, Any]] = []
        existing_quality: List[Dict[str, Any]] = []
        existing_person_ids = set()
        if not options["rebuild_all"]:
            existing_profiles, existing_quality = self._existing_profile_payload(options)
            existing_person_ids = {
                person_id for person_id in (self._profile_person_id(profile) for profile in existing_profiles)
                if person_id is not None
            }
        persons = [
            person for person in all_persons
            if options["rebuild_all"] or self._profile_person_id(person) not in existing_person_ids
        ]
        self._debug_log(
            "recognition_profiles_persons_loaded",
            persons_total=len(persons),
            persons_all_total=len(all_persons),
            existing_profiles_count=len(existing_profiles),
            skipped_existing_profiles_count=max(0, len(all_persons) - len(persons)),
            rebuild_all=options["rebuild_all"],
            include_hidden_persons=options["include_hidden_persons"],
        )
        self._set_progress(
            user_key, self.ACTION_BUILD, options, running=True, finished=False, phase="persons_loaded",
            message_key="cleanup:recognition_persons_loaded", message="Photos persons loaded.",
            persons_scanned=0, persons_total=len(persons),
        )
        profiles: List[Dict[str, Any]] = existing_profiles
        quality: List[Dict[str, Any]] = existing_quality
        outlier_findings = self.backend.file_analysis.readCheckFindings(self.FINDING_OUTLIERS)
        excluded_face_ids = set()
        if options["exclude_outliers"]:
            for entry in outlier_findings.get("entries", []):
                if not isinstance(entry, dict) or str(entry.get("review_state") or "") != "excluded":
                    continue
                try:
                    excluded_face_ids.add(int(entry.get("face_id")))
                except (TypeError, ValueError):
                    continue
        self._debug_log(
            "recognition_profiles_outlier_exclusions_loaded",
            exclude_outliers=options["exclude_outliers"],
            excluded_face_ids_count=len(excluded_face_ids),
        )
        folder_cache: Dict[int, str] = {}
        reference_options = {**options, "changed_since_days": 0}
        stopped = False
        for index, person in enumerate(persons):
            if self.backend._shouldStopCleanup(user_key, self.ACTION_BUILD):
                stopped = True
                self._debug_log(
                    "recognition_profiles_build_stop_requested",
                    persons_scanned=index,
                    persons_total=len(persons),
                    profiles_built=len(profiles),
                    quality_count=len(quality),
                )
                break
            references = self._person_references(
                user_key=user_key, cookies=cookies, base_url=base_url, shared_folder=shared_folder,
                person=person, embedder=embedder, options=reference_options, folder_cache=folder_cache,
                progress_context={
                    "action": self.ACTION_BUILD,
                    "phase": "reading_reference_images",
                    "message_key": "cleanup:recognition_reading_reference_images",
                    "message": "Reading recognition reference images.",
                    "progress_kind": "persons",
                    "persons_scanned": index,
                    "persons_total": len(persons),
                    "profiles_built": len(profiles),
                    "findings_count": len(quality),
                    "current_name": str(person.get("name") or ""),
                },
            )
            raw_reference_count = len(references)
            references = [reference for reference in references if int(reference.get("face_id") or 0) not in excluded_face_ids]
            embeddings = [entry["embedding"] for entry in references]
            person_id = int(person.get("id"))
            person_name = str(person.get("name") or "")
            if len(references) < options["min_faces_per_person"]:
                quality.append({"person_id": person_id, "person_name": person_name, "reference_count": len(references), "quality": "insufficient_references"})
                self._debug_log(
                    "recognition_profile_insufficient_references",
                    person_id=person_id,
                    person_name=person_name,
                    reference_count=len(references),
                    raw_reference_count=raw_reference_count,
                    min_faces_per_person=options["min_faces_per_person"],
                )
            if references:
                centroid = self._centroid(embeddings)
                medoid = references[self._medoid_index(embeddings)]
                intra_similarity = sum(self._similarity(embedding, centroid) for embedding in embeddings) / len(embeddings)
                profiles.append({
                    "person_id": person_id, "person_name": person_name, "profile_key": self._model_key(options),
                    "reference_count": len(references), "used_count": len(references), "quality": "good" if len(references) >= options["min_faces_per_person"] else "limited",
                    "intra_person_similarity": intra_similarity,
                    "centroid_embedding": centroid, "medoid": {key: medoid[key] for key in ("face_id", "image_id", "image_path", "bbox")},
                    "references": references,
                })
            self._debug_log(
                "recognition_profile_person_finished",
                person_id=person_id,
                person_name=person_name,
                raw_reference_count=raw_reference_count,
                excluded_reference_count=raw_reference_count - len(references),
                reference_count=len(references),
                profile_created=bool(references),
                quality="good" if len(references) >= options["min_faces_per_person"] else ("limited" if references else "insufficient_references"),
                profiles_built=len(profiles),
                quality_count=len(quality),
            )
            self._set_progress(
                user_key, self.ACTION_BUILD, options, running=True, finished=False, phase="building_profiles",
                message_key="cleanup:recognition_building_profiles", message="Building person profiles.",
                persons_scanned=index + 1, persons_total=len(persons), profiles_built=len(profiles), findings_count=len(quality),
            )
            self._persist_profiles_snapshot(
                options=options,
                profiles=profiles,
                quality=quality,
                event="recognition_profiles_checkpoint_persisted",
                persons_total=len(persons),
                persons_scanned=index + 1,
            )
        self._persist_profiles_snapshot(
            options=options,
            profiles=profiles,
            quality=quality,
            event="recognition_profiles_persisted",
            persons_total=len(persons),
            persons_scanned=len(persons),
        )
        quality_count = len(quality) + len(self._image_quality_issues)
        if not profiles:
            self._debug_log(
                "recognition_profiles_empty",
                persons_total=len(persons),
                quality_count=quality_count,
                image_quality_issues_count=len(self._image_quality_issues),
                stopped=stopped,
            )
        self._set_progress(
            user_key, self.ACTION_BUILD, options, running=False, finished=True, phase="finished",
            message_key="cleanup:recognition_profiles_finished", message="Person profiles built.",
            persons_scanned=len(persons), persons_total=len(persons), profiles_built=len(profiles), findings_count=quality_count,
        )

    def _build_outliers(self, *, user_key: str, options: Dict[str, Any]) -> None:
        profiles = self.profiles(options).get("profiles", [])
        previous = self.findings(
            self.ACTION_OUTLIERS,
            user_key=user_key,
            operation_mode="immediate" if options.get("resume_existing") else ("save_only" if options["operation_mode"] == "save_only" else ""),
        )
        previous_entries = previous.get("entries") if isinstance(previous.get("entries"), list) else []
        entries: List[Dict[str, Any]] = list(previous_entries) if options.get("resume_existing") and options["operation_mode"] == "immediate" else []
        resolved_face_ids = set()
        for entry in previous_entries:
            if entry.get("face_id") is None or str(entry.get("selection_state") or "") == "review":
                continue
            try:
                resolved_face_ids.add(int(entry.get("face_id")))
            except (TypeError, ValueError):
                continue
        for profile in profiles if isinstance(profiles, list) else []:
            centroid = profile.get("centroid_embedding") or []
            medoid = profile.get("medoid") if isinstance(profile.get("medoid"), dict) else {}
            for reference in profile.get("references", []):
                if int(reference.get("face_id") or 0) in resolved_face_ids:
                    continue
                similarity = self._similarity(reference.get("embedding") or [], centroid)
                if similarity >= options["outlier_similarity_threshold"]:
                    continue
                other_scores = sorted(
                    [
                        (self._similarity(reference.get("embedding") or [], other.get("centroid_embedding") or []), other)
                        for other in profiles
                        if other.get("person_id") != profile.get("person_id")
                    ],
                    key=lambda item: item[0],
                    reverse=True,
                )
                nearest_other_score, nearest_other = other_scores[0] if other_scores else (0.0, {})
                entries.append({
                    "outlier_id": f"out-{reference.get('face_id')}", "image_path": reference.get("image_path"),
                    "person_id": profile.get("person_id"), "person_name": profile.get("person_name"),
                    "face_id": reference.get("face_id"), "image_id": reference.get("image_id"), "bbox": reference.get("bbox"),
                    "profile_image_path": medoid.get("image_path"), "profile_bbox": medoid.get("bbox"),
                    "similarity_to_centroid": similarity,
                    "review_state": "excluded" if options["selection_mode"] == "exclude_confirmed" else "suspected",
                    "average_similarity": similarity,
                    "nearest_other_person_id": nearest_other.get("person_id"),
                    "nearest_other_person_name": nearest_other.get("person_name"),
                    "nearest_other_person_score": nearest_other_score,
                    "outlier_score": max(0.0, 1.0 - similarity),
                    "reason": "nearest_other_person_higher" if nearest_other_score > similarity else "low_centroid_similarity",
                    "selection_state": "selected" if options["selection_mode"] == "exclude_confirmed" else "review",
                    "write_state": "internal_only",
                })
                if options["operation_mode"] == "immediate" and entries[-1]["selection_state"] == "review":
                    self._write_findings(self.FINDING_OUTLIERS, self.ACTION_OUTLIERS, options, entries, user_key=user_key)
                    self._finish_review_scan(user_key, self.ACTION_OUTLIERS, options, entries)
                    return
        self._write_findings(self.FINDING_OUTLIERS, self.ACTION_OUTLIERS, options, entries, user_key=user_key)
        if options["selection_mode"] == "exclude_confirmed":
            self._apply_exclusions_to_profiles(options, [entry.get("face_id") for entry in entries])
        self._finish_review_scan(user_key, self.ACTION_OUTLIERS, options, entries)

    def _build_suggestions(self, *, user_key: str, cookies: Dict[str, str], base_url: str, options: Dict[str, Any]) -> None:
        self._image_embedding_cache = {}
        profiles = [
            profile for profile in self.profiles(options).get("profiles", [])
            if int(profile.get("used_count") or 0) >= options["min_faces_per_person"]
        ]
        if not profiles:
            self._set_progress(
                user_key, self.ACTION_SUGGEST, options, running=False, finished=True, phase="needs_profiles",
                message_key="cleanup:recognition_profiles_missing",
                message="Person profiles are missing. Build person profiles before analyzing unknown faces.",
                profiles_built=0, findings_count=0,
            )
            return
        embedder = self._prepared_embedder(options)
        shared_folder = self.backend.core.getSharedFolder(user_key=user_key, cookies=cookies, base_url=base_url, folder_name="photo")
        if not shared_folder:
            raise RuntimeError("shared_folder_not_found")
        unknown = self.backend.photos.listFotoTeamPersonUnknown(user_key=user_key, cookies=cookies, base_url=base_url, show_more=True, show_hidden=options["include_hidden_persons"])
        folder_cache: Dict[int, str] = {}
        previous = self.findings(
            self.ACTION_SUGGEST,
            user_key=user_key,
            operation_mode="immediate" if options.get("resume_existing") else ("save_only" if options["operation_mode"] == "save_only" else ""),
        )
        previous_entries = previous.get("entries") if isinstance(previous.get("entries"), list) else []
        entries: List[Dict[str, Any]] = list(previous_entries) if options.get("resume_existing") and options["operation_mode"] == "immediate" else []
        resolved_face_ids = set()
        for entry in previous_entries:
            if entry.get("unknown_face_id") is None or str(entry.get("selection_state") or "") == "review":
                continue
            try:
                resolved_face_ids.add(int(entry.get("unknown_face_id")))
            except (TypeError, ValueError):
                continue
        self._set_progress(
            user_key, self.ACTION_SUGGEST, options, running=True, finished=False, phase="unknown_loaded",
            message_key="cleanup:recognition_unknown_loaded", message="Unknown Photos faces loaded.",
            persons_scanned=0, persons_total=len(unknown), findings_count=len(entries),
        )
        for index, person in enumerate(unknown):
            references = self._person_references(
                user_key=user_key, cookies=cookies, base_url=base_url, shared_folder=shared_folder,
                person=person, embedder=embedder, options=options, folder_cache=folder_cache,
                progress_context={
                    "action": self.ACTION_SUGGEST,
                    "phase": "reading_unknown_images",
                    "message_key": "cleanup:recognition_reading_unknown_images",
                    "message": "Reading unknown face images.",
                    "persons_scanned": index,
                    "persons_total": len(unknown),
                    "findings_count": len(entries),
                },
            )
            for reference in references:
                if int(reference.get("face_id") or 0) in resolved_face_ids:
                    continue
                scored = sorted(
                    [(self._similarity(reference["embedding"], profile.get("centroid_embedding") or []), profile) for profile in profiles],
                    key=lambda item: item[0], reverse=True,
                )
                if not scored:
                    continue
                best_score, best = scored[0]
                second_score, second = scored[1] if len(scored) > 1 else (0.0, {})
                margin = best_score - second_score
                decision = "reject"
                if best_score >= options["safe_score"] and margin >= options["min_margin"]:
                    decision = "accept"
                elif best_score >= options["review_score"]:
                    decision = "review" if margin >= options["min_margin"] else "ambiguous"
                entries.append({
                    "suggestion_id": f"rec-{reference.get('face_id')}", "image_path": reference.get("image_path"),
                    "image_id": reference.get("image_id"), "unknown_face_id": reference.get("face_id"), "bbox": reference.get("bbox"),
                    "best_person_id": best.get("person_id"), "best_person_name": best.get("person_name"), "best_score": best_score,
                    "profile_image_path": (best.get("medoid") or {}).get("image_path"), "profile_bbox": (best.get("medoid") or {}).get("bbox"),
                    "second_person_id": second.get("person_id"), "second_person_name": second.get("person_name"), "second_score": second_score,
                    "score_margin": margin, "decision": decision,
                    "selection_state": "selected" if options["selection_mode"] == "safe_only" and decision == "accept" else "review",
                    "write_state": "pending", "profile_key": self._model_key(options),
                })
                if options["operation_mode"] == "immediate" and entries[-1]["selection_state"] == "review":
                    self._write_findings(self.FINDING_SUGGESTIONS, self.ACTION_SUGGEST, options, entries, user_key=user_key)
                    self._finish_review_scan(user_key, self.ACTION_SUGGEST, options, entries)
                    return
            self._set_progress(
                user_key, self.ACTION_SUGGEST, options, running=True, finished=False, phase="building_suggestions",
                message_key="cleanup:recognition_building_suggestions", message="Building recognition suggestions.",
                persons_scanned=index + 1, persons_total=len(unknown), findings_count=len(entries),
            )
        self._write_findings(self.FINDING_SUGGESTIONS, self.ACTION_SUGGEST, options, entries, user_key=user_key)
        self._finish_review_scan(user_key, self.ACTION_SUGGEST, options, entries)

    def _build_assignment_suggestions(self, *, user_key: str, cookies: Dict[str, str], base_url: str, options: Dict[str, Any]) -> None:
        self._image_embedding_cache = {}
        profiles = [
            profile for profile in self.profiles(options).get("profiles", [])
            if int(profile.get("used_count") or 0) >= options["min_faces_per_person"]
        ]
        if not profiles:
            self._set_progress(
                user_key, self.ACTION_ASSIGNMENT, options, running=False, finished=True, phase="needs_profiles",
                message_key="cleanup:recognition_profiles_missing",
                message="Person profiles are missing. Build person profiles before checking person assignments.",
                profiles_built=0, findings_count=0,
            )
            return
        embedder = self._prepared_embedder(options)
        shared_folder = self.backend.core.getSharedFolder(user_key=user_key, cookies=cookies, base_url=base_url, folder_name="photo")
        if not shared_folder:
            raise RuntimeError("shared_folder_not_found")
        persons = self.backend.photos.listFotoTeamPersonKnown(
            user_key=user_key, cookies=cookies, base_url=base_url, show_more=True,
            show_hidden=options["include_hidden_persons"], additional=["thumbnail"],
        )
        folder_cache: Dict[int, str] = {}
        previous = self.findings(
            self.ACTION_ASSIGNMENT,
            user_key=user_key,
            operation_mode="immediate" if options.get("resume_existing") else ("save_only" if options["operation_mode"] == "save_only" else ""),
        )
        previous_entries = previous.get("entries") if isinstance(previous.get("entries"), list) else []
        entries: List[Dict[str, Any]] = list(previous_entries) if options.get("resume_existing") and options["operation_mode"] == "immediate" else []
        resolved_face_ids = set()
        resume_person_id: Optional[int] = None
        resume_after_image_id = 0
        for entry in previous_entries:
            if options.get("resume_existing") and options["operation_mode"] == "immediate":
                try:
                    entry_person_id = int(entry.get("current_person_id") or 0)
                except (TypeError, ValueError):
                    entry_person_id = 0
                if entry_person_id:
                    resume_person_id = entry_person_id
                    try:
                        resume_after_image_id = int(entry.get("image_id") or 0)
                    except (TypeError, ValueError):
                        resume_after_image_id = 0
            if entry.get("current_face_id") is None or str(entry.get("selection_state") or "") == "review":
                continue
            try:
                resolved_face_ids.add(int(entry.get("current_face_id")))
            except (TypeError, ValueError):
                continue
        persons_to_scan = list(persons if isinstance(persons, list) else [])
        if resume_person_id:
            resume_start_index = next((
                index for index, person in enumerate(persons_to_scan)
                if self._profile_person_id(person) == resume_person_id
            ), 0)
            if resume_start_index:
                self._debug_log(
                    "recognition_assignment_resume_person",
                    resume_person_id=resume_person_id,
                    resume_after_image_id=resume_after_image_id,
                    skipped_persons=resume_start_index,
                    persons_total=len(persons_to_scan),
                    previous_entries_count=len(previous_entries),
                )
                persons_to_scan = persons_to_scan[resume_start_index:]
        self._set_progress(
            user_key, self.ACTION_ASSIGNMENT, options, running=True, finished=False, phase="persons_loaded",
            message_key="cleanup:recognition_persons_loaded", message="Photos persons loaded.",
            persons_scanned=0, persons_total=len(persons_to_scan), findings_count=len(entries),
        )
        for index, person in enumerate(persons_to_scan):
            if self._should_stop(user_key, self.ACTION_ASSIGNMENT):
                self._finish_stopped_scan(user_key, self.ACTION_ASSIGNMENT, options, entries)
                return
            try:
                current_person_id = int(person.get("id"))
            except (AttributeError, TypeError, ValueError):
                continue
            current_person_name = str(person.get("name") or "")
            references = self._person_references(
                user_key=user_key, cookies=cookies, base_url=base_url, shared_folder=shared_folder,
                person=person, embedder=embedder, options=options, folder_cache=folder_cache,
                progress_context={
                    "action": self.ACTION_ASSIGNMENT,
                    "phase": "reading_assigned_images",
                    "message_key": "cleanup:recognition_reading_assigned_images",
                    "message": "Reading assigned Photos face images.",
                    "persons_scanned": index,
                    "persons_total": len(persons_to_scan),
                    "findings_count": len(entries),
                    "current_name": current_person_name,
                    **({"resume_after_image_id": resume_after_image_id} if resume_after_image_id and current_person_id == resume_person_id else {}),
                },
            )
            if self._should_stop(user_key, self.ACTION_ASSIGNMENT):
                self._finish_stopped_scan(user_key, self.ACTION_ASSIGNMENT, options, entries)
                return
            for reference in references:
                if self._should_stop(user_key, self.ACTION_ASSIGNMENT):
                    self._finish_stopped_scan(user_key, self.ACTION_ASSIGNMENT, options, entries)
                    return
                try:
                    face_id = int(reference.get("face_id") or 0)
                except (TypeError, ValueError):
                    face_id = 0
                if not face_id or face_id in resolved_face_ids:
                    continue
                scored = sorted(
                    [(self._similarity(reference["embedding"], profile.get("centroid_embedding") or []), profile) for profile in profiles],
                    key=lambda item: item[0], reverse=True,
                )
                if not scored:
                    continue
                best_score, best = scored[0]
                best_person_id = int(best.get("person_id") or 0)
                if best_person_id == current_person_id:
                    continue
                second_score, second = scored[1] if len(scored) > 1 else (0.0, {})
                margin = best_score - second_score
                if best_score < options["review_score"] or margin < options["min_margin"]:
                    continue
                decision = "accept" if best_score >= options["safe_score"] else "review"
                entries.append({
                    "suggestion_id": f"assign-{face_id}", "image_path": reference.get("image_path"),
                    "image_id": reference.get("image_id"), "current_face_id": face_id, "unknown_face_id": face_id,
                    "bbox": reference.get("bbox"),
                    "current_person_id": current_person_id, "current_person_name": current_person_name,
                    "best_person_id": best_person_id, "best_person_name": best.get("person_name"), "best_score": best_score,
                    "profile_image_path": (best.get("medoid") or {}).get("image_path"), "profile_bbox": (best.get("medoid") or {}).get("bbox"),
                    "second_person_id": second.get("person_id"), "second_person_name": second.get("person_name"), "second_score": second_score,
                    "score_margin": margin, "decision": decision,
                    "selection_state": "selected" if options["selection_mode"] == "safe_only" and decision == "accept" else "review",
                    "write_state": "pending", "profile_key": self._model_key(options),
                })
                if options["operation_mode"] == "immediate" and entries[-1]["selection_state"] == "review":
                    self._write_findings(self.FINDING_ASSIGNMENTS, self.ACTION_ASSIGNMENT, options, entries, user_key=user_key)
                    self._finish_review_scan(user_key, self.ACTION_ASSIGNMENT, options, entries)
                    return
            self._set_progress(
                user_key, self.ACTION_ASSIGNMENT, options, running=True, finished=False, phase="building_assignment_suggestions",
                message_key="cleanup:recognition_building_assignment_suggestions",
                message="Building person assignment suggestions.",
                persons_scanned=index + 1, persons_total=len(persons_to_scan), findings_count=len(entries),
            )
        self._write_findings(self.FINDING_ASSIGNMENTS, self.ACTION_ASSIGNMENT, options, entries, user_key=user_key)
        self._finish_review_scan(user_key, self.ACTION_ASSIGNMENT, options, entries)

    def _write_findings(self, finding_type: str, action: str, options: Dict[str, Any], entries: List[Dict[str, Any]], *, user_key: str = "") -> None:
        payload = {
            "finding_type": finding_type, "action": action, "mode": options["operation_mode"],
            "generated_at": datetime.now(timezone.utc).isoformat(), "options": options, "entries": entries,
        }
        if options["operation_mode"] == "immediate":
            self._write_active_findings(user_key=user_key, action=action, payload=payload)
        elif options["operation_mode"] == "save_only":
            self.backend.file_analysis.writeCheckFindings(finding_type, payload)

    @staticmethod
    def _open_entries(entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return [entry for entry in entries if str(entry.get("selection_state") or "review") == "review" and str(entry.get("write_state") or "pending") in {"pending", "internal_only"}]

    def _finish_stopped_scan(self, user_key: str, action: str, options: Dict[str, Any], entries: List[Dict[str, Any]]) -> None:
        if entries:
            self._write_findings(self._finding_type(action), action, options, entries, user_key=user_key)
        self._set_progress(
            user_key, action, options, running=False, finished=True, stop_requested=True, phase="stopped",
            message_key="cleanup:progress_stopped", message="Cleanup stopped.",
            findings_count=len(entries),
        )

    def _finish_review_scan(self, user_key: str, action: str, options: Dict[str, Any], entries: List[Dict[str, Any]]) -> None:
        open_entries = self._open_entries(entries)
        review_required = options["operation_mode"] == "immediate" and bool(open_entries)
        self._set_progress(
            user_key, action, options, running=False, finished=True, phase="review_required" if review_required else "finished",
            message_key="cleanup:recognition_review_required" if review_required else "cleanup:recognition_scan_finished",
            message="Manual review required for the next recognition finding." if review_required else "Recognition scan finished.",
            findings_count=len(entries),
        )

    def update_review(self, *, action: str, item_id: str, decision: str, user_key: str = "", operation_mode: str = "findings") -> Dict[str, Any]:
        finding_type = self._finding_type(action)
        mode = str(operation_mode or "findings").strip().lower()
        payload = self.findings(action, user_key=user_key, operation_mode=mode)
        entries = payload.get("entries") if isinstance(payload.get("entries"), list) else []
        updated = False
        for entry in entries:
            current_id = entry.get("outlier_id") if action == self.ACTION_OUTLIERS else entry.get("suggestion_id")
            if str(current_id or "") != str(item_id or ""):
                continue
            if action == self.ACTION_OUTLIERS:
                entry["review_state"] = "ignored" if decision == "skipped" else decision
                entry["selection_state"] = "selected" if decision == "excluded" else "skipped"
            else:
                entry["selection_state"] = "selected" if decision == "selected" else "skipped"
                if decision == "skipped":
                    entry["write_state"] = "skipped"
            updated = True
            break
        payload["entries"] = entries
        if mode == "immediate":
            self._write_active_findings(user_key=user_key, action=action, payload=payload)
        else:
            self.backend.file_analysis.writeCheckFindings(finding_type, payload)
        if action == self.ACTION_OUTLIERS and decision == "excluded":
            selected = next((entry for entry in entries if str(entry.get("outlier_id") or "") == str(item_id or "")), {})
            options = payload.get("options") if isinstance(payload.get("options"), dict) else {}
            self._apply_exclusions_to_profiles(self.normalize_options(options), [selected.get("face_id")])
        return {"updated": updated, "findings": payload}

    def _apply_exclusions_to_profiles(self, options: Dict[str, Any], face_ids: List[Any]) -> None:
        excluded = set()
        for face_id in face_ids:
            try:
                excluded.add(int(face_id))
            except (TypeError, ValueError):
                continue
        if not excluded:
            return
        state_key = self._profile_state_key(options)
        payload = self.backend.file_analysis.readRuntimeState(self.PROFILE_STATE_TYPE, state_key)
        profiles = payload.get("profiles") if isinstance(payload.get("profiles"), list) else []
        changed = False
        for profile in profiles:
            references = profile.get("references") if isinstance(profile.get("references"), list) else []
            remaining = []
            for reference in references:
                try:
                    face_id = int(reference.get("face_id") or 0)
                except (TypeError, ValueError):
                    face_id = 0
                if face_id not in excluded:
                    remaining.append(reference)
            if len(remaining) == len(references):
                continue
            changed = True
            profile["references"] = remaining
            profile["used_count"] = len(remaining)
            profile["quality"] = "good" if len(remaining) >= options["min_faces_per_person"] else "limited"
            embeddings = [reference.get("embedding") or [] for reference in remaining]
            profile["centroid_embedding"] = self._centroid(embeddings)
            if remaining:
                medoid = remaining[self._medoid_index(embeddings)]
                profile["medoid"] = {key: medoid[key] for key in ("face_id", "image_id", "image_path", "bbox")}
            else:
                profile["medoid"] = {}
        if changed:
            payload["profiles"] = profiles
            payload["updated_at"] = datetime.now(timezone.utc).isoformat()
            self.backend.file_analysis.writeRuntimeState(self.PROFILE_STATE_TYPE, state_key, payload)
            self.backend.file_analysis.writeCheckFindings(self.FINDING_PROFILES, {
                "finding_type": self.FINDING_PROFILES,
                "entries": [
                    {key: value for key, value in profile.items() if key not in {"centroid_embedding", "references"}}
                    for profile in profiles
                ],
            })

    def sync_review_progress(self, *, user_key: str, action: str, operation_mode: str = "immediate") -> Dict[str, Any]:
        status_mode = "findings" if str(operation_mode or "").strip().lower() == "findings" else "scan"
        payload = self.findings(action, user_key=user_key, operation_mode=operation_mode)
        entries = payload.get("entries") if isinstance(payload.get("entries"), list) else []
        open_entries = self._open_entries(entries)
        current = open_entries[0] if open_entries else {}
        options = payload.get("options") if isinstance(payload.get("options"), dict) else {}
        options = {**options, "operation_mode": status_mode}
        self._set_progress(
            user_key, action, options, running=False, finished=True, phase="review_required" if open_entries else "finished",
            message_key="cleanup:recognition_review_required" if open_entries else "cleanup:recognition_scan_finished",
            message="Manual review required for the next recognition finding." if open_entries else "Recognition scan finished.",
            current_path=str(current.get("image_path") or ""), findings_count=len(entries),
            entries_current=len(entries) - len(open_entries), entries_total=len(entries),
        )
        return self.backend.getCleanupProgress(user_key, action)

    def apply_suggestions(self, *, user_key: str, cookies: Dict[str, str], base_url: str, selected_ids: Optional[List[str]] = None, operation_mode: str = "findings", action: str = ACTION_SUGGEST) -> Dict[str, Any]:
        requested = {str(value) for value in selected_ids or []}
        mode = str(operation_mode or "findings").strip().lower()
        normalized_action = str(action or self.ACTION_SUGGEST).strip().lower()
        if normalized_action not in {self.ACTION_SUGGEST, self.ACTION_ASSIGNMENT}:
            normalized_action = self.ACTION_SUGGEST
        payload = self.findings(normalized_action, user_key=user_key, operation_mode=mode)
        entries = payload.get("entries") if isinstance(payload.get("entries"), list) else []
        written = skipped = errors = 0
        for entry in entries:
            suggestion_id = str(entry.get("suggestion_id") or "")
            selected = suggestion_id in requested if requested else entry.get("selection_state") == "selected"
            if not selected or entry.get("write_state") == "written":
                continue
            try:
                self.backend.assignMatchedFaceToKnownPerson(
                    user_key=user_key, cookies=cookies, base_url=base_url,
                    face_id=int(entry["unknown_face_id"]), person_id=int(entry["best_person_id"]),
                    person_name=str(entry["best_person_name"]), item_id=int(entry["image_id"]), image_path=str(entry["image_path"]),
                )
                entry["write_state"] = "written"
                written += 1
            except Exception as exc:
                entry["write_state"] = "failed"
                entry["error"] = f"{type(exc).__name__}: {exc}"
                errors += 1
        if mode == "immediate":
            self._write_active_findings(user_key=user_key, action=normalized_action, payload=payload)
        else:
            self.backend.file_analysis.writeCheckFindings(self._finding_type(normalized_action), payload)
        return {"written_count": written, "skipped_count": skipped, "errors_count": errors, "findings": payload}

    def _set_progress(self, user_key: str, action: str, options: Dict[str, Any], **updates: Any) -> None:
        kind = str(updates.get("progress_kind") or "").strip().lower()
        if not kind:
            kind = "entries" if updates.get("entries_total") is not None else ("images" if updates.get("images_total") is not None else "persons")
        if kind == "images":
            current = int(updates.get("images_scanned") or 0)
            total = int(updates.get("images_total") or 0)
            title_key, fallback_title = "cleanup:label_images", "Bilder"
            primary_key, primary_label = "cleanup:label_scanned", "geprüft"
            secondary_key, secondary_label = "cleanup:label_files_remaining", "verbleibend"
        elif kind == "entries":
            current = int(updates.get("entries_current") or 0)
            total = int(updates.get("entries_total") or 0)
            title_key, fallback_title = "cleanup:label_entries", "Einträge"
            primary_key, primary_label = "cleanup:label_scanned", "geprüft"
            secondary_key, secondary_label = "cleanup:label_entries_remaining", "verbleibend"
        else:
            current = int(updates.get("persons_scanned") or 0)
            total = int(updates.get("persons_total") or 0)
            title_key, fallback_title = "cleanup:label_persons", "Personen"
            primary_key, primary_label = "cleanup:label_scanned", "geprüft"
            secondary_key, secondary_label = "cleanup:label_persons_remaining", "verbleibend"
        counters = [
            self.backend._buildStatusCounter("profiles", value=int(updates.get("profiles_built") or 0), label_key="cleanup:label_profiles", fallback_label="Person profiles", show_when_zero=True),
            self.backend._buildStatusCounter("findings", value=int(updates.get("findings_count") or 0), label_key="cleanup:label_findings", fallback_label="Findings", show_when_zero=True),
            self.backend._buildStatusCounter("images", value=int(updates.get("images_scanned") or 0), label_key="cleanup:label_images_processed", fallback_label="Images", show_when_zero=False),
        ]
        if action != self.ACTION_BUILD:
            counters.append(self.backend._buildStatusCounter("faces", value=int(updates.get("faces_scanned") or 0), label_key="cleanup:label_faces_processed", fallback_label="Faces", show_when_zero=False))
        counters.extend([
            self.backend._buildStatusCounter("references", value=int(updates.get("references_count") or 0), label_key="cleanup:label_references", fallback_label="Reference faces"),
            self.backend._buildStatusCounter("errors", value=int(updates.get("errors_count") or 0), label_key="cleanup:label_errors", fallback_label="Errors"),
        ])
        status = self.backend._buildStatusPayload(
            operation="cleanup",
            action=action,
            mode="findings" if str(options.get("operation_mode") or "").strip().lower() == "findings" else "scan",
            phase=str(updates.get("phase") or ""),
            progress=self.backend._buildStatusProgress(
                kind=kind, current=current, total=total,
                title_key=title_key, fallback_title=fallback_title,
                primary_label_key=primary_key, fallback_primary_label=primary_label,
                secondary_label_key=secondary_key, fallback_secondary_label=secondary_label,
            ),
            counters=counters,
        )
        self.backend._setCleanupProgress(user_key, action=action, options=options, status=status, **updates)
