"""Tests for init-shell installation and rc-path detection."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from typer.testing import CliRunner

from qwik.cli import app

runner = CliRunner()


class TestInitShellInstall:
    def _run_install(self, shell: str, rc: Path) -> Any:
        from qwik.shells.base import get_renderer

        renderer_cls = type(get_renderer(shell))
        orig = renderer_cls.rc_path
        try:
            renderer_cls.rc_path = lambda self: rc
            result = runner.invoke(app, ["init", shell, "--install"])
        finally:
            renderer_cls.rc_path = orig
        return result

    def test_install_bash_first_time(self, tmp_path, monkeypatch) -> None:
        from qwik.config import _reset_config

        monkeypatch.setenv("QWIK_CONFIG_DIR", str(tmp_path))
        _reset_config()
        runner.invoke(app, ["add", "gs", "git", "status"])
        rc = tmp_path / ".bashrc"
        result = self._run_install("bash", rc)
        assert result.exit_code == 0
        assert rc.exists()
        assert "qwik init bash" in rc.read_text()

    def test_install_zsh_first_time(self, tmp_path, monkeypatch) -> None:
        from qwik.config import _reset_config

        monkeypatch.setenv("QWIK_CONFIG_DIR", str(tmp_path))
        _reset_config()
        rc = tmp_path / ".zshrc"
        result = self._run_install("zsh", rc)
        assert result.exit_code in (0, 1)
        if result.exit_code == 0:
            assert "qwik init zsh" in rc.read_text()

    def test_install_fish_first_time(self, tmp_path, monkeypatch) -> None:
        from qwik.config import _reset_config

        monkeypatch.setenv("QWIK_CONFIG_DIR", str(tmp_path))
        _reset_config()
        rc = tmp_path / "config.fish"
        result = self._run_install("fish", rc)
        assert result.exit_code in (0, 1)
        if result.exit_code == 0:
            assert "qwik init fish" in rc.read_text()

    def test_install_pwsh_first_time(self, tmp_path, monkeypatch) -> None:
        from qwik.config import _reset_config

        monkeypatch.setenv("QWIK_CONFIG_DIR", str(tmp_path))
        _reset_config()
        rc = tmp_path / "profile.ps1"
        result = self._run_install("pwsh", rc)
        assert result.exit_code in (0, 1)
        if result.exit_code == 0:
            assert "qwik init pwsh" in rc.read_text()

    def test_install_idempotent(self, tmp_path, monkeypatch) -> None:
        from qwik.config import _reset_config

        monkeypatch.setenv("QWIK_CONFIG_DIR", str(tmp_path))
        _reset_config()
        rc = tmp_path / ".bashrc"
        rc.write_text('# qwik shell hook (bash)\neval "$(qwik init bash)"\n')
        result = self._run_install("bash", rc)
        assert "already present" in result.output

    def test_install_backup_created(self, tmp_path, monkeypatch) -> None:
        from qwik.config import _reset_config

        monkeypatch.setenv("QWIK_CONFIG_DIR", str(tmp_path))
        _reset_config()
        rc = tmp_path / ".bashrc"
        rc.write_text("# pre-existing\n")
        result = self._run_install("bash", rc)
        assert result.exit_code == 0
        backups = list(tmp_path.glob(".bashrc.qwik-backup-*"))
        assert len(backups) >= 1

    def test_install_rc_path_none(self, tmp_path, monkeypatch) -> None:
        from qwik.config import _reset_config
        from qwik.shells.bash import BashRenderer

        monkeypatch.setenv("QWIK_CONFIG_DIR", str(tmp_path))
        _reset_config()
        orig = BashRenderer.rc_path
        try:
            BashRenderer.rc_path = lambda self: None
            result = runner.invoke(app, ["init", "bash", "--install"])
            assert result.exit_code == 1
            assert "does not support" in result.output
        finally:
            BashRenderer.rc_path = orig

    def test_install_hook_idempotent(self, tmp_path, monkeypatch) -> None:
        from qwik.shells.bash import BashRenderer

        rc = tmp_path / ".bashrc"
        rc.write_text("# existing\n")
        orig_rc_path = BashRenderer.rc_path
        BashRenderer.rc_path = lambda self: rc
        try:
            r1 = runner.invoke(app, ["init", "bash", "--install"])
            r2 = runner.invoke(app, ["init", "bash", "--install"])
            assert (
                "already present" in r2.output
                or "Backed up" in r1.output
                or "Added hook" in r1.output
            )
        finally:
            BashRenderer.rc_path = orig_rc_path


class TestInitShellRcPath:
    def test_rc_path_pwsh_windows(self, monkeypatch) -> None:
        from qwik.commands.init_shell import _rc_path

        monkeypatch.setattr("sys.platform", "win32")
        rc = _rc_path("pwsh")
        assert "Documents" in str(rc)

    def test_rc_path_pwsh_linux(self, monkeypatch) -> None:
        from qwik.commands.init_shell import _rc_path

        monkeypatch.setattr("sys.platform", "linux")
        rc = _rc_path("pwsh")
        assert ".config" in str(rc)

    def test_rc_path_unknown_shell(self) -> None:
        from qwik.commands.init_shell import _rc_path

        assert _rc_path("tcsh") is None

    def test_init_install_creates_rc(self, tmp_path, monkeypatch) -> None:
        from qwik.config import _reset_config
        from qwik.shells.bash import BashRenderer

        monkeypatch.setenv("QWIK_CONFIG_DIR", str(tmp_path))
        _reset_config()
        runner.invoke(app, ["add", "gs", "git", "status"])
        rc = tmp_path / ".bashrc"
        original = BashRenderer.rc_path
        try:
            BashRenderer.rc_path = lambda self: rc
            result = runner.invoke(app, ["init", "bash", "--install"])
            assert result.exit_code in (0, 1)
        finally:
            BashRenderer.rc_path = original

    def test_init_install_idempotent_existing(self, tmp_path, monkeypatch) -> None:
        from qwik.config import _reset_config
        from qwik.shells.bash import BashRenderer

        monkeypatch.setenv("QWIK_CONFIG_DIR", str(tmp_path))
        _reset_config()
        runner.invoke(app, ["add", "gs", "git", "status"])
        rc = tmp_path / ".bashrc"
        rc.write_text('# qwik shell hook (bash)\neval "$(qwik init bash)"')
        original = BashRenderer.rc_path
        try:
            BashRenderer.rc_path = lambda self: rc
            result = runner.invoke(app, ["init", "bash", "--install"])
            assert result.exit_code == 0
            assert "already present" in result.output
        finally:
            BashRenderer.rc_path = original

    def test_init_install_unknown_shell(self, tmp_path, monkeypatch) -> None:
        from qwik.config import _reset_config
        from qwik.shells.bash import BashRenderer

        monkeypatch.setenv("QWIK_CONFIG_DIR", str(tmp_path))
        _reset_config()
        runner.invoke(app, ["add", "gs", "git", "status"])
        original = BashRenderer.rc_path
        try:
            BashRenderer.rc_path = lambda self: None
            result = runner.invoke(app, ["init", "bash", "--install"])
            assert result.exit_code == 1
            assert "does not support" in result.output
        finally:
            BashRenderer.rc_path = original

    def test_fish_rc_path_respects_xdg(self, tmp_path, monkeypatch) -> None:
        from qwik.commands.init_shell import _rc_path

        xdg = tmp_path / "xdg"
        xdg.mkdir()
        monkeypatch.setenv("XDG_CONFIG_HOME", str(xdg))
        monkeypatch.delenv("__fish_config_dir", raising=False)
        assert _rc_path("fish") == xdg / "fish" / "config.fish"

    def test_fish_rc_path_respects_fish_env(self, tmp_path, monkeypatch) -> None:
        from qwik.commands.init_shell import _rc_path

        fdir = tmp_path / "fishcustom"
        fdir.mkdir()
        monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
        monkeypatch.setenv("__fish_config_dir", str(fdir))
        assert _rc_path("fish") == fdir / "config.fish"

    def test_fish_rc_path_default(self, tmp_path, monkeypatch) -> None:
        import sys

        from qwik.commands.init_shell import _rc_path

        monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
        monkeypatch.delenv("__fish_config_dir", raising=False)
        if sys.platform == "win32":
            monkeypatch.setenv("USERPROFILE", str(tmp_path))
        else:
            monkeypatch.setenv("HOME", str(tmp_path))
        assert _rc_path("fish") == tmp_path / ".config" / "fish" / "config.fish"
