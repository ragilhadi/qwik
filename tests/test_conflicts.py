"""Unit tests for conflict detection."""

from qwik.core.conflicts import ConflictChecker, SHELL_BUILTINS
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
        assert "cd" in SHELL_BUILTINS

    def test_echo_present(self) -> None:
        assert "echo" in SHELL_BUILTINS
