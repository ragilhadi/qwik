"""Tests for the ``qwik completion`` command."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner, Result

from qwik.cli import app

runner = CliRunner()


class TestCompletionPrint:
    def test_completion_bash_print(self) -> None:
        result = runner.invoke(app, ["completion", "bash"])
        assert result.exit_code == 0
        assert "complete -F" in result.output or "_qwik" in result.output

    def test_completion_zsh_print(self) -> None:
        result = runner.invoke(app, ["completion", "zsh"])
        assert result.exit_code == 0
        assert "compdef" in result.output or "_qwik" in result.output

    def test_completion_fish_print(self) -> None:
        result = runner.invoke(app, ["completion", "fish"])
        assert result.exit_code == 0
        assert "qwik" in result.output

    def test_completion_pwsh_print(self) -> None:
        result = runner.invoke(app, ["completion", "pwsh"])
        assert result.exit_code == 0
        assert "_QWIK_COMPLETE" in result.output

    def test_completion_unknown_shell(self) -> None:
        result = runner.invoke(app, ["completion", "tcsh"])
        assert result.exit_code == 1


class TestCompletionInstall:
    def _run_install(
        self,
        shell: str,
        rc: Path | None,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> Result:
        from qwik.commands import completion as cmp_mod
        from qwik.commands import init_shell as is_mod

        monkeypatch.setattr(
            cmp_mod, "_rc_path", lambda s: rc if s == shell else None
        )
        monkeypatch.setattr(
            is_mod, "_rc_path", lambda s: rc if s == shell else None
        )
        monkeypatch.setattr(
            cmp_mod,
            "_fish_config_dir",
            lambda: tmp_path / "fish",
        )
        monkeypatch.setattr(
            is_mod,
            "_fish_config_dir",
            lambda: tmp_path / "fish",
        )
        return runner.invoke(app, ["completion", shell, "--install"])

    def test_install_bash(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        rc = tmp_path / ".bashrc"
        rc.write_text("# pre-existing\n")
        result = self._run_install("bash", rc, monkeypatch, tmp_path)
        assert result.exit_code == 0
        assert rc.read_text().count("# qwik completion (bash)") >= 1
        assert "qwik.sh" in rc.read_text()
        script = tmp_path / ".bash_completions" / "qwik.sh"
        assert script.exists()
        assert "complete -o default -F" in script.read_text()
        backups = list(tmp_path.glob(".bashrc.qwik-backup-*"))
        assert len(backups) >= 1

    def test_install_zsh(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        rc = tmp_path / ".zshrc"
        rc.write_text("# pre-existing\n")
        result = self._run_install("zsh", rc, monkeypatch, tmp_path)
        assert result.exit_code == 0
        script = tmp_path / ".zfunc" / "_qwik"
        assert script.exists()
        assert "compdef" in script.read_text()
        assert "# qwik completion (zsh)" in rc.read_text()

    def test_install_fish(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        result = self._run_install("fish", None, monkeypatch, tmp_path)
        assert result.exit_code == 0
        script = tmp_path / "fish" / "completions" / "qwik.fish"
        assert script.exists()
        assert "qwik" in script.read_text()
        assert "auto-load" in result.output or "next shell" in result.output

    def test_install_pwsh(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        rc = tmp_path / "profile.ps1"
        rc.write_text("# pre-existing\n")
        result = self._run_install("pwsh", rc, monkeypatch, tmp_path)
        assert result.exit_code == 0
        text = rc.read_text()
        assert "# qwik completion (pwsh)" in text
        assert "_QWIK_COMPLETE" in text

    def test_install_idempotent(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        rc = tmp_path / ".bashrc"
        rc.write_text("# pre-existing\n")
        self._run_install("bash", rc, monkeypatch, tmp_path)
        r2 = self._run_install("bash", rc, monkeypatch, tmp_path)
        assert r2.exit_code == 0
        assert "already installed" in r2.output
        assert rc.read_text().count("# qwik completion (bash)") == 1

    def test_completion_install_powershell_alias_idempotent_with_pwsh(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        rc = tmp_path / "profile.ps1"
        rc.write_text("# pre-existing\n")
        from qwik.commands import completion as cmp_mod
        from qwik.commands import init_shell as is_mod

        for mod in (cmp_mod, is_mod):
            monkeypatch.setattr(
                mod, "_rc_path", lambda s: rc if s in {"pwsh", "powershell"} else None
            )
        monkeypatch.setattr(
            cmp_mod, "_fish_config_dir", lambda: tmp_path / "fish"
        )
        monkeypatch.setattr(
            is_mod, "_fish_config_dir", lambda: tmp_path / "fish"
        )

        r1 = runner.invoke(app, ["completion", "powershell", "--install"])
        assert r1.exit_code == 0
        r2 = runner.invoke(app, ["completion", "pwsh", "--install"])
        assert r2.exit_code == 0
        assert "already installed" in r2.output
        assert rc.read_text().count("# qwik completion (pwsh)") == 1

    def test_install_fish_xdg(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from qwik.commands import completion as cmp_mod

        xdg = tmp_path / "xdg"
        xdg.mkdir()
        monkeypatch.setenv("XDG_CONFIG_HOME", str(xdg))
        monkeypatch.delenv("__fish_config_dir", raising=False)
        monkeypatch.setattr(
            cmp_mod, "_fish_config_dir", lambda: xdg / "fish"
        )
        result = runner.invoke(app, ["completion", "fish", "--install"])
        assert result.exit_code == 0
        script = xdg / "fish" / "completions" / "qwik.fish"
        assert script.exists()
        assert "qwik" in script.read_text()
