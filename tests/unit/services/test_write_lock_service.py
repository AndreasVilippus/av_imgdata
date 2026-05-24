#!/usr/bin/env python3
import os
import sys
import unittest

sys.path.insert(0, os.path.abspath("src"))

from services.write_lock_service import WriteLockService


class WriteLockServiceTests(unittest.TestCase):
    def create_service(self):
        def conflict_error(lock_key, phase, context):
            return RuntimeError({
                "lock_key": lock_key,
                "phase": phase,
                **(context or {}),
            })

        return WriteLockService(conflict_error)

    def test_allows_unrelated_locks_independently(self):
        service = self.create_service()

        with service.acquire("metadata:/a.jpg", phase="left"):
            with service.acquire("metadata:/b.jpg", phase="right"):
                pass

    def test_rejects_same_lock_while_held_with_structured_context(self):
        service = self.create_service()

        with service.acquire("metadata:/a.jpg", phase="metadata_write"):
            with self.assertRaises(RuntimeError) as context:
                with service.acquire(
                    "metadata:/a.jpg",
                    phase="metadata_write",
                    context={"image_path": "/a.jpg"},
                ):
                    pass

        details = context.exception.args[0]
        self.assertEqual(details["lock_key"], "metadata:/a.jpg")
        self.assertEqual(details["phase"], "metadata_write")
        self.assertEqual(details["image_path"], "/a.jpg")

    def test_releases_lock_after_context_exit(self):
        service = self.create_service()

        with service.acquire("metadata:/a.jpg", phase="metadata_write"):
            pass

        with service.acquire("metadata:/a.jpg", phase="metadata_write"):
            pass


if __name__ == "__main__":
    unittest.main()
