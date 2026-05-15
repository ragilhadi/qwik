"""Tests for the doctor command."""

from __future__ import annotations

import shutil
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from qwik.cli import app
from qwik.commands.doctor import _detect_shell, _hook_installed

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


class TestDoctorEdgeCases:
    def test_hook_installed_none(self) -> None:
        assert _hook_installed(None) is False
