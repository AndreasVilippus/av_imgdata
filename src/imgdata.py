#!/usr/bin/env python3
from pathlib import Path
from threading import Lock
from typing import Any, Dict, List, Optional

from api.session_manager import SessionManager
from handler.core_handler import CoreHandler
from handler.file_handler import FileHandler
from handler.photos_handler import PhotosHandler
from models.file_face import FileFace
from models.photos_face import PhotosFace
from services.bbox_normlaizer import from_photos, from_xmp
from services.config_service import ConfigService
from services.face_matcher import FaceMatcher
from services.name_mapping_service import NameMappingService


class ImgDataService:
    """Orchestrates business use-cases across Photos and file handlers."""

    def __init__(self, session_manager: SessionManager):
        self.session_manager = session_manager
        self.core = CoreHandler(session_manager)
        self.photos = PhotosHandler(session_manager)
        self.config = ConfigService()
        self.files = FileHandler(self.config)
        self.name_mappings = NameMappingService()
        self.face_matcher = FaceMatcher()
        self._face_matching_progress: Dict[str, Dict[str, Any]] = {}
        self._face_matching_progress_lock = Lock()

    def update_session_context(
        self,
        *,
        user_key: str,
        base_url: str,
        kk_message: Optional[str] = None,
        synotoken: Optional[str] = None,
        account: Optional[str] = None,
    ) -> None:
        self.session_manager.update_context(
            user_key,
            base_url=base_url,
            kk_message=kk_message,
            synotoken=synotoken,
            account=account,
        )

    def status_persons(
        self,
        *,
        user_key: str,
        cookies: Dict[str, str],
        base_url: str,
    ) -> Dict[str, int]:
        status = self.photos.person_status(user_key=user_key, cookies=cookies, base_url=base_url)
        status["mappings"] = len(self.name_mappings.readNameMappings())
        return status

    def _setFaceMatchingProgress(self, user_key: str, **updates: Any) -> None:
        with self._face_matching_progress_lock:
            current = dict(self._face_matching_progress.get(user_key, {}))
            current.update(updates)
            self._face_matching_progress[user_key] = current

    def _setFaceMatchingProgressMessage(
        self,
        user_key: str,
        message_key: str,
        *,
        message_params: Optional[Dict[str, Any]] = None,
        message: Optional[str] = None,
        **updates: Any,
    ) -> None:
        payload: Dict[str, Any] = {
            "message_key": message_key,
            "message_params": message_params or {},
            "message": message or message_key,
        }
        payload.update(updates)
        self._setFaceMatchingProgress(user_key, **payload)

    def getFaceMatchingProgress(self, user_key: str) -> Dict[str, Any]:
        with self._face_matching_progress_lock:
            current = self._face_matching_progress.get(user_key, {})
            return dict(current) if isinstance(current, dict) else {}

    def requestStopFaceMatching(self, user_key: str) -> Dict[str, Any]:
        self._setFaceMatchingProgressMessage(
            user_key,
            "face_match:progress_stopping",
            stop_requested=True,
        )
        return self.getFaceMatchingProgress(user_key)

    def _shouldStopFaceMatching(self, user_key: str) -> bool:
        progress = self.getFaceMatchingProgress(user_key)
        return bool(progress.get("stop_requested"))

    @staticmethod
    def _buildPhotoImagePath(shared_folder: str, folder_name: str, filename: str) -> str:
        folder_relative = folder_name.strip()
        if folder_relative.startswith("/"):
            folder_relative = folder_relative.lstrip("/")

        shared_folder_name = Path(shared_folder).name
        if shared_folder_name and folder_relative.startswith(f"{shared_folder_name}/"):
            folder_relative = folder_relative[len(shared_folder_name) + 1:]

        if folder_relative:
            return str(Path(shared_folder) / folder_relative / filename)
        return str(Path(shared_folder) / filename)
    
    def searchPhotoFaceInFile(
        self,
        *,
        user_key: str,
        cookies: Dict[str, str],
        base_url: str,
        limit: int = 1,
        offset: int = 0,
        skip_face_ids: Optional[List[int]] = None,
        auto: bool = False,
    ) -> Dict[str, Any]:
        known_persons_cache: Optional[List[Dict[str, Any]]] = None
        skip_face_ids_set = {
            int(face_id) for face_id in (skip_face_ids or [])
            if isinstance(face_id, int) or str(face_id).isdigit()
        }
        persons_read = 0
        images_read = 0
        faces_read = 0
        metadata_faces_read = 0
        transferred_count = 0
        final_message_key = "face_match:progress_finished"
        final_message_params: Dict[str, Any] = {}
        self._setFaceMatchingProgressMessage(
            user_key,
            "face_match:status_starting",
            running=True,
            stop_requested=False,
            action="search_photo_face_in_file",
            persons_read=0,
            images_read=0,
            faces_read=0,
            current_person_id=None,
            current_image_id=None,
            current_face_id=None,
            metadata_faces_read=0,
            transferred_count=0,
        )
        try:
            shared_folder = self.core.getSharedFolder(
                user_key=user_key,
                cookies=cookies,
                base_url=base_url,
                folder_name="photo",
            )
            if not shared_folder:
                final_message_key = "face_match:progress_shared_folder_missing"
                return {
                    "searched": False,
                    "person": None,
                    "image": None,
                    "face": None,
                    "metadata_face": None,
                    "image_path": None,
                    "error": "shared_folder_not_found",
                }

            unknown_persons: List[Dict[str, Any]] = self.photos.listFotoTeamPersonUnknown(
                user_key=user_key,
                cookies=cookies,
                base_url=base_url,
                limit=limit,
                offset=offset,
                show_more=True,
                show_hidden=False,
            )
            self._setFaceMatchingProgressMessage(
                user_key,
                "face_match:progress_unknown_persons_loaded",
                message_params={"count": len(unknown_persons)},
                persons_total=len(unknown_persons),
            )

            for person in unknown_persons:
                if self._shouldStopFaceMatching(user_key):
                    final_message_key = "face_match:progress_stopped"
                    return {
                        "searched": False,
                        "stopped": True,
                        "person": None,
                        "image": None,
                        "face": None,
                        "metadata_face": None,
                        "image_path": None,
                        "transferred_count": transferred_count,
                        "auto": auto,
                    }
                person_id = person.get("id")
                if person_id is None:
                    continue

                try:
                    person_id_int = int(person_id)
                except (TypeError, ValueError):
                    continue

                persons_read += 1
                self._setFaceMatchingProgressMessage(
                    user_key,
                    "face_match:progress_checking_person",
                    message_params={"current": persons_read, "total": len(unknown_persons)},
                    persons_read=persons_read,
                    current_person_id=person_id_int,
                )

                images = self.photos.listFotoTeamItems(
                    user_key=user_key,
                    cookies=cookies,
                    base_url=base_url,
                    person_id=person_id_int,
                    additional=['thumbnail'],
                )

                for image in images:
                    if self._shouldStopFaceMatching(user_key):
                        final_message_key = "face_match:progress_stopped"
                        return {
                            "searched": False,
                            "stopped": True,
                            "person": None,
                            "image": None,
                            "face": None,
                            "metadata_face": None,
                            "image_path": None,
                            "transferred_count": transferred_count,
                            "auto": auto,
                        }
                    image_id = image.get("id")
                    if image_id is None:
                        continue

                    try:
                        image_id_int = int(image_id)
                    except (TypeError, ValueError):
                        continue

                    images_read += 1
                    self._setFaceMatchingProgressMessage(
                        user_key,
                        "face_match:progress_checking_image",
                        message_params={"count": images_read},
                        images_read=images_read,
                        current_image_id=image_id_int,
                    )

                    faces = self.photos.list_faceFotoTeamItems(
                        user_key=user_key,
                        cookies=cookies,
                        base_url=base_url,
                        id_item=image_id_int
                    )
                    for face in faces:
                        if self._shouldStopFaceMatching(user_key):
                            final_message_key = "face_match:progress_stopped"
                            return {
                                "searched": False,
                                "stopped": True,
                                "person": None,
                                "image": None,
                                "face": None,
                                "metadata_face": None,
                                "image_path": None,
                                "transferred_count": transferred_count,
                                "auto": auto,
                            }
                        faces_read += 1
                        self._setFaceMatchingProgressMessage(
                            user_key,
                            "face_match:progress_checking_face",
                            message_params={"count": faces_read},
                            faces_read=faces_read,
                            current_face_id=face.get("face_id"),
                        )
                        face_person_id = face.get("person_id")
                        face_id = face.get("face_id")
                        try:
                            face_person_id_int = int(face_person_id)
                            face_id_int = int(face_id)
                        except (TypeError, ValueError):
                            continue
                        if face_id_int in skip_face_ids_set:
                            continue
                        if face.get("face_name", "") != "":
                            continue
                        if face_person_id_int != person_id_int:
                            continue

                        folder_id = image.get("folder_id")
                        filename = image.get("filename")
                        try:
                            folder_id_int = int(folder_id)
                        except (TypeError, ValueError):
                            continue
                        if not isinstance(filename, str) or not filename:
                            continue

                        folder_payload = self.photos.getFotoTeamFolder(
                            user_key=user_key,
                            cookies=cookies,
                            base_url=base_url,
                            id_folder=folder_id_int,
                        )
                        folder_data = folder_payload.get("folder") if isinstance(folder_payload, dict) else None
                        folder_name = folder_data.get("name") if isinstance(folder_data, dict) else None
                        if not isinstance(folder_name, str) or not folder_name:
                            continue

                        image_path = self._buildPhotoImagePath(shared_folder, folder_name, filename)
                        metadata_faces = self.files.readAllPersonsFromImage(image_path)
                        metadata_faces_read += len(metadata_faces)
                        self._setFaceMatchingProgressMessage(
                            user_key,
                            "face_match:progress_checking_metadata",
                            message_params={"count": images_read},
                            metadata_faces_read=metadata_faces_read,
                        )

                        photo_face = PhotosFace(
                            face_id=face_id_int,
                            person_id=person_id_int,
                            bbox=from_photos(face),
                        )
                        indexed_file_faces = [
                            (
                                metadata_index,
                                FileFace(
                                    name=str(metadata_face.get("name") or ""),
                                    bbox=from_xmp(metadata_face),
                                    source=str(metadata_face.get("source") or "metadata"),
                                    source_format=str(metadata_face.get("source_format") or metadata_face.get("format") or ""),
                                ),
                            )
                            for metadata_index, metadata_face in enumerate(metadata_faces)
                            if isinstance(metadata_face, dict)
                        ]
                        file_faces = [entry[1] for entry in indexed_file_faces]
                        if not file_faces:
                            continue

                        matches = self.face_matcher.match([photo_face], file_faces)
                        self._setFaceMatchingProgressMessage(
                            user_key,
                            "face_match:progress_match_candidates",
                            message_params={"face": faces_read, "count": len(matches)},
                        )
                        if not matches:
                            continue

                        matched = None
                        for candidate in matches:
                            match_name = str(candidate.get("file_name") or "").strip()
                            if match_name:
                                matched = candidate
                                break
                        if not matched:
                            final_message_key = "face_match:progress_only_unnamed_matches"
                            continue

                        file_face_index = matched.get("file_face_index")
                        if not isinstance(file_face_index, int) or file_face_index < 0 or file_face_index >= len(indexed_file_faces):
                            continue
                        metadata_face_index = indexed_file_faces[file_face_index][0]
                        matched_person = None
                        mapped_assignment = None
                        matched_name = str(matched.get("file_name") or "").strip()
                        if matched_name:
                            if known_persons_cache is None:
                                known_persons_cache = self.photos.listFotoTeamPersonKnown(
                                    user_key=user_key,
                                    cookies=cookies,
                                    base_url=base_url,
                                    additional=["thumbnail"],
                                )
                            mapped_assignment = self.name_mappings.findNameMapping(matched_name)
                            if mapped_assignment:
                                mapped_target_name = str(mapped_assignment.get("target_name") or "").strip()
                                if mapped_target_name:
                                    matched_person = self.photos.findKnownPersonByName(
                                        user_key=user_key,
                                        cookies=cookies,
                                        base_url=base_url,
                                        name=mapped_target_name,
                                        known_persons=known_persons_cache,
                                    )
                            if matched_person is None:
                                matched_person = self.photos.findKnownPersonByName(
                                    user_key=user_key,
                                    cookies=cookies,
                                    base_url=base_url,
                                    name=matched_name,
                                    known_persons=known_persons_cache,
                                )
                        final_message_key = "face_match:result_named_match"
                        final_message_params = {}
                        if matched_person:
                            final_message_key = "face_match:result_named_match_with_id"
                            final_message_params = {"id": matched_person.get("id")}

                        if auto and matched_person:
                            matched_person_id = matched_person.get("id") if isinstance(matched_person, dict) else None
                            matched_person_name = matched_person.get("name") if isinstance(matched_person, dict) else None
                            if matched_person_id is not None and matched_person_name:
                                self.assignMatchedFaceToKnownPerson(
                                    user_key=user_key,
                                    cookies=cookies,
                                    base_url=base_url,
                                    face_id=face_id_int,
                                    person_id=int(matched_person_id),
                                    person_name=str(matched_person_name),
                                )
                                transferred_count += 1
                                final_message_key = "face_match:progress_auto_assigned"
                                final_message_params = {"count": transferred_count}
                                self._setFaceMatchingProgressMessage(
                                    user_key,
                                    final_message_key,
                                    message_params=final_message_params,
                                    transferred_count=transferred_count,
                                )
                                skip_face_ids_set.add(face_id_int)
                                continue

                        return {
                            "searched": True,
                            "person": person,
                            "image": image,
                            "face": face,
                            "metadata_face": metadata_faces[metadata_face_index],
                            "image_path": image_path,
                            "match": matched,
                            "matched_person": matched_person,
                            "matched_person_id": matched_person.get("id") if isinstance(matched_person, dict) else None,
                            "name_mapping": mapped_assignment,
                            "transferred_count": transferred_count,
                            "auto": auto,
                        }

            final_message_key = "face_match:result_no_match"
            final_message_params = {}
            if auto and transferred_count:
                final_message_key = "face_match:progress_auto_assign_complete"
                final_message_params = {"count": transferred_count}
            return {
                "searched": True,
                "person": None,
                "image": None,
                "face": None,
                "metadata_face": None,
                "image_path": None,
                "transferred_count": transferred_count,
                "auto": auto,
            }
        finally:
            self._setFaceMatchingProgressMessage(
                user_key,
                final_message_key,
                message_params=final_message_params,
                running=False,
                stop_requested=False,
                persons_read=persons_read,
                images_read=images_read,
                faces_read=faces_read,
                transferred_count=transferred_count,
            )

    def list_files(self, *, base_path: str, pattern: str = "*") -> Dict[str, object]:
        files = self.files.list_files(base_path=base_path, pattern=pattern)
        return {"count": len(files), "files": files}

    def read_file_text(self, *, path: str, max_bytes: int = 1024 * 1024) -> Dict[str, object]:
        return self.files.read_text(path=path, max_bytes=max_bytes)

    def getSharedFolder(
        self,
        *,
        user_key: str,
        cookies: Dict[str, str],
        base_url: str,
        folder_name: str = "photo",
    ) -> Optional[str]:
        return self.core.getSharedFolder(
            user_key=user_key,
            cookies=cookies,
            base_url=base_url,
            folder_name=folder_name,
        )

    def assignMatchedFaceToKnownPerson(
        self,
        *,
        user_key: str,
        cookies: Dict[str, str],
        base_url: str,
        face_id: int,
        person_id: int,
        person_name: str,
    ) -> Dict[str, Any]:
        return self.photos.assignFaceToPerson(
            user_key=user_key,
            cookies=cookies,
            base_url=base_url,
            face_id=face_id,
            person_id=person_id,
            person_name=person_name,
        )

    def createMatchedFaceAsPerson(
        self,
        *,
        user_key: str,
        cookies: Dict[str, str],
        base_url: str,
        face_id: int,
        person_name: str,
    ) -> Dict[str, Any]:
        return self.photos.createPersonFromFace(
            user_key=user_key,
            cookies=cookies,
            base_url=base_url,
            face_id=face_id,
            person_name=person_name,
        )

    def suggestPersonsByName(
        self,
        *,
        user_key: str,
        cookies: Dict[str, str],
        base_url: str,
        name_prefix: str,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        return self.photos.suggestFotoTeamPerson(
            user_key=user_key,
            cookies=cookies,
            base_url=base_url,
            name_prefix=name_prefix,
            additional=["thumbnail"],
            limit=limit,
        )

    def saveNameMapping(
        self,
        *,
        source_name: str,
        target_name: str,
    ) -> bool:
        return self.name_mappings.saveNameMapping(
            source_name=source_name,
            target_name=target_name,
        )

    def getRuntimeConfig(self) -> Dict[str, Any]:
        return self.config.readMergedConfig()

    def saveRuntimeConfig(self, config: Dict[str, Any]) -> bool:
        return self.config.writeConfig(config)
