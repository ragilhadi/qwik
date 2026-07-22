"""Tests for the doctor command."""

from __future__ import annotations

import shutil
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from qwik.cli import app
from qwik.commands.doctor import _detect_shell, _hook_installed, _latest_valid_backup

runner = CliRunner()


class TestDoctorBasic:
    def test_doctor_passes_with_aliases(self, tmp_path, monkeypatch) -> None:
        from qwik.config import _reset_config

        monkeypatch.setenv("QWIK_CONFIG_DIR", str(tmp_path))
        _reset_config()
        runner.invoke(app, ["add", "gs", "git", "status"])
        result = runner.invoke(app, ["doctor"])
        assert "passed" in result.output

    def test_doctor_with_conflicts(self, tmp_path, monkeypatch) -> None:
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

    def test_doctor_conflict_found(self, tmp_path, monkeypatch) -> None:
        from qwik.config import _reset_config

        monkeypatch.setenv("QWIK_CONFIG_DIR", str(tmp_path))
        _reset_config()
        name = next((n for n in ["ls", "cat", "grep"] if shutil.which(n)), None)
        if name is None:
            pytest.skip("No PATH binary found")
        runner.invoke(app, ["add", name, "echo", "shadow", "--force"])
        result = runner.invoke(app, ["doctor"])
        assert "passed" in result.output


class TestDoctorFallbacks:
    def test_doctor_fallback_proc(self, tmp_path, monkeypatch) -> None:
        from qwik.config import _reset_config

        monkeypatch.delenv("SHELL", raising=False)
        _reset_config()
        if Path("/proc/self/status").exists():
            result = _detect_shell()
            assert result in ("bash", "zsh", "fish", "pwsh", None)
        else:
            pytest.skip("/proc not available")

    def test_doctor_proc_fallback(self, monkeypatch) -> None:
        monkeypatch.delenv("SHELL", raising=False)
        s = _detect_shell()
        assert s in ("bash", "zsh", "fish", "pwsh", None)


class TestDoctorShellDetection:
    def test_detect_shell_from_env(self, monkeypatch) -> None:
        monkeypatch.setenv("SHELL", "/usr/bin/zsh")
        assert _detect_shell() == "zsh"

    def test_detect_shell_fish(self, monkeypatch) -> None:
        monkeypatch.setenv("SHELL", "/usr/bin/fish")
        assert _detect_shell() == "fish"

    def test_detect_shell_pwsh(self, monkeypatch) -> None:
        monkeypatch.setenv("SHELL", "/usr/bin/pwsh")
        assert _detect_shell() == "pwsh"

    def test_detect_shell_no_env(self, monkeypatch) -> None:
        monkeypatch.delenv("SHELL", raising=False)
        result = _detect_shell()
        assert result is None or result in ("bash", "zsh", "fish", "pwsh")


