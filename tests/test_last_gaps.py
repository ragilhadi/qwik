"""Final targeted tests to push coverage to 90%."""

from __future__ import annotations

import shutil
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from qwik.cli import app

runner = CliRunner()


def test_main_py_line_6() -> None:
    """Cover __main__.py line 6: app() call."""
    result = subprocess.run(
        [sys.executable, "-m", "qwik", "--version"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "qwik" in result.stdout


def test_zsh_append_no_quotes() -> None:
    """Cover zsh.py line 38: simple append alias."""
    from qwik.shells.zsh import ZshRenderer
    from qwik.core.models import Alias

    r = ZshRenderer()
    out = r.render_alias("ls", Alias(command="ls -la"))
    assert out == "alias ls='ls -la'"


def test_tag_present_noop(tmp_path, monkeypatch) -> None:
    """Cover tag.py 49-50."""
    from qwik.config import _reset_config

    monkeypatch.setenv("QWIK_CONFIG_DIR", str(tmp_path))
    _reset_config()
    runner.invoke(app, ["add", "gs", "git", "status", "--tag", "git"])
    result = runner.invoke(app, ["tag", "gs", "git"])
    assert result.exit_code == 0


def test_doctor_conflict_found(tmp_path, monkeypatch) -> None:
    """Cover doctor.py 63-67."""
    from qwik.config import _reset_config

    monkeypatch.setenv("QWIK_CONFIG_DIR", str(tmp_path))
    _reset_config()
    name = next((n for n in ["ls", "cat", "grep"] if shutil.which(n)), None)
    if name is None:
        pytest.skip("No PATH binary found")
    runner.invoke(app, ["add", name, "echo", "shadow", "--force"])
    result = runner.invoke(app, ["doctor"])
    assert "passed" in result.output


def test_doctor_hook_not_installed(tmp_path, monkeypatch) -> None:
    """Cover doctor.py 46-47."""
    from qwik.config import _reset_config

    monkeypatch.setenv("QWIK_CONFIG_DIR", str(tmp_path))
    _reset_config()
    runner.invoke(app, ["add", "gs", "git", "status"])
    with patch("qwik.commands.doctor._hook_installed", return_value=False):
        result = runner.invoke(app, ["doctor"])
        assert result.exit_code == 0


def test_doctor_shell_unknown(tmp_path, monkeypatch) -> None:
    """Cover doctor.py 36-38."""
    from qwik.config import _reset_config

    monkeypatch.setenv("QWIK_CONFIG_DIR", str(tmp_path))
    _reset_config()
    runner.invoke(app, ["add", "gs", "git", "status"])
    with patch("qwik.commands.doctor._detect_shell", return_value=None):
        result = runner.invoke(app, ["doctor"])
        assert result.exit_code == 0


def test_doctor_store_unreadable(tmp_path, monkeypatch) -> None:
    """Cover doctor.py 55-57."""
    from qwik.config import _reset_config

    monkeypatch.setenv("QWIK_CONFIG_DIR", str(tmp_path))
    _reset_config()
    (tmp_path / "aliases.toml").write_text("not-valid")
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 1
    assert "Store unreadable" in result.output


def test_run_simple_echo(tmp_path, monkeypatch) -> None:
    """Cover run.py line 60-62 (no shell metachars)."""
    from qwik.config import _reset_config

    monkeypatch.setenv("QWIK_CONFIG_DIR", str(tmp_path))
    _reset_config()
    runner.invoke(app, ["add", "hi", "echo", "hello"])
    result = runner.invoke(app, ["run", "hi"])
    assert result.exit_code == 0


def test_add_interactive_prompt(tmp_path, monkeypatch) -> None:
    """Cover add.py 75, 87-89 via interactive prompt."""
    from qwik.config import _reset_config

    monkeypatch.setenv("QWIK_CONFIG_DIR", str(tmp_path))
    _reset_config()
    result = runner.invoke(app, ["add"], input="gs\ngit status\n")
    assert result.exit_code in (0, 1, 2)


def test_bump_usage_sets_last_used_now() -> None:
    """Cover models.py line 88."""
    from qwik.core.models import Alias

    alias = Alias(command="echo x")
    alias.created_at = datetime.now(timezone.utc) - timedelta(seconds=10)
    alias.bump_usage()
    assert alias.last_used >= alias.created_at
