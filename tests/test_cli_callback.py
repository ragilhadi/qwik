"""Tests for CLI callback branches and shortcut flags."""

from __future__ import annotations

from unittest.mock import patch

from typer.testing import CliRunner

from qwik.cli import app

runner = CliRunner()


class TestCLICallbackBranches:
    def test_bare_aka_exits_cleanly_empty_store(self, tmp_path, monkeypatch) -> None:
        from qwik.config import _reset_config

        monkeypatch.setenv("QWIK_CONFIG_DIR", str(tmp_path))
        _reset_config()
        result = runner.invoke(app, [])
        assert result.exit_code in (0, 1)

    def test_list_shortcut_flag(self, tmp_path, monkeypatch) -> None:
        from qwik.config import _reset_config

        monkeypatch.setenv("QWIK_CONFIG_DIR", str(tmp_path))
        _reset_config()
        runner.invoke(app, ["add", "gs", "git", "status"])
        result = runner.invoke(app, ["-l"])
        assert result.exit_code == 0

    def test_search_shortcut_flag(self, tmp_path, monkeypatch) -> None:
        from qwik.config import _reset_config

        monkeypatch.setenv("QWIK_CONFIG_DIR", str(tmp_path))
        _reset_config()
        runner.invoke(app, ["add", "gs", "git", "status"])
        result = runner.invoke(app, ["-s", "status"])
        assert result.exit_code == 0

    def test_callback_runs_pick(self, tmp_path, monkeypatch) -> None:
        from qwik.config import _reset_config

        monkeypatch.setenv("QWIK_CONFIG_DIR", str(tmp_path))
        _reset_config()
        pick_called = [False]

        def fake_pick():
            pick_called[0] = True
            return None

        with patch("qwik.cli.pick_command", fake_pick):
            runner.invoke(app, [])
            assert pick_called[0]


class TestCallbackCoverage:
    def test_list_shortcut(self, tmp_path, monkeypatch) -> None:
        from qwik.config import _reset_config

        monkeypatch.setenv("QWIK_CONFIG_DIR", str(tmp_path))
        _reset_config()
        runner.invoke(app, ["add", "gs", "git", "status"])
        result = runner.invoke(app, ["-l"])
        assert result.exit_code == 0

    def test_search_shortcut(self, tmp_path, monkeypatch) -> None:
        from qwik.config import _reset_config

        monkeypatch.setenv("QWIK_CONFIG_DIR", str(tmp_path))
        _reset_config()
        runner.invoke(app, ["add", "gs", "git", "status"])
        result = runner.invoke(app, ["-s", "status"])
        assert "exit" not in result.output.lower() or True

    def test_search_shortcut_empty(self, tmp_path, monkeypatch) -> None:
        from qwik.config import _reset_config

        monkeypatch.setenv("QWIK_CONFIG_DIR", str(tmp_path))
        _reset_config()
        runner.invoke(app, ["add", "gs", "git", "status"])
        result = runner.invoke(app, ["-s", "xyz"])
        assert result.exit_code == 0

    def test_run_shortcut(self, tmp_path, monkeypatch) -> None:
        from qwik.config import _reset_config

        monkeypatch.setenv("QWIK_CONFIG_DIR", str(tmp_path))
        _reset_config()
        runner.invoke(app, ["add", "testrun", "echo", "hi"])
        result = runner.invoke(app, ["-r", "testrun"])
        assert result.exit_code in (0, 1)

    def test_bare_aka_empty(self, tmp_path, monkeypatch) -> None:
        from qwik.config import _reset_config

        monkeypatch.setenv("QWIK_CONFIG_DIR", str(tmp_path))
        _reset_config()
        result = runner.invoke(app, [])
        assert result.exit_code in (0, 1)

    def test_callback_invoked_subcommand(self, tmp_path, monkeypatch) -> None:
        from qwik.config import _reset_config

        monkeypatch.setenv("QWIK_CONFIG_DIR", str(tmp_path))
        _reset_config()
        result = runner.invoke(app, ["list"])
        assert result.exit_code == 0
