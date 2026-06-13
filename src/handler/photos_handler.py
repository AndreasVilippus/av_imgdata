#!/usr/bin/env python3
import json
import threading
import unicodedata
from pathlib import Path
from typing import Any, Dict, List, Optional
from api.session_manager import SessionManager, SessionManagerError
from services.config_service import ConfigService

DEFAULT_MAX_PHOTOS_PERSONS = ConfigService.defaultConfig()["photos"]["MAX_PHOTOS_PERSONS"]


class PhotosLookupCache:
    def __init__(self):
        self.folder_id_by_path: Dict[str, int] = {}
        self.items_by_folder_id: Dict[tuple, Dict[str, Dict[str, Any]]] = {}
        self._folders_by_parent_id: Dict[Optional[int], List[Dict[str, Any]]] = {}
        self.lock = threading.Lock()


class PhotosHandler:
    """Photos/FotoTeam-specific DSM API access."""

    def __init__(self, session_manager: SessionManager, config_service: ConfigService):
        self._session_manager = session_manager
        self._config_service = config_service

    def _max_photos_persons(self) -> int:
        config = self._config_service.readMergedConfig()
        photos = config.get("photos", {})
        try:
            return max(1, int(photos.get("MAX_PHOTOS_PERSONS", DEFAULT_MAX_PHOTOS_PERSONS)))
        except (TypeError, ValueError):
            return DEFAULT_MAX_PHOTOS_PERSONS

    def _face_match_person_sort_order(self) -> str:
        config = self._config_service.readMergedConfig()
        face_match = config.get("face_match", {}) if isinstance(config.get("face_match"), dict) else {}
        normalized = str(face_match.get("PERSON_SORT_ORDER", "id_desc") or "").strip().lower()
        return normalized if normalized in {"id_desc", "id_asc", "none"} else "id_desc"

    @staticmethod
    def _person_id_value(person: Dict[str, Any]) -> Optional[int]:
        try:
            return int(person.get("id"))
        except (TypeError, ValueError):
            return None

    def sortPersonsForFaceMatch(self, persons: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        order = self._face_match_person_sort_order()
        normalized = list(persons or [])
        if order == "none":
            return normalized
        if order == "id_asc":
            return sorted(
                normalized,
                key=lambda person: (
                    self._person_id_value(person) is None,
                    self._person_id_value(person) if self._person_id_value(person) is not None else 0,
                ),
            )
        return sorted(
            normalized,
            key=lambda person: (
                self._person_id_value(person) is None,
                -(self._person_id_value(person) if self._person_id_value(person) is not None else 0),
            ),
        )

    @staticmethod
    def _filter_persons_by_name(persons: List[Dict[str, Any]], person_filter: Optional[str] = None) -> List[Dict[str, Any]]:
        if person_filter == "unknown":
            return [p for p in persons if p.get("name", "") == ""]
        if person_filter == "known":
            return [p for p in persons if p.get("name", "") != ""]
        return persons

    @staticmethod
    def _normalize_person_name(name: Any) -> str:
        raw_value = unicodedata.normalize("NFKC", str(name or ""))
        cleaned_chars = []
        for char in raw_value:
            category = unicodedata.category(char)
            if category.startswith("C"):
                if char.isspace():
                    cleaned_chars.append(" ")
                continue
            cleaned_chars.append(char)
        normalized = "".join(cleaned_chars)
        return " ".join(normalized.strip().casefold().split())

    @staticmethod
    def _string_codepoints(value: Any) -> List[str]:
        return [f"U+{ord(char):04X}" for char in str(value or "")]

    def person_status(
        self,
        *,
        user_key: str,
        cookies: Dict[str, str],
        base_url: str,
    ) -> Dict[str, int]:
        persons = self.listFotoTeamPerson(user_key=user_key, cookies=cookies, base_url=base_url)
        total = len(persons)
        unknown = len([p for p in persons if p.get("name") == ""])
        known = total - unknown
        return {"total": total, "known": known, "unknown": unknown}

    def listFotoTeamPerson(
        self,
        *,
        user_key: str,
        cookies: Dict[str, str],
        base_url: str,
        offset: int = 0,
        limit: int = DEFAULT_MAX_PHOTOS_PERSONS,
        show_more: bool = True,
        show_hidden: bool = False,
        additional: Optional[List[str]] = None,
        person_filter: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        max_persons = self._max_photos_persons()
        if limit > max_persons:
            limit = max_persons
        payload = self._session_manager.call_api(
            user_key=user_key,
            cookies=cookies,
            base_url=base_url,
            api="SYNO.FotoTeam.Browse.Person",
            params={
                "method": "list",
                "version": "1",
                "library": "shared_space",
                "additional": additional or [],
                "offset": str(offset),
                "limit": str(limit),
                "show_more": "true" if show_more else "false",
                "show_hidden": "true" if show_hidden else "false",
            },
        )
        data = payload.get("data", {})
        if not isinstance(data, dict):
            return []
        items = data.get("list", [])
        if not isinstance(items, list):
            return []
        return self._filter_persons_by_name(items, person_filter=person_filter)

    def listFotoTeamPersonUnknown(
        self,
        *,
        user_key: str,
        cookies: Dict[str, str],
        base_url: str,
        offset: int = 0,
        limit: int = DEFAULT_MAX_PHOTOS_PERSONS,
        show_more: bool = True,
        show_hidden: bool = False,
        additional: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        return self.listFotoTeamPerson(
            user_key=user_key,
            cookies=cookies,
            base_url=base_url,
            offset=offset,
            limit=limit,
            show_more=show_more,
            show_hidden=show_hidden,
            additional=additional,
            person_filter="unknown",
        )

    def listFotoTeamPersonKnown(
        self,
        *,
        user_key: str,
        cookies: Dict[str, str],
        base_url: str,
        offset: int = 0,
        limit: int = DEFAULT_MAX_PHOTOS_PERSONS,
        show_more: bool = True,
        show_hidden: bool = False,
        additional: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        return self.listFotoTeamPerson(
            user_key=user_key,
            cookies=cookies,
            base_url=base_url,
            offset=offset,
            limit=limit,
            show_more=show_more,
            show_hidden=show_hidden,
            additional=additional,
            person_filter="known",
        )

    def findKnownPersonByName(
        self,
        *,
        user_key: str,
        cookies: Dict[str, str],
        base_url: str,
        name: str,
        known_persons: Optional[List[Dict[str, Any]]] = None,
    ) -> Optional[Dict[str, Any]]:
        normalized_name = self._normalize_person_name(name)
        if not normalized_name:
            return None

        persons = known_persons
        if persons is None:
            persons = self.listFotoTeamPersonKnown(
                user_key=user_key,
                cookies=cookies,
                base_url=base_url,
            )

        for person in persons:
            if self._normalize_person_name(person.get("name")) == normalized_name:
                return person

        try:
            suggestions = self.suggestFotoTeamPerson(
                user_key=user_key,
                cookies=cookies,
                base_url=base_url,
                name_prefix=name,
                additional=["thumbnail"],
                limit=20,
            )
        except SessionManagerError:
            suggestions = []
        for person in suggestions:
            if self._normalize_person_name(person.get("name")) == normalized_name:
                return person
        return None

    def debugKnownPersonLookup(
        self,
        *,
        user_key: str,
        cookies: Dict[str, str],
        base_url: str,
        name: str,
        known_persons: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        normalized_name = self._normalize_person_name(name)
        persons = known_persons
        if persons is None:
            persons = self.listFotoTeamPersonKnown(
                user_key=user_key,
                cookies=cookies,
                base_url=base_url,
                additional=["thumbnail"],
            )

        list_matches = []
        for person in persons:
            person_name = person.get("name")
            if self._normalize_person_name(person_name) == normalized_name:
                list_matches.append({
                    "id": person.get("id"),
                    "name": person_name,
                })

        suggestions = self.suggestFotoTeamPerson(
            user_key=user_key,
            cookies=cookies,
            base_url=base_url,
            name_prefix=name,
            additional=["thumbnail"],
            limit=20,
        )
        suggest_matches = []
        for person in suggestions:
            person_name = person.get("name")
            if self._normalize_person_name(person_name) == normalized_name:
                suggest_matches.append({
                    "id": person.get("id"),
                    "name": person_name,
                })

        return {
            "raw_name": str(name or ""),
            "normalized_name": normalized_name,
            "raw_name_codepoints": self._string_codepoints(name),
            "known_persons_count": len(persons),
            "list_exact_matches": list_matches,
            "suggest_exact_matches": suggest_matches,
        }

    def findKnownPersonById(
        self,
        *,
        person_id: int,
        known_persons: List[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        for person in known_persons:
            try:
                if int(person.get("id")) == int(person_id):
                    return person
            except Exception:
                continue
        return None

    def suggestFotoTeamPerson(
        self,
        *,
        user_key: str,
        cookies: Dict[str, str],
        base_url: str,
        name_prefix: str,
        additional: Optional[List[str]] = None,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        normalized_prefix = str(name_prefix or "").strip()
        if not normalized_prefix:
            return []

        payload = self._session_manager.call_api_post(
            user_key=user_key,
            cookies=cookies,
            base_url=base_url,
            api="SYNO.FotoTeam.Browse.Person",
            params={
                "method": "suggest",
                "version": "3",
                "name_prefix": json.dumps(normalized_prefix),
                "additional": additional or [],
                "limit": int(limit),
            },
        )
        data = payload.get("data", {})
        if not isinstance(data, dict):
            return []
        items = data.get("list", [])
        return items if isinstance(items, list) else []

    def listFotoTeamItems(
        self,
        *,
        user_key: str,
        cookies: Dict[str, str],
        base_url: str,
        person_id: Optional[int] = None,
        folder_id: Optional[int] = None,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        offset: int = 0,
        limit: int = 100,
        additional: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        params: Dict[str, Any] = {
            "method": "list",
            "version": "4",
            "offset": str(offset),
            "limit": str(limit),
            "additional": additional or [],
        }
        if person_id is not None:
            params["person_id"] = str(person_id)
        if folder_id is not None:
            params["folder_id"] = str(folder_id)
        if start_time is not None:
            params["start_time"] = str(start_time)
        if end_time is not None:
            params["end_time"] = str(end_time)

        payload = self._session_manager.call_api(
            user_key=user_key,
            cookies=cookies,
            base_url=base_url,
            api="SYNO.FotoTeam.Browse.Item",
            params=params,
        )
        data = payload.get("data", {})
        if not isinstance(data, dict):
            return []
        items = data.get("list", [])
        return items if isinstance(items, list) else []

    def getFotoTeamPerson(
        self,
        *,
        user_key: str,
        cookies: Dict[str, str],
        base_url: str,
        person_id: int,
        additional: Optional[List[str]] = None,
    ) -> Optional[Dict[str, Any]]:
        payload = self._session_manager.call_api(
            user_key=user_key,
            cookies=cookies,
            base_url=base_url,
            api="SYNO.FotoTeam.Browse.Person",
            params={
                "method": "get",
                "version": "3",
                "library": "shared_space",
                "id": str(person_id),
                "person_id": str(person_id),
                "additional": additional or [],
            },
        )
        data = payload.get("data", {})
        if not isinstance(data, dict):
            return None

        if data.get("id") is not None:
            return data

        person = data.get("person")
        if isinstance(person, dict):
            return person

        items = data.get("list", [])
        if not isinstance(items, list) or not items:
            return None

        person = items[0]
        return person if isinstance(person, dict) else None

    def list_faceFotoTeamItems(
        self,
        *,
        user_key: str,
        cookies: Dict[str, str],
        base_url: str,
        id_item: int,
    ) -> List[Dict[str, Any]]:
        payload = self._session_manager.call_api(
            user_key=user_key,
            cookies=cookies,
            base_url=base_url,
            api="SYNO.FotoTeam.Browse.Item",
            params={
                "method": "list_face",
                "version": "6",
                "id_item": str(id_item),
            },
        )
        data = payload.get("data", {})
        if not isinstance(data, dict):
            return []

        faces = data.get("list", [])
        if not isinstance(faces, list):
            return []

        mapped: List[Dict[str, Any]] = []
        for face in faces:
            if not isinstance(face, dict):
                continue
            mapped.append(
                {
                    "face_id": face.get("face_id"),
                    "face_name": face.get("name", ""),
                    "person_id": face.get("person_id"),
                    "bbox": face.get("face_bounding_box"),
                }
            )
        return mapped

    def getFotoTeamFolder(
        self,
        *,
        user_key: str,
        cookies: Dict[str, str],
        base_url: str,
        id_folder: int,
    ) -> Dict[str, Any]:
        payload = self._session_manager.call_api(
            user_key=user_key,
            cookies=cookies,
            base_url=base_url,
            api="SYNO.FotoTeam.Browse.Folder",
            params={
                "method": "get",
                "version": "2",
                "id": str(id_folder),
            },
        )
        data = payload.get("data", {})
        return data if isinstance(data, dict) else {}

    def listFotoTeamFolders(
        self,
        *,
        user_key: str,
        cookies: Dict[str, str],
        base_url: str,
        parent_id: Optional[int] = None,
        offset: int = 0,
        limit: int = 500,
    ) -> List[Dict[str, Any]]:
        params: Dict[str, Any] = {
            "method": "list",
            "version": "2",
            "offset": str(offset),
            "limit": str(limit),
        }
        if parent_id is not None:
            params["id"] = str(parent_id)
        payload = self._session_manager.call_api(
            user_key=user_key,
            cookies=cookies,
            base_url=base_url,
            api="SYNO.FotoTeam.Browse.Folder",
            params=params,
        )
        data = payload.get("data", {})
        if not isinstance(data, dict):
            return []
        items = data.get("list", [])
        return items if isinstance(items, list) else []

    def findFotoTeamItemByPath(
        self,
        *,
        user_key: str,
        cookies: Dict[str, str],
        base_url: str,
        shared_folder: str,
        image_path: str,
        additional: Optional[List[str]] = None,
        lookup_cache: Optional[PhotosLookupCache] = None,
    ) -> Optional[Dict[str, Any]]:
        try:
            relative_path = Path(str(image_path or "").strip()).relative_to(Path(str(shared_folder or "").strip()))
        except Exception:
            return None

        relative_parent = relative_path.parent
        if str(relative_parent) in ("", "."):
            return None

        folder_keys: List[str] = []
        current_key = ""
        for part in relative_parent.parts:
            normalized_part = str(part or "").strip().strip("/")
            if not normalized_part:
                continue
            current_key = f"{current_key}/{normalized_part}" if current_key else f"/{normalized_part}"
            folder_keys.append(current_key)

        if not folder_keys:
            return None

        current_parent_id: Optional[int] = None
        current_folder: Optional[Dict[str, Any]] = None

        for folder_key in folder_keys:
            cached_folder_id: Optional[int] = None
            if lookup_cache is not None:
                with lookup_cache.lock:
                    cached_folder_id = lookup_cache.folder_id_by_path.get(folder_key)
            if cached_folder_id is not None:
                current_parent_id = cached_folder_id
                current_folder = {"id": cached_folder_id, "name": folder_key}
                continue

            folders: Optional[List[Dict[str, Any]]] = None
            if lookup_cache is not None:
                with lookup_cache.lock:
                    cached_folders = lookup_cache._folders_by_parent_id.get(current_parent_id)
                    if cached_folders is not None:
                        folders = [dict(folder) for folder in cached_folders if isinstance(folder, dict)]
            if folders is None:
                folders = self.listFotoTeamFolders(
                    user_key=user_key,
                    cookies=cookies,
                    base_url=base_url,
                    parent_id=current_parent_id,
                )
                if lookup_cache is not None:
                    with lookup_cache.lock:
                        lookup_cache._folders_by_parent_id[current_parent_id] = [
                            dict(folder) for folder in folders if isinstance(folder, dict)
                        ]

            next_folder = next(
                (
                    folder for folder in folders
                    if isinstance(folder, dict) and str(folder.get("name") or "").strip() == folder_key
                ),
                None,
            )
            if not isinstance(next_folder, dict):
                return None
            current_folder = next_folder
            try:
                current_parent_id = int(next_folder.get("id"))
            except (TypeError, ValueError):
                return None
            if lookup_cache is not None:
                with lookup_cache.lock:
                    lookup_cache.folder_id_by_path[folder_key] = current_parent_id

        if current_parent_id is None:
            return None

        filename = relative_path.name
        effective_additional = additional or ["thumbnail"]
        cache_key = (current_parent_id, tuple(str(value) for value in effective_additional))
        if lookup_cache is not None:
            with lookup_cache.lock:
                cached_items = lookup_cache.items_by_folder_id.get(cache_key)
                if cached_items is not None:
                    matched_item = cached_items.get(filename)
                    if isinstance(matched_item, dict):
                        return dict(matched_item)
                    return None

        offset = 0
        page_size = 200
        indexed_items: Dict[str, Dict[str, Any]] = {}
        while True:
            items = self.listFotoTeamItems(
                user_key=user_key,
                cookies=cookies,
                base_url=base_url,
                folder_id=current_parent_id,
                offset=offset,
                limit=page_size,
                additional=effective_additional,
            )
            if not items:
                if lookup_cache is not None:
                    with lookup_cache.lock:
                        lookup_cache.items_by_folder_id[cache_key] = indexed_items
                return None

            for item in items:
                if not isinstance(item, dict):
                    continue
                item_filename = str(item.get("filename") or "").strip()
                if not item_filename:
                    continue
                cached_item = dict(item)
                if current_folder and "folder_id" not in cached_item:
                    cached_item["folder_id"] = current_parent_id
                indexed_items[item_filename] = cached_item

            if len(items) < page_size:
                if lookup_cache is not None:
                    with lookup_cache.lock:
                        lookup_cache.items_by_folder_id[cache_key] = indexed_items
                matched_item = indexed_items.get(filename)
                return dict(matched_item) if isinstance(matched_item, dict) else None
            offset += page_size

    def indexFotoTeamPaths(
        self,
        *,
        user_key: str,
        cookies: Dict[str, str],
        base_url: str,
        paths: List[str],
        index_type: str = "basic",
    ) -> Dict[str, Any]:
        normalized_paths = [
            str(path or "").strip()
            for path in paths
            if str(path or "").strip()
        ]
        if not normalized_paths:
            return {}
        payload = self._session_manager.call_api_post(
            user_key=user_key,
            cookies=cookies,
            base_url=base_url,
            api="SYNO.FotoTeam.Index",
            params={
                "method": "index_add",
                "version": "1",
                "type": str(index_type or "basic").strip() or "basic",
                "paths": normalized_paths,
            },
        )
        data = payload.get("data", {})
        return data if isinstance(data, dict) else {}

    def assignFaceToPerson(
        self,
        *,
        user_key: str,
        cookies: Dict[str, str],
        base_url: str,
        face_id: int,
        person_id: int,
        person_name: str,
    ) -> Dict[str, Any]:
        payload = self._session_manager.call_api_post(
            user_key=user_key,
            cookies=cookies,
            base_url=base_url,
            api="SYNO.FotoTeam.Browse.Person",
            params={
                "method": "separate",
                "version": "1",
                "face_id": [int(face_id)],
                "target_id": str(person_id),
            },
        )
        data = payload.get("data", {})
        return data if isinstance(data, dict) else {}

    def createPersonFromFace(
        self,
        *,
        user_key: str,
        cookies: Dict[str, str],
        base_url: str,
        face_id: int,
        person_name: str,
    ) -> Dict[str, Any]:
        payload = self._session_manager.call_api_post(
            user_key=user_key,
            cookies=cookies,
            base_url=base_url,
            api="SYNO.FotoTeam.Browse.Person",
            params={
                "method": "separate",
                "version": "1",
                "face_id": [int(face_id)],
                "name": json.dumps(person_name),
            },
        )
        data = payload.get("data", {})
        return data if isinstance(data, dict) else {}

    def addFaceToItem(
        self,
        *,
        user_key: str,
        cookies: Dict[str, str],
        base_url: str,
        id_item: int,
        face_bbox: Dict[str, Any],
        face_id_temp: Optional[str] = None,
        person_id: Optional[int] = None,
        person_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        top_left = face_bbox.get("top_left") if isinstance(face_bbox, dict) else None
        bottom_right = face_bbox.get("bottom_right") if isinstance(face_bbox, dict) else None
        face_payload: Dict[str, Any] = {
            "face_bounding_box": {
                "top_left": {
                    "x": float((top_left or {}).get("x") or 0),
                    "y": float((top_left or {}).get("y") or 0),
                },
                "bottom_right": {
                    "x": float((bottom_right or {}).get("x") or 0),
                    "y": float((bottom_right or {}).get("y") or 0),
                },
            },
            "face_id_temp": str(face_id_temp or f"{id_item}-0"),
        }
        if person_id is not None:
            face_payload["person_id"] = int(person_id)
        else:
            normalized_person_name = str(person_name or "").strip()
            if normalized_person_name:
                face_payload["name"] = normalized_person_name
        payload = self._session_manager.call_api_post(
            user_key=user_key,
            cookies=cookies,
            base_url=base_url,
            api="SYNO.FotoTeam.Browse.Person",
            params={
                "method": "add_face",
                "version": "3",
                "id_item": int(id_item),
                "face": [face_payload],
            },
        )
        data = payload.get("data", {})
        return data if isinstance(data, dict) else {}
