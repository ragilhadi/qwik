"""End-to-end tests: source generated hooks in real shells."""
from __future__ import annotations

import shutil
import subprocess

import pytest
from typer.testing import CliRunner

from qwik.cli import app

runner = CliRunner()


def _shell_available(name: str) -> bool:
    return shutil.which(name) is not None


def _qwik_env() -> dict[str, str]:
    """Environment for qwik subprocesses: force UTF-8 stdio on Windows."""
    import os

    env = dict(os.environ)
    env.setdefault("PYTHONUTF8", "1")
    env.setdefault("PYTHONIOENCODING", "utf-8")
    return env


@pytest.fixture
def qwik_store(tmp_path, monkeypatch):
    from qwik.config import _reset_config
    monkeypatch.setenv("QWIK_CONFIG_DIR", str(tmp_path))
    _reset_config()
    runner.invoke(app, ["add", "gs", "git", "status"])
    runner.invoke(app, ["add", "gco", "git", "checkout", "{1}"])
    return tmp_path


@pytest.mark.integration
def test_bash_hook_runs_alias(qwik_store, tmp_path):
    if not _shell_available("bash"):
        pytest.skip("bash not installed")
    rcfile = tmp_path / "bashrc"
    hook = subprocess.run(
        ["qwik", "init", "bash"], capture_output=True, text=True, check=True, env=_qwik_env()
    ).stdout
    rcfile.write_text(f"{hook}\n", encoding="utf-8")
    result = subprocess.run(
        ["bash", "-c", f"source {rcfile}; qwik run gs"],
        capture_output=True, text=True, env=_qwik_env(),
    )
    assert result.returncode in (0, 1, 128)


@pytest.mark.integration
def test_zsh_hook_runs_alias(qwik_store, tmp_path):
    if not _shell_available("zsh"):
        pytest.skip("zsh not installed")
    hook = subprocess.run(
        ["qwik", "init", "zsh"], capture_output=True, text=True, check=True, env=_qwik_env()
    ).stdout
    result = subprocess.run(
        ["zsh", "-c", f"{hook}; gco main"],
        capture_output=True, text=True, env=_qwik_env(),
    )
    assert "git checkout main" in result.stdout or "git checkout" in result.stderr


@pytest.mark.integration
def test_fish_hook_runs_alias(qwik_store, tmp_path):
    if not _shell_available("fish"):
        pytest.skip("fish not installed")
    hook = subprocess.run(
        ["qwik", "init", "fish"], capture_output=True, text=True, check=True, env=_qwik_env()
    ).stdout
    result = subprocess.run(
        ["fish", "-c", f"{hook}; gco main"],
        capture_output=True, text=True, env=_qwik_env(),
    )
    assert "git checkout main" in result.stdout or "git checkout" in result.stderr


@pytest.mark.integration
def test_fish_hook_runs_append_mode_alias(qwik_store, tmp_path):
    if not _shell_available("fish"):
        pytest.skip("fish not installed")
    hook = subprocess.run(
        ["qwik", "init", "fish"], capture_output=True, text=True, check=True, env=_qwik_env()
    ).stdout
    result = subprocess.run(
        ["fish", "-c", f"{hook}; gs"],
        capture_output=True, text=True, env=_qwik_env(),
    )
    assert "Unknown command" not in result.stderr
    assert result.returncode in (0, 1, 128)


@pytest.mark.integration
def test_pwsh_hook_runs_alias(qwik_store, tmp_path):
    if not _shell_available("pwsh"):
        pytest.skip("pwsh not installed")
    hook = subprocess.run(
        ["qwik", "init", "pwsh"], capture_output=True, text=True, check=True, env=_qwik_env()
    ).stdout
    result = subprocess.run(
        ["pwsh", "-NoProfile", "-Command", f"{hook}; gco main"],
        capture_output=True, text=True, env=_qwik_env(),
    )
    assert "git checkout main" in result.stdout or "git checkout" in result.stderr
