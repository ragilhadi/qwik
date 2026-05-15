"""Unit tests for the substitute engine."""

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
