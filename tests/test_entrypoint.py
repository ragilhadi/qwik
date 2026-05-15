"""Tests for the __main__.py entrypoint."""

from __future__ import annotations

import subprocess
import sys


class TestEntrypoint:
    def test_main_entrypoint(self) -> None:
        import qwik.__main__ as m

        assert hasattr(m, "app")

    def test_main_py_line_6(self) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "qwik", "--version"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "qwik" in result.stdout

    def test_main_executes(self) -> None:
        import qwik.__main__ as m

        assert callable(m.app)

    def test_main_module_executes(self) -> None:
        import qwik.__main__ as m

        assert callable(m.app)
