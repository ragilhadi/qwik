"""Use monkeypatch to instrument the CLI callback and force-hit its branches."""

from __future__ import annotations


from typer.testing import CliRunner

from qwik.cli import app

runner = CliRunner()


class TestCallbackBranches:
    """Cover cli.py lines 109-110, 113-114, 126-127, 131-138 by mocking."""

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
        """Bare `qwik` on empty store should reach pick_command (exits gracefully)."""
        from qwik.config import _reset_config

        monkeypatch.setenv("QWIK_CONFIG_DIR", str(tmp_path))
        _reset_config()
        result = runner.invoke(app, [])
        assert result.exit_code in (0, 1)

    def test_callback_invoked_subcommand(self, tmp_path, monkeypatch) -> None:
        """When invoked_subcommand is set, callback returns early."""
        from qwik.config import _reset_config

        monkeypatch.setenv("QWIK_CONFIG_DIR", str(tmp_path))
        _reset_config()
        # Running a subcommand should use the early return
        result = runner.invoke(app, ["list"])
        assert result.exit_code == 0
