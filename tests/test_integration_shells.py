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


@pytest.fixture
def git_repo(tmp_path):
    """A real git repo with a ``main`` branch to check out into.

    The ``gco main`` tests below run in whatever directory the test
    process's cwd is; asserting on git's own success/failure text only
    makes sense if "main" actually exists as a branch there. Rather than
    depend on this repository's own default branch (which is "master",
    not "main"), build an isolated repo with a real "main" branch and
    run the shell subprocess with this as its cwd — deterministic
    regardless of the ambient environment.
    """
    repo = tmp_path / "workdir"
    repo.mkdir()
    run = lambda *args: subprocess.run(  # noqa: E731
        args, cwd=repo, check=True, capture_output=True, text=True
    )
    run("git", "init", "-q")
    run("git", "config", "user.email", "qwik-test@example.com")
    run("git", "config", "user.name", "qwik test")
    run("git", "checkout", "-q", "-b", "trunk")
    (repo / "README.md").write_text("test\n", encoding="utf-8")
    run("git", "add", ".")
    run("git", "commit", "-q", "-m", "init")
    run("git", "branch", "main")
    return repo


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
def test_zsh_hook_runs_alias(qwik_store, git_repo, tmp_path):
    if not _shell_available("zsh"):
        pytest.skip("zsh not installed")
    hook = subprocess.run(
        ["qwik", "init", "zsh"], capture_output=True, text=True, check=True, env=_qwik_env()
    ).stdout
    result = subprocess.run(
        ["zsh", "-c", f"{hook}; gco main"],
        capture_output=True, text=True, env=_qwik_env(), cwd=git_repo,
    )
    assert "Switched to branch" in result.stdout or "Switched to branch" in result.stderr


@pytest.mark.integration
def test_fish_hook_runs_alias(qwik_store, git_repo, tmp_path):
    if not _shell_available("fish"):
        pytest.skip("fish not installed")
    hook = subprocess.run(
        ["qwik", "init", "fish"], capture_output=True, text=True, check=True, env=_qwik_env()
    ).stdout
    result = subprocess.run(
        ["fish", "-c", f"{hook}; gco main"],
        capture_output=True, text=True, env=_qwik_env(), cwd=git_repo,
    )
    assert "Switched to branch" in result.stdout or "Switched to branch" in result.stderr


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
def test_pwsh_hook_runs_alias(qwik_store, git_repo, tmp_path):
    if not _shell_available("pwsh"):
        pytest.skip("pwsh not installed")
    hook = subprocess.run(
        ["qwik", "init", "pwsh"], capture_output=True, text=True, check=True, env=_qwik_env()
    ).stdout
    result = subprocess.run(
        ["pwsh", "-NoProfile", "-Command", f"{hook}; gco main"],
        capture_output=True, text=True, env=_qwik_env(), cwd=git_repo,
    )
    assert "Switched to branch" in result.stdout or "Switched to branch" in result.stderr
