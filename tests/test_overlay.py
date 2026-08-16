"""Tests for qwik overlay commands."""

from __future__ import annotations

from unittest.mock import patch

from typer.testing import CliRunner

from qwik.cli import app

runner = CliRunner()


def _setup_store(tmp_path, monkeypatch):
    from qwik.config import _reset_config

    monkeypatch.setenv("QWIK_CONFIG_DIR", str(tmp_path))
    _reset_config()
    runner.invoke(app, ["add", "gs", "git", "status"])


def test_overlay_add_without_git_fails(tmp_path, monkeypatch):
    _setup_store(tmp_path, monkeypatch)
    with patch("qwik.commands.overlay.git_available", return_value=False):
        result = runner.invoke(app, ["overlay", "add", "https://github.com/team/aliases"])
    assert result.exit_code == 1
    assert "git not found" in result.output


def test_overlay_list_no_overlay(tmp_path, monkeypatch):
    _setup_store(tmp_path, monkeypatch)
    result = runner.invoke(app, ["overlay", "list"])
    assert result.exit_code == 0
    assert "No overlay configured" in result.output


def test_overlay_remove_no_overlay(tmp_path, monkeypatch):
    _setup_store(tmp_path, monkeypatch)
    result = runner.invoke(app, ["overlay", "remove"])
    assert result.exit_code == 1
    assert "No overlay configured" in result.output


def test_overlay_copy_not_overlay_alias(tmp_path, monkeypatch):
    _setup_store(tmp_path, monkeypatch)
    result = runner.invoke(app, ["overlay", "copy", "gs"])
    assert result.exit_code == 1
    assert "not an overlay alias" in result.output.lower() or "not found" in result.output.lower()
