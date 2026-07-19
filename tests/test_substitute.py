"""Unit tests for the substitute engine."""

import shlex

import pytest

from qwik.core.substitute import (
    expand,
    find_unrecognized_braces,
    has_placeholders,
    validate_placeholders_static,
)


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


class TestMalformedPlaceholders:
    """Malformed ``{...}`` spans are rejected at add-time, not silently literal.

    The heuristic (documented in ``find_unrecognized_braces``): a ``{...}`` span
    not matched by ``_PLACEHOLDER_RE`` is rejected only when it *looks like a
    placeholder attempt* — i.e. its inner text contains one of ``:-``, ``@``,
    ``*``, or starts with a digit/letter/underscore. Pure-punctuation spans
    (``{$$$}``, ``{}``, ``{ }``) and unclosed braces are left as literals.
    """

    REJECT_CASES = [
        "echo {bad name}",
        "echo {1foo}",
        "echo {@x}",
        "echo {1:}",
    ]
    ACCEPT_LITERAL_CASES = [
        "echo {}",
        "echo {}:-x}",
        "echo {$$$}",
        "echo { not closed",
    ]

    @pytest.mark.parametrize("command", REJECT_CASES)
    def test_validate_rejects_malformed(self, command: str) -> None:
        with pytest.raises(ValueError) as exc_info:
            validate_placeholders_static(command)
        msg = str(exc_info.value)
        assert "placeholder" in msg.lower()
        assert command in msg

    @pytest.mark.parametrize("command", ACCEPT_LITERAL_CASES)
    def test_validate_accepts_literal_spans(self, command: str) -> None:
        # These look like literal braces / punctuation, not placeholder attempts.
        validate_placeholders_static(command)

    def test_validate_reports_first_offending_token(self) -> None:
        command = "echo {bad name} then {1foo}"
        with pytest.raises(ValueError) as exc_info:
            validate_placeholders_static(command)
        assert "{bad name}" in str(exc_info.value)

    def test_find_returns_offending_spans(self) -> None:
        spans = find_unrecognized_braces("echo {bad name} and {1foo}")
        assert spans == ["{bad name}", "{1foo}"]

    def test_find_ignores_valid_placeholders(self) -> None:
        valid = "git checkout {1} {@} {*} {name} {1:-x} {name:-y}"
        assert find_unrecognized_braces(valid) == []

    def test_find_ignores_pure_punctuation_braces(self) -> None:
        assert find_unrecognized_braces("echo {$$$}") == []
        assert find_unrecognized_braces("echo {}") == []
        assert find_unrecognized_braces("echo { }") == []

    def test_find_ignores_unclosed_brace(self) -> None:
        assert find_unrecognized_braces("echo { not closed") == []

    def test_find_ignores_nested_literal_braces(self) -> None:
        # ``{{1}}`` — the inner ``{1}`` is a valid placeholder; the outer
        # brace pair does not form a separate ``{...}`` span. No rejection.
        assert find_unrecognized_braces("echo {{1}}") == []

    @pytest.mark.parametrize("command", REJECT_CASES)
    def test_add_rejects_malformed_cli(
        self, tmp_path, monkeypatch, command: str
    ) -> None:
        from qwik.config import _reset_config
        from typer.testing import CliRunner

        from qwik.cli import app

        monkeypatch.setenv("QWIK_CONFIG_DIR", str(tmp_path))
        _reset_config()
        result = CliRunner().invoke(app, ["add", "bad", command])
        assert result.exit_code == 1
        assert "Traceback" not in result.output
        # The offending token should appear in the surfaced error.
        for token in ("bad name", "1foo", "@x", "1:"):
            if token in command:
                assert token in result.output
                break

    @pytest.mark.parametrize("command", ACCEPT_LITERAL_CASES)
    def test_add_accepts_literal_cli(
        self, tmp_path, monkeypatch, command: str
    ) -> None:
        from qwik.config import _reset_config
        from typer.testing import CliRunner

        from qwik.cli import app

        monkeypatch.setenv("QWIK_CONFIG_DIR", str(tmp_path))
        _reset_config()
        result = CliRunner().invoke(app, ["add", "lit", command])
        assert result.exit_code == 0, f"exit={result.exit_code} out={result.output!r}"
        assert "Added" in result.output
