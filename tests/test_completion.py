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
        from qwik.shells.bash import BashRenderer
        from qwik.shells.fish import FishRenderer
        from qwik.shells.pwsh import PwshRenderer
        from qwik.shells.zsh import ZshRenderer

        renderer_cls = {
            "bash": BashRenderer,
            "zsh": ZshRenderer,
            "fish": FishRenderer,
            "pwsh": PwshRenderer,
        }.get(shell)
        if renderer_cls is not None:
            if shell == "fish":
                monkeypatch.setattr(
                    renderer_cls, "rc_path", lambda self: tmp_path / "fish" / "config.fish"
                )
            else:
                monkeypatch.setattr(renderer_cls, "rc_path", lambda self: rc)
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

    def test_install_zsh_includes_autoload(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Regression: the appended block called bare `compinit` with no
        # `autoload -Uz compinit` first. compinit is an autoloadable
        # function, not a builtin, so every new zsh session printed
        # "command not found: compinit" and completions never activated.
        rc = tmp_path / ".zshrc"
        rc.write_text("# pre-existing\n")
        result = self._run_install("zsh", rc, monkeypatch, tmp_path)
        assert result.exit_code == 0
        text = rc.read_text()
        assert "autoload -Uz compinit" in text
        # autoload must appear before the call that needs it.
        assert text.index("autoload -Uz compinit") < text.index(
            "compinit", text.index("autoload -Uz compinit") + 1
        )

    def test_install_zsh_writes_resolved_fpath(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Regression: the rc line hardcoded `$HOME/.zfunc`, which only
        # matches the directory the script was actually written to
        # (rc.parent / ".zfunc") when rc.parent == $HOME.
        rc = tmp_path / "not-home" / ".zshrc"
        rc.parent.mkdir()
        rc.write_text("# pre-existing\n")
        result = self._run_install("zsh", rc, monkeypatch, tmp_path)
        assert result.exit_code == 0
        text = rc.read_text()
        assert str(tmp_path / "not-home" / ".zfunc") in text
        assert "$HOME/.zfunc" not in text

    def test_install_zsh_idempotent(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        rc = tmp_path / ".zshrc"
        rc.write_text("# pre-existing\n")
        self._run_install("zsh", rc, monkeypatch, tmp_path)
        result = self._run_install("zsh", rc, monkeypatch, tmp_path)
        assert result.exit_code == 0
        assert "already installed" in result.output
        assert rc.read_text().count("qwik completion (zsh)") == 1

    def test_install_zsh_repairs_legacy_broken_block(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        rc = tmp_path / ".zshrc"
        rc.write_text(
            "export FOO=bar\n"
            "\n"
            "# qwik completion (zsh)\n"
            "fpath=($HOME/.zfunc $fpath)\n"
            "compinit\n"
            "\n"
            "export BAZ=qux\n"
        )
        result = self._run_install("zsh", rc, monkeypatch, tmp_path)
        assert result.exit_code == 0
        assert "Repaired" in result.output
        text = rc.read_text()
        # The old block's bare, unguarded `compinit` line is gone
        # entirely — not just shadowed by a corrected one appended after
        # it, which would still hit "command not found: compinit" at
        # shell startup before ever reaching the fix.
        assert not any(line.strip() == "compinit" for line in text.splitlines())
        assert "autoload -Uz compinit" in text
        assert text.count("# qwik completion (zsh)") == 1  # substring of v2 marker too
        # The user's own config, on both sides of the old block, survives.
        assert "export FOO=bar" in text
        assert "export BAZ=qux" in text

    def test_install_zsh_repair_is_idempotent(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        rc = tmp_path / ".zshrc"
        rc.write_text(
            "# qwik completion (zsh)\nfpath=($HOME/.zfunc $fpath)\ncompinit\n"
        )
        self._run_install("zsh", rc, monkeypatch, tmp_path)
        result = self._run_install("zsh", rc, monkeypatch, tmp_path)
        assert result.exit_code == 0
        assert "already installed" in result.output
        text = rc.read_text()
        assert not any(line.strip() == "compinit" for line in text.splitlines())
        assert text.count("# qwik completion (zsh)") == 1

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

    def test_install_bash_writes_resolved_source_path(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Regression: the rc line hardcoded `~/.bash_completions/qwik.sh`,
        # which only matches the directory the script was actually
        # written to (rc.parent / ".bash_completions") when rc.parent is
        # $HOME.
        rc = tmp_path / "not-home" / ".bashrc"
        rc.parent.mkdir()
        rc.write_text("# pre-existing\n")
        result = self._run_install("bash", rc, monkeypatch, tmp_path)
        assert result.exit_code == 0
        text = rc.read_text()
        assert str(tmp_path / "not-home" / ".bash_completions" / "qwik.sh") in text
        assert "~/.bash_completions" not in text

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
        from qwik.shells.pwsh import PwshRenderer

        monkeypatch.setattr(PwshRenderer, "rc_path", lambda self: rc)

        r1 = runner.invoke(app, ["completion", "powershell", "--install"])
        assert r1.exit_code == 0
        r2 = runner.invoke(app, ["completion", "pwsh", "--install"])
        assert r2.exit_code == 0
        assert "already installed" in r2.output
        assert rc.read_text().count("# qwik completion (pwsh)") == 1

    def test_install_fish_xdg(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from qwik.shells.fish import FishRenderer

        xdg = tmp_path / "xdg"
        xdg.mkdir()
        monkeypatch.setenv("XDG_CONFIG_HOME", str(xdg))
        monkeypatch.delenv("__fish_config_dir", raising=False)
        result = runner.invoke(app, ["completion", "fish", "--install"])
        assert result.exit_code == 0
        script = xdg / "fish" / "completions" / "qwik.fish"
        assert script.exists()
        assert "qwik" in script.read_text()
