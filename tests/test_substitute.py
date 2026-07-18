"""Unit tests for the substitute engine."""

import shlex

import pytest

from qwik.core.substitute import expand, has_placeholders


class TestHasPlaceholders:
    def test_plain_command(self) -> None:
        assert has_placeholders("git status") is False

    def test_with_positional(self) -> None:
        assert has_placeholders("git checkout {1}") is True

    def test_with_all_args(self) -> None:
        assert has_placeholders("echo {@}") is True

    def test_with_quoted(self) -> None:
        assert has_placeholders("echo {*}") is True

    def test_with_default(self) -> None:
        assert has_placeholders("git push origin {1:-main}") is True

    def test_with_named(self) -> None:
        assert has_placeholders("git checkout {branch}") is True

    def test_with_named_default(self) -> None:
        assert has_placeholders("git checkout {branch:-main}") is True


class TestExpand:
    def test_append_mode_no_args(self) -> None:
        assert expand("git status", []) == "git status"

    def test_append_mode_with_args(self) -> None:
        assert expand("git status", ["--short"]) == "git status --short"

    def test_positional(self) -> None:
        assert expand("git checkout {1}", ["main"]) == "git checkout main"

    def test_all_args(self) -> None:
        assert (
            expand('git commit -m "chore: {@}"', ["init", "version"])
            == 'git commit -m "chore: init version"'
        )

    def test_default_present(self) -> None:
        assert (
            expand("git push origin {1:-main}", ["feat/x"]) == "git push origin feat/x"
        )

    def test_default_missing(self) -> None:
        assert expand("git push origin {1:-main}", []) == "git push origin main"

    def test_surplus_appended(self) -> None:
        assert expand("kubectl {1}", ["get", "pods"]) == "kubectl get pods"

    def test_missing_arg_raises(self) -> None:
        with pytest.raises(ValueError):
            expand("git checkout {1}", [])

    def test_missing_arg_with_default_no_raise(self) -> None:
        # Should not raise because there is a default
        assert expand("echo {1:-world}", []) == "echo world"

    def test_zero_placeholder_raises(self) -> None:
        """{0} is invalid (positional placeholders are 1-based per PRD §6.3)."""
        with pytest.raises(ValueError):
            expand("echo {0}", [])

    def test_zero_placeholder_with_args_raises(self) -> None:
        with pytest.raises(ValueError):
            expand("echo {0}", ["a"])

    def test_zero_default_placeholder_raises(self) -> None:
        with pytest.raises(ValueError):
            expand("echo {0:-default}", [])


class TestQuoting:
    def test_positional_metachar_is_quoted(self) -> None:
        assert expand("git checkout {1}", ["; rm -rf /"]) == f"git checkout {shlex.quote('; rm -rf /')}"

    def test_default_metachar_is_quoted(self) -> None:
        assert expand("echo {1:-x}", []) == "echo x"
        assert expand("echo {1:-; rm -rf /}", []) == f"echo {shlex.quote('; rm -rf /')}"

    def test_all_args_metachar_is_quoted(self) -> None:
        out = expand("echo {@}", ["a", "; rm", "b"])
        assert out == f"echo {shlex.quote('a')} {shlex.quote('; rm')} {shlex.quote('b')}"

    def test_positional_normal_stays_unquoted(self) -> None:
        assert expand("git checkout {1}", ["main"]) == "git checkout main"

    def test_default_normal_stays_unquoted(self) -> None:
        assert expand("git push origin {1:-main}", ["feat/x"]) == "git push origin feat/x"

    def test_all_args_normal_stays_unquoted(self) -> None:
        assert expand("echo {@}", ["a", "b"]) == "echo a b"


from qwik.core.substitute import _named_placeholder_index_map


class TestNamedIndexMap:
    def test_single_name(self) -> None:
        assert _named_placeholder_index_map("git checkout {branch}") == {"branch": 1}

    def test_two_names_order_of_appearance(self) -> None:
        assert _named_placeholder_index_map('git commit -m "{type}: {scope}"') == {
            "type": 1,
            "scope": 2,
        }

    def test_repeated_name_reuses_index(self) -> None:
        assert _named_placeholder_index_map("echo {a} {a}") == {"a": 1}

    def test_mixed_named_and_numeric(self) -> None:
        assert _named_placeholder_index_map("echo {1} {name}") == {"name": 2}

    def test_named_with_default_uses_name(self) -> None:
        assert _named_placeholder_index_map("git checkout {branch:-main}") == {"branch": 1}

    def test_no_names_returns_empty(self) -> None:
        assert _named_placeholder_index_map("git status") == {}

    def test_only_numeric_returns_empty(self) -> None:
        assert _named_placeholder_index_map("git checkout {1}") == {}

    def test_invalid_braces_are_literals(self) -> None:
        assert _named_placeholder_index_map("echo {123bad}") == {}
        assert _named_placeholder_index_map("echo {bad name}") == {}
        assert _named_placeholder_index_map("echo {$$$}") == {}


class TestNamedExpand:
    def test_single_name_substitutes_first_arg(self) -> None:
        assert expand("git checkout {branch}", ["main"]) == "git checkout main"

    def test_two_names_substitute_in_order(self) -> None:
        assert expand('git commit -m "{type}: {scope}"', ["feat", "login"]) == \
            'git commit -m "feat: login"'

    def test_repeated_name_reuses_same_arg(self) -> None:
        assert expand("echo {a} and {a}", ["x", "y"]) == "echo x and x y"

    def test_named_default_used_when_arg_missing(self) -> None:
        assert expand("git checkout {branch:-main}", []) == "git checkout main"

    def test_named_default_overridden_by_arg(self) -> None:
        assert expand("git checkout {branch:-main}", ["feature/x"]) == "git checkout feature/x"

    def test_mixed_numeric_and_named(self) -> None:
        assert expand("echo {1} {name}", ["a", "b"]) == "echo a b"

    def test_named_missing_no_default_raises(self) -> None:
        with pytest.raises(ValueError):
            expand("git checkout {branch}", [])

    def test_named_zero_is_not_a_placeholder(self) -> None:
        assert expand("echo {0bad}", ["x"]) == "echo {0bad} x"

    def test_named_metachar_is_quoted(self) -> None:
        out = expand("git checkout {branch}", ["; rm -rf /"])
        assert out == f"git checkout {shlex.quote('; rm -rf /')}"

    def test_named_default_metachar_is_quoted(self) -> None:
        out = expand("echo {branch:-; rm -rf /}", [])
        assert out == f"echo {shlex.quote('; rm -rf /')}"

    def test_named_with_surplus_appended(self) -> None:
        assert expand("kubectl {verb}", ["get", "pods"]) == "kubectl get pods"
