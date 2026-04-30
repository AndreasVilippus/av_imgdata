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
    def update(self, _cookies):
        return None


class FakeSession:
    get_results = []
    post_results = []
    get_calls = []
    post_calls = []

    def __init__(self):
        self.verify = False
        self.cookies = FakeCookies()

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


if __name__ == "__main__":
    unittest.main()
