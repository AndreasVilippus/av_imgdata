#!/usr/bin/env python3
import os
import sys
import unittest

sys.path.insert(0, os.path.abspath("src"))

from imgdata import WriteDebouncer


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


class WriteDebouncerTests(unittest.TestCase):
    def test_flushes_first_new_entry(self):
        clock = FakeClock()
        debouncer = WriteDebouncer(60, 25, now_func=clock)

        self.assertTrue(debouncer.should_flush(entry_count=1))

    def test_does_not_flush_without_new_entries(self):
        clock = FakeClock()
        debouncer = WriteDebouncer(60, 25, now_func=clock)
        debouncer.mark_flushed(5)
        clock.now = 120.0

        self.assertFalse(debouncer.should_flush(entry_count=5))

    def test_flushes_after_entry_delta(self):
        clock = FakeClock()
        debouncer = WriteDebouncer(60, 25, now_func=clock)
        debouncer.mark_flushed(5)
        clock.now = 1.0

        self.assertTrue(debouncer.should_flush(entry_count=30))

    def test_flushes_after_time_interval(self):
        clock = FakeClock()
        debouncer = WriteDebouncer(60, 25, now_func=clock)
        debouncer.mark_flushed(5)
        clock.now = 59.0
        self.assertFalse(debouncer.should_flush(entry_count=6))

        clock.now = 60.0
        self.assertTrue(debouncer.should_flush(entry_count=6))

    def test_force_flushes_even_without_entries(self):
        clock = FakeClock()
        debouncer = WriteDebouncer(60, 25, now_func=clock)

        self.assertTrue(debouncer.should_flush(force=True, entry_count=0))


if __name__ == "__main__":
    unittest.main()
