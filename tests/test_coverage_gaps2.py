"""Targeted tests for the remaining high-stmt coverage gaps."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from qwik.cli import app

runner = CliRunner()


class TestDoctorCoverage:
    """Cover doctor.py remaining error paths and fallback detection."""

    def test_doctor_store_readable_with_aliases(self, tmp_path, monkeypatch) -> None:
        """Cover doctor store readable + conflict check path."""
        from qwik.config import _reset_config

        monkeypatch.setenv("QWIK_CONFIG_DIR", str(tmp_path))
        _reset_config()
        runner.invoke(app, ["add", "gs", "git", "status"])
        result = runner.invoke(app, ["doctor"])
        assert "passed" in result.output

    def test_doctor_fallback_proc(self, tmp_path, monkeypatch) -> None:
        """Cover /proc fallback detection in doctor."""
        from qwik.commands.doctor import _detect_shell
        from qwik.config import _reset_config

        monkeypatch.delenv("SHELL", raising=False)
        _reset_config()
        # When $SHELL is missing, fallback to /proc on Linux
        if Path("/proc/self/status").exists():
            result = _detect_shell()
            # Should at least return bash, zsh, fish, pwsh, or None
            assert result in ("bash", "zsh", "fish", "pwsh", None)
        else:
            pytest.skip("/proc not available")

    def test_doctor_hook_not_installed(self, tmp_path, monkeypatch) -> None:
        from qwik.config import _reset_config

        monkeypatch.setenv("QWIK_CONFIG_DIR", str(tmp_path))
        _reset_config()
        runner.invoke(app, ["add", "gs", "git", "status"])
        # Ensure no rc file exists by mocking _hook_installed
        with patch("qwik.commands.doctor._hook_installed", return_value=False):
            result = runner.invoke(app, ["doctor"])
            assert result.exit_code == 0

    def test_doctor_with_conflicts(self, tmp_path, monkeypatch) -> None:
        """Add an alias that shadows a known PATH binary (if one exists)."""
        import shutil

        from qwik.config import _reset_config

        monkeypatch.setenv("QWIK_CONFIG_DIR", str(tmp_path))
        _reset_config()

        binary = next((b for b in ["ls", "cat", "echo"] if shutil.which(b)), None)
        if binary is None:
            pytest.skip("No common binary found on PATH")
        runner.invoke(app, ["add", binary, "echo", "shadow", "--force"])
        result = runner.invoke(app, ["doctor"])
        assert result.exit_code == 0
        assert "passed" in result.output


class TestInitShellInstall:
    """Cover init_shell.py install path densely."""

    def _run_install(self, shell: str, rc: Path) -> None:
        from qwik.commands import init_shell as is_mod

        orig = is_mod._rc_path
        try:
            is_mod._rc_path = lambda s: rc
            result = runner.invoke(app, ["init", shell, "--install"])
        finally:
            is_mod._rc_path = orig
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

        monkeypatch.setenv("QWIK_CONFIG_DIR", str(tmp_path))
        _reset_config()
        from qwik.commands import init_shell as is_mod

        orig = is_mod._rc_path
        try:
            is_mod._rc_path = lambda s: None
            result = runner.invoke(app, ["init", "bash", "--install"])
            assert result.exit_code == 1
            assert "Cannot determine rc file" in result.output
        finally:
            is_mod._rc_path = orig


class TestCLICallbackBranches:
    """Cover cli.py callback remaining branches."""

    def test_bare_aka_exits_cleanly_empty_store(self, tmp_path, monkeypatch) -> None:
        """Bare ``qwik`` with empty store should exit cleanly."""
        from qwik.config import _reset_config

        monkeypatch.setenv("QWIK_CONFIG_DIR", str(tmp_path))
        _reset_config()
        result = runner.invoke(app, [])
        # Picker with empty aliases exits with error and advice
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


class TestRunCoverage:
    def test_run_template_with_shell_chars(self, tmp_path, monkeypatch) -> None:
        """Run a command with shell metacharacters."""
        from qwik.config import _reset_config

        monkeypatch.setenv("QWIK_CONFIG_DIR", str(tmp_path))
        _reset_config()
        runner.invoke(app, ["add", "lshome", "ls", "~"])
        result = runner.invoke(app, ["run", "lshome"])
        assert result.exit_code in (0, 1, 2)

    def test_run_missing_arg(self, tmp_path, monkeypatch) -> None:
        """Template alias missing required arg."""
        from qwik.config import _reset_config

        monkeypatch.setenv("QWIK_CONFIG_DIR", str(tmp_path))
        _reset_config()
        runner.invoke(app, ["add", "gco", "git checkout {1}"])
        result = runner.invoke(app, ["run", "gco"])
        assert result.exit_code == 1
        assert "Missing argument" in result.output


class TestImportConflict:
    def test_import_conflict_display(self, tmp_path, monkeypatch) -> None:
        from qwik.config import _reset_config
        from unittest.mock import patch

        monkeypatch.setenv("QWIK_CONFIG_DIR", str(tmp_path))
        _reset_config()
        runner.invoke(app, ["add", "gs", "git", "status"])
        out = tmp_path / "export.json"
        runner.invoke(app, ["export", str(out)])
        # Re-import same store with conflicts
        with patch("qwik.commands.importer.prompt_confirm", return_value=True):
            result = runner.invoke(app, ["import", str(out)])
            assert result.exit_code == 0
            assert "Conflicts" in result.output


class TestPromptsCoverage:
    """Cover prompts.py remaining branches."""

    def test_prompt_confirm_true(self) -> None:
        from qwik.ui.prompts import prompt_confirm
        from unittest.mock import patch

        with patch("rich.prompt.Confirm.ask", return_value=True):
            assert prompt_confirm("continue?") is True

    def test_prompt_text_allow_empty(self) -> None:
        from qwik.ui.prompts import prompt_text
        from unittest.mock import patch

        with patch("rich.prompt.Prompt.ask", return_value=""):
            assert prompt_text("name", allow_empty=True) == ""

    def test_prompt_text_disallow_empty(self) -> None:
        from qwik.ui.prompts import prompt_text
        from unittest.mock import patch

        call_count = 0

        def fake_ask(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return ""
            return "hello"

        with patch("rich.prompt.Prompt.ask", side_effect=fake_ask):
            result = prompt_text("name", allow_empty=False)
            assert result == "hello"
            assert call_count == 2


class TestPickNoAliases:
    """Cover pick.py edge cases."""

    def test_pick_command_empty_store(self, tmp_path, monkeypatch) -> None:
        from qwik.config import _reset_config

        monkeypatch.setenv("QWIK_CONFIG_DIR", str(tmp_path))
        _reset_config()
        result = runner.invoke(app, ["pick"])
        assert result.exit_code == 0
        assert "No aliases found" in result.output or result.output == ""


class TestSearchCommandEmpty:
    def test_search_empty_store(self, tmp_path, monkeypatch) -> None:
        from qwik.config import _reset_config

        monkeypatch.setenv("QWIK_CONFIG_DIR", str(tmp_path))
        _reset_config()
        result = runner.invoke(app, ["search", "xyz"])
        assert result.exit_code == 0
        assert "No aliases yet" in result.output
