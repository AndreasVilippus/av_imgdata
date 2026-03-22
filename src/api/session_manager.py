#!/usr/bin/env python3
import hashlib
import json
import threading
from typing import Any, Dict, Optional

import requests


class SessionBootstrapRequired(Exception):
    pass


class SessionManagerError(Exception):
    def __init__(self, detail: Dict[str, Any], status_code: int = 401):
        super().__init__("session manager error")
        self.detail = detail
        self.status_code = status_code


class SessionManager:
    def __init__(self, verify_ssl: bool = False, timeout: int = 20):
        self.verify_ssl = verify_ssl
        self.timeout = timeout
        self._sessions: Dict[str, Dict[str, Any]] = {}
        self._locks: Dict[str, threading.RLock] = {}
        self._locks_guard = threading.Lock()

    @staticmethod
    def user_key_from_cookies(cookies: Dict[str, str]) -> Optional[str]:
        raw_key = cookies.get("id") or cookies.get("_SSID")
        if not raw_key:
            return None
        return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()

    def _get_lock(self, user_key: str) -> threading.RLock:
        with self._locks_guard:
            if user_key not in self._locks:
                self._locks[user_key] = threading.RLock()
            return self._locks[user_key]

    def _get_state(self, user_key: str) -> Dict[str, Any]:
        state = self._sessions.get(user_key)
        if state is None:
            state = {
                "sid": None,
                "synotoken": None,
                "kk_message": None,
                "account": None,
                "base_url": None,
            }
            self._sessions[user_key] = state
        return state

    @staticmethod
    def _error_code(payload: Dict[str, Any]) -> Optional[int]:
        error = payload.get("error")
        if isinstance(error, dict):
            return error.get("code")
        return None

    @staticmethod
    def _safe_json(response: requests.Response) -> Dict[str, Any]:
        try:
            return response.json()
        except Exception:
            return {
                "success": False,
                "http_status": response.status_code,
                "error": {"code": "invalid_json"},
                "_raw": (response.text or "")[:2000],
            }

    @staticmethod
    def _normalize_params(params: Dict[str, Any]) -> Dict[str, Any]:
        normalized: Dict[str, Any] = {}
        for key, value in params.items():
            if isinstance(value, (list, dict)):
                normalized[key] = json.dumps(value)
            else:
                normalized[key] = value
        return normalized

    def update_context(
        self,
        user_key: str,
        *,
        base_url: str,
        kk_message: Optional[str] = None,
        synotoken: Optional[str] = None,
        account: Optional[str] = None,
    ) -> Dict[str, Any]:
        state = self._get_state(user_key)
        state["base_url"] = base_url
        if kk_message:
            state["kk_message"] = kk_message
        if synotoken:
            state["synotoken"] = synotoken
        if account:
            state["account"] = account
        return state

    def _resume(self, user_key: str, cookies: Dict[str, str], base_url: str) -> Dict[str, Any]:
        state = self._get_state(user_key)
        if not state.get("kk_message"):
            raise SessionBootstrapRequired("missing kk_message for resume bootstrap")

        payload = {
            "method": "resume",
            "version": "7",
            "session": "webui",
            "enable_syno_token": "yes",
            "kk_message": state.get("kk_message"),
        }
        if state.get("account"):
            payload["account"] = state.get("account")

        headers = {
            "Referer": f"{base_url}/",
            "Origin": base_url,
            "X-Requested-With": "XMLHttpRequest",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        }
        if state.get("synotoken"):
            headers["X-SYNO-TOKEN"] = state.get("synotoken")

        session = requests.Session()
        session.verify = self.verify_ssl
        session.cookies.update(cookies)
        response = session.post(
            f"{base_url}/webapi/entry.cgi",
            params={"api": "SYNO.API.Auth"},
            data=payload,
            headers=headers,
            timeout=self.timeout,
        )
        data = self._safe_json(response)
        if not data.get("success"):
            raise SessionManagerError({"error": "resume_failed", "resume": data}, status_code=401)

        resume_data = data.get("data") if isinstance(data.get("data"), dict) else {}
        sid = resume_data.get("sid")
        if sid:
            state["sid"] = sid
        state["synotoken"] = resume_data.get("synotoken") or state.get("synotoken")
        state["kk_message"] = resume_data.get("kk_message") or state.get("kk_message")
        state["base_url"] = base_url

        if not state.get("synotoken"):
            raise SessionManagerError(
                {"error": "missing_synotoken_after_resume", "resume": data},
                status_code=401,
            )
        return state

    def ensure_session(self, user_key: str, cookies: Dict[str, str], base_url: str) -> Dict[str, Any]:
        lock = self._get_lock(user_key)
        with lock:
            state = self._get_state(user_key)
            state["base_url"] = base_url
            if not state.get("sid") and not state.get("synotoken"):
                state = self._resume(user_key, cookies, base_url)
            return state

    def call_api(
        self,
        user_key: str,
        cookies: Dict[str, str],
        base_url: str,
        api: str,
        params: Dict[str, Any],
    ) -> Dict[str, Any]:
        lock = self._get_lock(user_key)
        with lock:
            state = self.ensure_session(user_key, cookies, base_url)
            request_params = self._normalize_params(dict(params))
            request_params["api"] = api
            if state.get("sid"):
                request_params["_sid"] = state.get("sid")
            headers = {
                "Referer": f"{base_url}/",
                "Origin": base_url,
                "X-Requested-With": "XMLHttpRequest",
            }
            if state.get("synotoken"):
                headers["X-SYNO-TOKEN"] = state.get("synotoken")

            session = requests.Session()
            session.verify = self.verify_ssl
            session.cookies.update(cookies)
            response = session.get(
                f"{base_url}/webapi/entry.cgi",
                params=request_params,
                headers=headers,
                timeout=self.timeout,
            )
            data = self._safe_json(response)
            if data.get("success"):
                return data

            if self._error_code(data) == 119:
                state["sid"] = None
                state = self._resume(user_key, cookies, base_url)
                if state.get("sid"):
                    request_params["_sid"] = state.get("sid")
                else:
                    request_params.pop("_sid", None)
                if state.get("synotoken"):
                    headers["X-SYNO-TOKEN"] = state.get("synotoken")
                retry_response = session.get(
                    f"{base_url}/webapi/entry.cgi",
                    params=request_params,
                    headers=headers,
                    timeout=self.timeout,
                )
                retry_data = self._safe_json(retry_response)
                if retry_data.get("success"):
                    return retry_data
                raise SessionManagerError(
                    {"error": "api_failed_after_resume", "api": api, "response": retry_data},
                    status_code=401,
                )

            raise SessionManagerError(
                {"error": "api_failed", "api": api, "response": data},
                status_code=401,
            )

    def call_api_post(
        self,
        user_key: str,
        cookies: Dict[str, str],
        base_url: str,
        api: str,
        params: Dict[str, Any],
    ) -> Dict[str, Any]:
        lock = self._get_lock(user_key)
        with lock:
            state = self.ensure_session(user_key, cookies, base_url)
            request_params = self._normalize_params(dict(params))
            request_params["api"] = api
            if state.get("sid"):
                request_params["_sid"] = state.get("sid")
            headers = {
                "Referer": f"{base_url}/",
                "Origin": base_url,
                "X-Requested-With": "XMLHttpRequest",
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            }
            if state.get("synotoken"):
                headers["X-SYNO-TOKEN"] = state.get("synotoken")

            session = requests.Session()
            session.verify = self.verify_ssl
            session.cookies.update(cookies)
            response = session.post(
                f"{base_url}/webapi/entry.cgi",
                data=request_params,
                headers=headers,
                timeout=self.timeout,
            )
            data = self._safe_json(response)
            if data.get("success"):
                return data

            if self._error_code(data) == 119:
                state["sid"] = None
                state = self._resume(user_key, cookies, base_url)
                if state.get("sid"):
                    request_params["_sid"] = state.get("sid")
                else:
                    request_params.pop("_sid", None)
                if state.get("synotoken"):
                    headers["X-SYNO-TOKEN"] = state.get("synotoken")
                retry_response = session.post(
                    f"{base_url}/webapi/entry.cgi",
                    data=request_params,
                    headers=headers,
                    timeout=self.timeout,
                )
                retry_data = self._safe_json(retry_response)
                if retry_data.get("success"):
                    return retry_data
                raise SessionManagerError(
                    {"error": "api_failed_after_resume", "api": api, "response": retry_data},
                    status_code=401,
                )

            raise SessionManagerError(
                {"error": "api_failed", "api": api, "response": data},
                status_code=401,
            )
