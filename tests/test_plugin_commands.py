"""Tests for entry-point-based CLI command plugin discovery."""

from __future__ import annotations

from typer.testing import CliRunner

from qwik.cli import app

runner = CliRunner()


def test_builtin_commands_registered() -> None:
    """All built-in commands should be present in the app."""
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    commands = [
        "add",
        "list",
        "show",
        "edit",
        "rename",
        "rm",
        "run",
        "search",
        "pick",
        "init",
        "doctor",
    ]
    for cmd in commands:
        assert cmd in result.output


def test_discover_plugin_commands_does_not_crash() -> None:
    """Plugin discovery should handle no plugins gracefully."""
    from qwik.cli import _discover_plugin_commands

    _discover_plugin_commands()
