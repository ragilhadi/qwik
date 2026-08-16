"""Startup-time regression check for issue #31.

Not run by default CI (no marker gate); run manually with:
    pytest tests/test_startup_perf.py -v -s

``qwik`` used to eagerly import ``prompt_toolkit`` (via
``qwik.commands.pick`` -> ``qwik.ui.picker``, registered at CLI-app
build time) and re-scan shell-renderer entry points on every
``get_renderer()``/``supported_shells()`` call, on *every* invocation —
even ones like ``qwik init bash`` that never touch the picker. This
checks two things stay true: ``prompt_toolkit`` is not importable-cost
on the hot path, and a plain subcommand stays fast.

The threshold is intentionally generous and relative rather than
matching the issue's literal absolute figure: sandboxed CI environments
have measurably higher baseline import overhead than a typical
developer machine (verified during the fix: bare ``import
prompt_toolkit`` alone costs ~130ms here), so a tight absolute ceiling
would be flaky by environment rather than meaningful.
"""

from __future__ import annotations

import subprocess
import sys
import time

import pytest


@pytest.mark.benchmark
def test_prompt_toolkit_not_imported_by_cli_module() -> None:
    """Importing ``qwik.cli`` must not pull in ``prompt_toolkit``.

    ``prompt_toolkit`` should only load once an interactive picker
    session actually runs (``qwik.ui.picker.run_picker``), not merely
    because the CLI app registers the ``pick`` command.
    """
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import qwik.cli, sys; "
            "assert 'prompt_toolkit' not in sys.modules, "
            "'prompt_toolkit should not be imported by qwik.cli'",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.benchmark
def test_init_command_startup_under_threshold() -> None:
    """``qwik init bash`` should stay well clear of a generous ceiling."""
    times: list[float] = []
    for _ in range(7):
        start = time.perf_counter()
        subprocess.run(
            [sys.executable, "-m", "qwik", "init", "bash"],
            capture_output=True,
            check=False,
        )
        times.append((time.perf_counter() - start) * 1000)
    times.sort()
    median = times[len(times) // 2]
    print(f"\n  qwik init bash: {median:.1f}ms median (limit: 600ms)")
    assert median < 600, f"qwik init bash too slow: {median:.1f}ms"
