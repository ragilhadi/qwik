"""Unit tests for conflict detection."""

import pytest

from qwik.core.conflicts import ConflictChecker, SHELL_BUILTINS, is_builtin
from qwik.core.models import Alias, AliasStore


class TestConflictChecker:
    def test_new_name_is_safe(self) -> None:
        store = AliasStore()
        checker = ConflictChecker(store)
        result = checker.check("newalias")
        assert result.is_safe is True
        assert result.needs_warning is False

    def test_existing_alias(self) -> None:
        store = AliasStore()
        store.add("gs", Alias(command="git status"))
        checker = ConflictChecker(store)
        result = checker.check("gs")
        assert result.existing_alias is True
        assert result.is_safe is False

    def test_shell_builtin(self) -> None:
        store = AliasStore()
        checker = ConflictChecker(store)
        result = checker.check("cd")
        assert result.is_builtin is True
        assert result.is_safe is False

    def test_invalid_syntax(self) -> None:
        store = AliasStore()
        checker = ConflictChecker(store)
        result = checker.check("my alias")
        assert result.valid_syntax is False
        assert result.is_safe is False


class TestBuiltinsSet:
    def test_cd_present(self) -> None:
        from qwik.core.conflicts import is_builtin

        assert is_builtin("cd") is True

    def test_echo_present(self) -> None:
        from qwik.core.conflicts import is_builtin

        assert is_builtin("echo") is True


class TestShellSpecificBuiltins:
    def test_zsh_setopt(self) -> None:
        from qwik.core.conflicts import is_builtin

        assert is_builtin("setopt", "zsh") is True

    def test_zsh_setopt_not_bash(self) -> None:
        from qwik.core.conflicts import is_builtin

        assert is_builtin("setopt", "bash") is False

    def test_fish_abbr(self) -> None:
        from qwik.core.conflicts import is_builtin

        assert is_builtin("abbr", "fish") is True

    def test_fish_abbr_not_bash(self) -> None:
        from qwik.core.conflicts import is_builtin

        assert is_builtin("abbr", "bash") is False

    def test_pwsh_write_output(self) -> None:
        from qwik.core.conflicts import is_builtin

        # The long-form cmdlet name is not a realistic alias-name
        # collision (nobody names an alias "Write-Output"); the set is
        # built from the short default aliases users actually type.
        assert is_builtin("Write-Output", "pwsh") is False
        assert is_builtin("echo", "pwsh") is True
        assert is_builtin("write", "pwsh") is True

    def test_cmd_dir(self) -> None:
        from qwik.core.conflicts import is_builtin

        assert is_builtin("dir", "cmd") is True

    def test_cmd_dir_not_bash(self) -> None:
        from qwik.core.conflicts import is_builtin

        assert is_builtin("dir", "bash") is False


class TestConflictCheckerShellParam:
    def test_check_uses_shell_param(self) -> None:
        store = AliasStore()
        checker = ConflictChecker(store)
        zsh_result = checker.check("setopt", shell="zsh")
        bash_result = checker.check("setopt", shell="bash")
        assert zsh_result.is_builtin is True
        assert bash_result.is_builtin is False

    def test_check_defaults_to_bash(self) -> None:
        store = AliasStore()
        checker = ConflictChecker(store)
        result = checker.check("setopt")
        assert result.is_builtin is False


def test_is_builtin_defaults_to_bash():
    from qwik.core.conflicts import is_builtin

    assert is_builtin("cd") is True
    assert is_builtin("nope-not-real") is False


class TestCaseSensitivity:
    """cmd.exe and PowerShell resolve names case-insensitively; bash, zsh,
    and fish do not — `CD` and `cd` are genuinely different commands
    there."""

    @pytest.mark.parametrize(
        "shell,name",
        [
            ("cmd", "cd"), ("cmd", "CD"), ("cmd", "Cd"), ("cmd", "cD"),
            ("cmd", "echo"), ("cmd", "ECHO"),
            ("cmd", "dir"), ("cmd", "DIR"), ("cmd", "Dir"),
            ("pwsh", "ls"), ("pwsh", "LS"), ("pwsh", "Ls"),
            ("pwsh", "cd"), ("pwsh", "CD"),
            ("pwsh", "cat"), ("pwsh", "CAT"),
            ("pwsh", "rm"), ("pwsh", "RM"),
            ("pwsh", "cp"), ("pwsh", "mv"), ("pwsh", "pwd"),
            ("pwsh", "echo"), ("pwsh", "select"), ("pwsh", "where"),
        ],
    )
    def test_case_insensitive_shells_match_any_case(self, shell, name) -> None:
        assert is_builtin(name, shell) is True

    @pytest.mark.parametrize("shell", ["bash", "zsh", "fish"])
    def test_posix_shells_stay_case_sensitive(self, shell) -> None:
        assert is_builtin("cd", shell) is True
        assert is_builtin("CD", shell) is False
        assert is_builtin("Cd", shell) is False

    @pytest.mark.parametrize("shell", ["nu", "xonsh"])
    def test_nu_and_xonsh_stay_case_sensitive(self, shell) -> None:
        assert is_builtin("cd", shell) is True
        assert is_builtin("CD", shell) is False


class TestNuAndXonshOwnBuiltinSets:
    def test_nu_has_its_own_set(self) -> None:
        assert is_builtin("cd", "nu") is True
        assert is_builtin("each", "nu") is True
        # bash-only builtins must not leak into nu's set via a fallback.
        assert is_builtin("shopt", "nu") is False

    def test_xonsh_has_its_own_set(self) -> None:
        assert is_builtin("cd", "xonsh") is True
        assert is_builtin("import", "xonsh") is True
        assert is_builtin("shopt", "xonsh") is False

    def test_nu_and_xonsh_are_distinct_sets(self) -> None:
        assert SHELL_BUILTINS["nu"] != SHELL_BUILTINS["bash"]
        assert SHELL_BUILTINS["xonsh"] != SHELL_BUILTINS["bash"]
        assert SHELL_BUILTINS["nu"] is not SHELL_BUILTINS["bash"]


class TestUnknownShellName:
    def test_unrecognized_shell_is_not_silently_bash(self) -> None:
        # A typo'd or unsupported shell name must not be treated as "no
        # shell detected" (which falls back to bash) — that would let a
        # bash builtin silently pass or fail for a shell qwik knows
        # nothing about.
        assert is_builtin("cd", "not-a-real-shell") is False
        assert is_builtin("shopt", "not-a-real-shell") is False

    def test_none_still_falls_back_to_bash(self) -> None:
        assert is_builtin("cd", None) is True
        assert is_builtin("shopt", None) is True
