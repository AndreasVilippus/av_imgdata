#!/usr/bin/env python3
import json
import unicodedata
from typing import Any, Dict, List, Optional
from api.session_manager import SessionManager
from services.config_service import ConfigService

DEFAULT_MAX_PHOTOS_PERSONS = ConfigService.defaultConfig()["photos"]["MAX_PHOTOS_PERSONS"]

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

    @staticmethod
    def _filter_persons_by_name(persons: List[Dict[str, Any]], person_filter: Optional[str] = None) -> List[Dict[str, Any]]:
        if person_filter == "unknown":
            return [p for p in persons if p.get("name", "") == ""]
        if person_filter == "known":
            return [p for p in persons if p.get("name", "") != ""]
        return persons

    @staticmethod
    def _normalize_person_name(name: Any) -> str:
        normalized = unicodedata.normalize("NFC", str(name or ""))
        return " ".join(normalized.strip().casefold().split())

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
        return None

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
        person_id: int,
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
            "person_id": str(person_id),
            "additional": additional or [],
        }
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
                "name": json.dumps(person_name),
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