class TestDoctorErrors:
    def test_doctor_unknown_shell_warning(self, tmp_path, monkeypatch) -> None:
        from qwik.config import _reset_config

        monkeypatch.setenv("QWIK_CONFIG_DIR", str(tmp_path))
        _reset_config()
        with patch("qwik.commands.doctor._detect_shell", return_value="tcsh"):
            result = runner.invoke(app, ["doctor"])
            assert result.exit_code == 0
            assert "best-effort" in result.output

    def test_doctor_no_shell(self, tmp_path, monkeypatch) -> None:
        from qwik.config import _reset_config

        monkeypatch.setenv("QWIK_CONFIG_DIR", str(tmp_path))
        _reset_config()
        with patch("qwik.commands.doctor._detect_shell", return_value=None):
            result = runner.invoke(app, ["doctor"])
            assert result.exit_code == 0
            assert "unknown" in result.output

    def test_doctor_unreadable_store(self, tmp_path, monkeypatch) -> None:
        from qwik.config import _reset_config

        monkeypatch.setenv("QWIK_CONFIG_DIR", str(tmp_path))
        _reset_config()
        (tmp_path / "aliases.toml").write_text("not-valid")
        result = runner.invoke(app, ["doctor"])
        assert result.exit_code == 1
        assert "Store unreadable" in result.output

    def test_doctor_hook_not_installed(self, tmp_path, monkeypatch) -> None:
        from qwik.config import _reset_config

        monkeypatch.setenv("QWIK_CONFIG_DIR", str(tmp_path))
        _reset_config()
        runner.invoke(app, ["add", "gs", "git", "status"])
        with patch("qwik.commands.doctor._hook_installed", return_value=False):
            result = runner.invoke(app, ["doctor"])
            assert result.exit_code == 0

    def test_doctor_shell_unknown(self, tmp_path, monkeypatch) -> None:
        from qwik.config import _reset_config

        monkeypatch.setenv("QWIK_CONFIG_DIR", str(tmp_path))
        _reset_config()
        runner.invoke(app, ["add", "gs", "git", "status"])
        with patch("qwik.commands.doctor._detect_shell", return_value=None):
            result = runner.invoke(app, ["doctor"])
            assert result.exit_code == 0

    def test_doctor_store_unreadable(self, tmp_path, monkeypatch) -> None:
        from qwik.config import _reset_config

        monkeypatch.setenv("QWIK_CONFIG_DIR", str(tmp_path))
        _reset_config()
        (tmp_path / "aliases.toml").write_text("not-valid")
        result = runner.invoke(app, ["doctor"])
        assert result.exit_code == 1
        assert "Store unreadable" in result.output


class TestPwshHookDetection:
    """`_hook_installed("pwsh")` uses the pwsh renderer's rc_path."""

    def test_pwsh_hook_present(self, tmp_path, monkeypatch) -> None:
        rc = tmp_path / "Microsoft.PowerShell_profile.ps1"
        rc.write_text("# qwik shell hook (pwsh)\nInvoke-Expression (qwik init pwsh)\n")
        monkeypatch.setattr(
            "qwik.shells.pwsh.PwshRenderer.rc_path", lambda self: rc
        )
        assert _hook_installed("pwsh") is True

    def test_pwsh_hook_absent_empty(self, tmp_path, monkeypatch) -> None:
        rc = tmp_path / "Microsoft.PowerShell_profile.ps1"
        rc.write_text("")
        monkeypatch.setattr(
            "qwik.shells.pwsh.PwshRenderer.rc_path", lambda self: rc
        )
        assert _hook_installed("pwsh") is False

    def test_pwsh_hook_absent_missing(self, tmp_path, monkeypatch) -> None:
        rc = tmp_path / "missing_profile.ps1"
        monkeypatch.setattr(
            "qwik.shells.pwsh.PwshRenderer.rc_path", lambda self: rc
        )
        assert _hook_installed("pwsh") is False


class TestDoctorEdgeCases:
    def test_hook_installed_none(self) -> None:
        assert _hook_installed(None) is False


