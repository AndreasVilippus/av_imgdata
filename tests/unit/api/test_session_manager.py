#!/usr/bin/env python3
import os
import sys
import unittest
from unittest.mock import patch

import requests

sys.path.insert(0, os.path.abspath("src"))

from api.session_manager import SessionManager, SessionManagerError


class FakeResponse:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload if payload is not None else {"success": True, "data": {}}
        self.text = text

    def json(self):
        return self._payload


class FakeCookies:
    def __init__(self):
        self.values = {}

    def update(self, cookies):
        self.values.update(cookies)
        return None


class FakeSession:
    get_results = []
    post_results = []
    get_calls = []
    post_calls = []
    instances = []

    def __init__(self):
        self.verify = False
        self.cookies = FakeCookies()
        self.closed = False
        self.__class__.instances.append(self)

    def close(self):
        self.closed = True

    def get(self, *args, **kwargs):
        if args:
            kwargs["url"] = args[0]
        self.__class__.get_calls.append(kwargs)
        result = self.__class__.get_results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    def post(self, *args, **kwargs):
        if args:
            kwargs["url"] = args[0]
        self.__class__.post_calls.append(kwargs)
        result = self.__class__.post_results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


def build_manager():
    manager = SessionManager(timeout=1)
    manager._sessions["user"] = {
        "sid": "sid",
        "synotoken": "token",
        "kk_message": "kk",
        "account": None,
        "base_url": "https://example.test",
        "cookies": {},
        "last_seen_at": "",
    }
    return manager


class SessionManagerRetryTests(unittest.TestCase):
    def setUp(self):
        FakeSession.get_results = []
        FakeSession.post_results = []
        FakeSession.get_calls = []
        FakeSession.post_calls = []
        FakeSession.instances = []

    def test_get_retries_once_on_transient_http_status(self):
        FakeSession.get_results = [
            FakeResponse(status_code=503, payload={"success": False, "error": {"code": "temporary"}}),
            FakeResponse(status_code=200, payload={"success": True, "data": {"ok": True}}),
        ]

        with patch("api.session_manager.requests.Session", FakeSession):
            result = build_manager().call_api(
                user_key="user",
                cookies={},
                base_url="https://example.test",
                api="SYNO.Test.Read",
                params={"method": "list"},
            )

        self.assertTrue(result["success"])
        self.assertEqual(len(FakeSession.get_calls), 2)

    def test_get_retries_once_on_timeout(self):
        FakeSession.get_results = [
            requests.Timeout("temporary timeout"),
            FakeResponse(status_code=200, payload={"success": True, "data": {"ok": True}}),
        ]

        with patch("api.session_manager.requests.Session", FakeSession):
            result = build_manager().call_api(
                user_key="user",
                cookies={},
                base_url="https://example.test",
                api="SYNO.Test.Read",
                params={"method": "list"},
            )

        self.assertTrue(result["success"])
        self.assertEqual(len(FakeSession.get_calls), 2)

    def test_post_does_not_retry_on_timeout(self):
        FakeSession.post_results = [requests.Timeout("temporary timeout")]

        with patch("api.session_manager.requests.Session", FakeSession):
            with self.assertRaises(SessionManagerError) as context:
                build_manager().call_api_post(
                    user_key="user",
                    cookies={},
                    base_url="https://example.test",
                    api="SYNO.Test.Write",
                    params={"method": "write"},
                )

        self.assertEqual(len(FakeSession.post_calls), 1)
        self.assertEqual(context.exception.detail["error"], "transient_post_failed")
        self.assertFalse(context.exception.detail["retryable"])
        self.assertEqual(context.exception.detail["attempts"], 1)

    def test_reuses_http_session_for_same_user(self):
        FakeSession.get_results = [
            FakeResponse(status_code=200, payload={"success": True, "data": {"first": True}}),
            FakeResponse(status_code=200, payload={"success": True, "data": {"second": True}}),
        ]
        manager = build_manager()

        with patch("api.session_manager.requests.Session", FakeSession):
            manager.call_api(
                user_key="user",
                cookies={"id": "cookie1"},
                base_url="https://example.test",
                api="SYNO.Test.Read",
                params={"method": "first"},
            )
            manager.call_api(
                user_key="user",
                cookies={"id": "cookie2"},
                base_url="https://example.test",
                api="SYNO.Test.Read",
                params={"method": "second"},
            )

        self.assertEqual(len(FakeSession.instances), 1)
        self.assertEqual(len(FakeSession.get_calls), 2)
        self.assertEqual(FakeSession.instances[0].cookies.values["id"], "cookie2")

    def test_uses_separate_http_sessions_for_different_users(self):
        FakeSession.get_results = [
            FakeResponse(status_code=200, payload={"success": True, "data": {"user": 1}}),
            FakeResponse(status_code=200, payload={"success": True, "data": {"user": 2}}),
        ]
        manager = build_manager()
        manager._sessions["other"] = {
            "sid": "other_sid",
            "synotoken": "other_token",
            "kk_message": "kk",
            "account": None,
            "base_url": "https://example.test",
            "cookies": {},
            "last_seen_at": "",
        }

        with patch("api.session_manager.requests.Session", FakeSession):
            manager.call_api(
                user_key="user",
                cookies={"id": "cookie1"},
                base_url="https://example.test",
                api="SYNO.Test.Read",
                params={"method": "first"},
            )
            manager.call_api(
                user_key="other",
                cookies={"id": "cookie2"},
                base_url="https://example.test",
                api="SYNO.Test.Read",
                params={"method": "second"},
            )

        self.assertEqual(len(FakeSession.instances), 2)
        self.assertEqual(FakeSession.instances[0].cookies.values["id"], "cookie1")
        self.assertEqual(FakeSession.instances[1].cookies.values["id"], "cookie2")

    def test_reset_http_session_closes_and_removes_session(self):
        manager = build_manager()

        with patch("api.session_manager.requests.Session", FakeSession):
            session = manager._get_http_session("user", {"id": "cookie"})
            manager._reset_http_session("user")

        self.assertTrue(session.closed)
        self.assertNotIn("user", manager._http_sessions)


if __name__ == "__main__":
    unittest.main()
