"""Unit tests for qwik.core.shell_detect.

detect_shell() used to be POSIX-only (`$SHELL` + `/proc`), so it always
returned None on Windows and could never identify cmd, nu, or xonsh at
all. These tests mock the environment (and, for the Windows-only paths,
`sys.platform`) rather than requiring the real OS/shell, since CI doesn't
run every shell on every platform.
"""

from __future__ import annotations

import sys
from unittest import mock

import pytest

from qwik.core import shell_detect as sd

_ALL_DETECTION_ENV_VARS = (
    "SHELL",
    "QWIK_SHELL",
    "NU_VERSION",
    "XONSH_VERSION",
    "PSModulePath",
    "PROMPT",
)


@pytest.fixture
def clean_env(monkeypatch):
    """Remove every signal detect_shell looks at."""
    for var in _ALL_DETECTION_ENV_VARS:
        monkeypatch.delenv(var, raising=False)
    return monkeypatch


class TestOverride:
    def test_qwik_shell_override_wins(self, clean_env) -> None:
        clean_env.setenv("QWIK_SHELL", "nu")
        clean_env.setenv("SHELL", "/bin/bash")
        assert sd.detect_shell() == "nu"

    def test_qwik_shell_override_case_insensitive(self, clean_env) -> None:
        clean_env.setenv("QWIK_SHELL", "PWSH")
        assert sd.shell_name_from_override() == "pwsh"

    def test_qwik_shell_unknown_value_ignored(self, clean_env) -> None:
        clean_env.setenv("QWIK_SHELL", "not-a-real-shell")
        assert sd.shell_name_from_override() is None


class TestVersionEnv:
    def test_nu_version_detected(self, clean_env) -> None:
        clean_env.setenv("NU_VERSION", "0.90.0")
        assert sd.detect_shell() == "nu"

    def test_xonsh_version_detected(self, clean_env) -> None:
        clean_env.setenv("XONSH_VERSION", "0.14.0")
        assert sd.detect_shell() == "xonsh"

    def test_version_env_wins_over_stale_shell(self, clean_env) -> None:
        # nu/xonsh often inherit $SHELL unchanged from whatever launched
        # them, so it can misreport the shell actually running.
        clean_env.setenv("SHELL", "/bin/bash")
        clean_env.setenv("NU_VERSION", "0.90.0")
        assert sd.detect_shell() == "nu"


class TestShellNameFromEnv:
    @pytest.mark.parametrize(
        "shell_path,expected",
        [
            ("/bin/bash", "bash"),
            ("/usr/bin/zsh", "zsh"),
            ("/usr/local/bin/fish", "fish"),
            ("/usr/bin/pwsh", "pwsh"),
            ("C:\\Program Files\\PowerShell\\7\\pwsh.exe", "pwsh"),
        ],
    )
    def test_known_shells(self, clean_env, shell_path, expected) -> None:
        clean_env.setenv("SHELL", shell_path)
        assert sd.shell_name_from_env() == expected

    def test_unset(self, clean_env) -> None:
        assert sd.shell_name_from_env() is None

    def test_unrecognized(self, clean_env) -> None:
        clean_env.setenv("SHELL", "/bin/dash")
        assert sd.shell_name_from_env() is None


class TestWindowsDetection:
    """`detect_shell()` on Windows, mocked since we're not on one."""

    def test_pwsh_via_psmodulepath(self, clean_env) -> None:
        clean_env.setenv("PSModulePath", r"C:\Program Files\WindowsPowerShell\Modules")
        with mock.patch.object(sys, "platform", "win32"):
            assert sd.detect_shell() == "pwsh"

    def test_cmd_via_prompt(self, clean_env) -> None:
        clean_env.setenv("PROMPT", "$P$G")
        with mock.patch.object(sys, "platform", "win32"):
            assert sd.detect_shell() == "cmd"

    def test_psmodulepath_takes_precedence_over_prompt(self, clean_env) -> None:
        # A pwsh session can still have PROMPT set by an ancestor cmd;
        # PSModulePath is the more specific, authoritative signal.
        clean_env.setenv("PSModulePath", r"C:\Modules")
        clean_env.setenv("PROMPT", "$P$G")
        with mock.patch.object(sys, "platform", "win32"):
            assert sd.detect_shell() == "pwsh"

    def test_no_signals_falls_back_to_none_without_crashing(self, clean_env) -> None:
        # No env heuristics match, and the ToolHelp32 process walk finds
        # no classifiable ancestor — must not raise. The walk itself is
        # stubbed out here rather than left to fail on its own: on a
        # non-Windows CI runner it fails because `ctypes.windll` doesn't
        # exist, but on a *real* Windows runner it succeeds and walks the
        # actual process tree — which, inside a CI job, has a genuine
        # shell (e.g. pwsh.exe, since that's what runs the job step) as
        # an ancestor. Relying on that accidental failure made this test
        # platform-dependent instead of actually testing "no signals".
        with (
            mock.patch.object(sys, "platform", "win32"),
            mock.patch.object(sd, "_shell_name_from_windows_parent_process", return_value=None),
        ):
            assert sd.detect_shell() is None

    def test_shell_env_not_consulted_on_windows_when_absent(self, clean_env) -> None:
        # $SHELL is a POSIX convention; genuine Windows sessions don't set
        # it, so detection must not depend on it being present.
        with (
            mock.patch.object(sys, "platform", "win32"),
            mock.patch.object(sd, "_shell_name_from_windows_parent_process", return_value=None),
        ):
            assert "SHELL" not in __import__("os").environ
            assert sd.detect_shell() is None

    def test_classify_exe_name_short_names_require_exact_match(self) -> None:
        # "nu" and "cmd" are short enough to false-positive as substrings
        # (e.g. "menu.exe", "runuser") — only an exact basename counts.
        assert sd._classify_exe_name("menu.exe") is None
        assert sd._classify_exe_name("runuser") is None
        assert sd._classify_exe_name("nu.exe") == "nu"
        assert sd._classify_exe_name("cmd.exe") == "cmd"

    def test_classify_exe_name_longer_names_substring_ok(self) -> None:
        assert sd._classify_exe_name("git-bash.exe") == "bash"
        assert sd._classify_exe_name("pwsh.exe") == "pwsh"
        assert sd._classify_exe_name("powershell.exe") == "pwsh"
        assert sd._classify_exe_name("xonsh.exe") == "xonsh"


class TestMacDetection:
    def test_falls_back_to_ps_not_only_shell_env(self, clean_env, monkeypatch) -> None:
        # macOS has no /proc; detection must not depend solely on $SHELL.
        def fake_run(*args, **kwargs):
            import subprocess as _sp

            return _sp.CompletedProcess(args, 0, stdout="fish\n", stderr="")

        monkeypatch.setattr(sd.subprocess, "run", fake_run)
        with mock.patch.object(sys, "platform", "darwin"):
            assert sd.shell_name_from_proc() == "fish"

    def test_ps_failure_returns_none(self, clean_env, monkeypatch) -> None:
        def fake_run(*args, **kwargs):
            raise FileNotFoundError("no ps")

        monkeypatch.setattr(sd.subprocess, "run", fake_run)
        with mock.patch.object(sys, "platform", "darwin"):
            assert sd.shell_name_from_proc() is None


class TestSupportedShellsCoverage:
    def test_all_renderer_shells_are_known(self) -> None:
        from qwik.shells.base import supported_shells

        for shell in supported_shells():
            assert shell in sd._KNOWN_SHELLS