class TestRestoreFromBackup:
    """`qwik doctor` offers to restore from the latest valid backup."""

    def _seed_store_and_backup(self, tmp_path: Path) -> None:
        """Create a valid store, then back it up before corrupting it.

        Produces exactly one backup containing both ``gs`` and ``gp`` so
        the restore flow deterministically picks it.
        """
        runner.invoke(app, ["add", "gs", "git", "status"])
        runner.invoke(app, ["add", "gp", "git", "push"])
        backups_dir = tmp_path / "backups"
        for f in backups_dir.glob("aliases-*.toml"):
            f.unlink()
        from qwik.core.store import get_store

        store = get_store()
        data = store.load()
        store.save_with_backup(data)
        assert list(backups_dir.glob("aliases-*.toml"))

    def _corrupt_store(self, tmp_path: Path) -> None:
        """Overwrite the live store with invalid TOML."""
        (tmp_path / "aliases.toml").write_text("not-valid", encoding="utf-8")

    def test_doctor_offers_restore_on_corrupt_store(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        from qwik.config import _reset_config
        from qwik.core.store import get_store

        monkeypatch.setenv("QWIK_CONFIG_DIR", str(tmp_path))
        _reset_config()
        self._seed_store_and_backup(tmp_path)
        self._corrupt_store(tmp_path)
        result = runner.invoke(app, ["doctor"], input="y\n")
        assert result.exit_code == 0, result.output
        assert "Restore" in result.output or "restore" in result.output.lower()
        store = get_store()
        data = store.load()
        assert "gs" in data.aliases
        assert "gp" in data.aliases

    def test_doctor_decline_keeps_corrupt_store(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        from qwik.config import _reset_config
        from qwik.core.store import get_store

        monkeypatch.setenv("QWIK_CONFIG_DIR", str(tmp_path))
        _reset_config()
        self._seed_store_and_backup(tmp_path)
        self._corrupt_store(tmp_path)
        result = runner.invoke(app, ["doctor"], input="n\n")
        assert result.exit_code == 1
        live = (tmp_path / "aliases.toml").read_text(encoding="utf-8")
        assert live == "not-valid"
        with pytest.raises(RuntimeError):
            get_store().load()

    def test_doctor_no_backups_exits_with_actionable_error(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        from qwik.config import _reset_config

        monkeypatch.setenv("QWIK_CONFIG_DIR", str(tmp_path))
        _reset_config()
        self._corrupt_store(tmp_path)
        backups = tmp_path / "backups"
        if backups.exists():
            for f in backups.glob("aliases-*.toml"):
                f.unlink()
        result = runner.invoke(app, ["doctor"])
        assert result.exit_code == 1
        assert "manual" in result.output.lower() or "backup" in result.output.lower()

    def test_doctor_skips_invalid_backups(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        from qwik.config import _reset_config
        from qwik.core.store import get_store

        monkeypatch.setenv("QWIK_CONFIG_DIR", str(tmp_path))
        _reset_config()
        self._seed_store_and_backup(tmp_path)
        backups_dir = tmp_path / "backups"
        backups = sorted(backups_dir.glob("aliases-*.toml"))
        valid_backup = backups[0]
        valid_backup.with_name("aliases-00000000-000000-000000-0000.toml").write_text(
            "not-valid", encoding="utf-8"
        )
        self._corrupt_store(tmp_path)
        result = runner.invoke(app, ["doctor"], input="y\n")
        assert result.exit_code == 0, result.output
        data = get_store().load()
        assert "gs" in data.aliases


class TestLatestValidBackupHelper:
    def test_returns_none_when_no_backups(self, tmp_path: Path) -> None:
        backups = tmp_path / "backups"
        backups.mkdir()
        assert _latest_valid_backup(backups) is None

    def test_returns_newest_valid(self, tmp_path: Path) -> None:
        backups = tmp_path / "backups"
        backups.mkdir()
        (backups / "aliases-20260719-120000-000001-0001.toml").write_text(
            'version = 1\n[aliases.a]\ncommand = "x"\n', encoding="utf-8"
        )
        newest = backups / "aliases-20260719-120000-000002-0002.toml"
        newest.write_text(
            'version = 1\n[aliases.b]\ncommand = "y"\n', encoding="utf-8"
        )
        result = _latest_valid_backup(backups)
        assert result is not None
        assert result.name == "aliases-20260719-120000-000002-0002.toml"

    def test_skips_invalid_backups(self, tmp_path: Path) -> None:
        backups = tmp_path / "backups"
        backups.mkdir()
        (backups / "aliases-99990101-000000-000000-9999.toml").write_text(
            "not-valid", encoding="utf-8"
        )
        good = backups / "aliases-20260719-120000-000002-0002.toml"
        good.write_text(
            'version = 1\n[aliases.a]\ncommand = "x"\n', encoding="utf-8"
        )
        assert _latest_valid_backup(backups) == good
