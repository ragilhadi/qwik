"""Unit tests for qwik.core.shell_exec.build_invocation.

subprocess.run(cmd, shell=True) does not run the user's actual shell: on
POSIX it always uses /bin/sh, and on Windows it always uses cmd.exe
(COMSPEC) regardless of what's detected. That's fine for POSIX shells and
for "cmd" (their quoting rules match), but wrong for "pwsh" — a
PowerShell-quoted string handed to cmd.exe would be quoting for an
interpreter that never sees it, so pwsh needs an explicit interpreter.
"""

from __future__ import annotations

from unittest import mock

from qwik.core.shell_exec import build_invocation


class TestBuildInvocation:
    def test_posix_shell_uses_native_shell_true(self) -> None:
        for shell in ("bash", "zsh", "fish", "nu", "xonsh", None):
            cmd, use_shell = build_invocation("git status", shell)
            assert cmd == "git status"
            assert use_shell is True

    def test_cmd_uses_native_shell_true(self) -> None:
        # shell=True on Windows already invokes cmd.exe (COMSPEC), which
        # is exactly what quote_for_shell(..., "cmd") targets.
        cmd, use_shell = build_invocation("git status", "cmd")
        assert cmd == "git status"
        assert use_shell is True

    def test_pwsh_invokes_powershell_explicitly(self) -> None:
        with mock.patch("qwik.core.shell_exec.shutil.which", return_value=None):
            cmd, use_shell = build_invocation("git status", "pwsh")
        assert use_shell is False
        assert isinstance(cmd, list)
        assert cmd[0] == "powershell"
        assert "-Command" in cmd
        assert cmd[-1] == "git status"

    def test_pwsh_prefers_pwsh_executable_when_available(self) -> None:
        with mock.patch(
            "qwik.core.shell_exec.shutil.which",
            side_effect=lambda name: "/usr/bin/pwsh" if name == "pwsh" else None,
        ):
            cmd, use_shell = build_invocation("git status", "pwsh")
        assert use_shell is False
        assert cmd[0] == "pwsh"
