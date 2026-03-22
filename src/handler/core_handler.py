#!/usr/bin/env python3
from typing import Dict, Optional
from api.session_manager import SessionManager


class CoreHandler:
    """DSM Core API access (non-Photos)."""

    def __init__(self, session_manager: SessionManager):
        self._session_manager = session_manager

    def getSharedFolder(
        self,
        *,
        user_key: str,
        cookies: Dict[str, str],
        base_url: str,
        folder_name: str = "photo",
    ) -> Optional[str]:
        payload = self._session_manager.call_api(
            user_key=user_key,
            cookies=cookies,
            base_url=base_url,
            api="SYNO.Core.Share",
            params={
                "method": "list",
                "version": "1",
            },
        )

        data = payload.get("data")
        if not isinstance(data, dict):
            return None
        shares = data.get("shares")
        if not isinstance(shares, list):
            return None

        for share in shares:
            if not isinstance(share, dict):
                continue
            if share.get("name") != folder_name:
                continue
            vol_path = share.get("vol_path")
            if isinstance(vol_path, str) and vol_path:
                return f"{vol_path}/{folder_name}"
        return None
