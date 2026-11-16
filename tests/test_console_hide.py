# -*- coding: utf-8 -*-
"""Unit tests for bootstrap.hide_own_console."""

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import bootstrap


class FakeKernel32:
    def __init__(self, hwnd=1234, process_count=1):
        self.hwnd = hwnd
        self.process_count = process_count

    def GetConsoleWindow(self):
        return self.hwnd

    def GetConsoleProcessList(self, buffer, size):
        for index in range(min(self.process_count, size)):
            buffer[index] = 1000 + index
        return self.process_count


class FakeUser32:
    def __init__(self):
        self.calls = []

    def ShowWindow(self, hwnd, command):
        self.calls.append((hwnd, command))
        return True


class FailingKernel32:
    def GetConsoleWindow(self):
        raise RuntimeError("console API failure")


class ConsoleHideTests(unittest.TestCase):
    def run_hide(self, kernel32, user32, console_override=None):
        environment = {}
        if console_override is not None:
            environment["PYSHOT_CONSOLE"] = console_override

        with patch.object(
            bootstrap, "_get_console_api", return_value=(kernel32, user32)
        ):
            with patch.dict(os.environ, environment, clear=True):
                status = bootstrap.hide_own_console()

        return status, user32.calls

    def test_owned_console_is_hidden(self):
        status, calls = self.run_hide(
            FakeKernel32(hwnd=4321, process_count=1), FakeUser32()
        )
        self.assertEqual(status, "hidden")
        self.assertEqual(calls, [(4321, 0)])

    def test_shared_console_is_not_hidden(self):
        status, calls = self.run_hide(
            FakeKernel32(hwnd=4321, process_count=3), FakeUser32()
        )
        self.assertEqual(status, "shared")
        self.assertEqual(calls, [])

    def test_missing_console_returns_none(self):
        status, calls = self.run_hide(
            FakeKernel32(hwnd=0, process_count=0), FakeUser32()
        )
        self.assertEqual(status, "none")
        self.assertEqual(calls, [])

    def test_environment_override_keeps_console(self):
        status, calls = self.run_hide(
            FakeKernel32(hwnd=4321, process_count=1),
            FakeUser32(),
            console_override="1",
        )
        self.assertEqual(status, "kept")
        self.assertEqual(calls, [])

    def test_api_exception_returns_error(self):
        status, calls = self.run_hide(FailingKernel32(), FakeUser32())
        self.assertEqual(status, "error")
        self.assertEqual(calls, [])

    def test_main_hides_console_after_dependency_check(self):
        source = (PROJECT_ROOT / "main.py").read_text(encoding="utf-8")
        dependency_check = source.index('"--check-deps" in sys.argv')
        hide_call = source.index("hide_own_console()")
        self.assertGreater(hide_call, dependency_check)


if __name__ == "__main__":
    unittest.main()
