"""End-to-end tests: source generated hooks in real shells and invoke the
resulting aliases exactly as an interactive user would.

Every test writes the rendered hook plus an alias invocation to a small
script file and runs it through the real shell binary, then asserts on
*exact* stdout/stderr — never a substring, an ``or`` across streams, or a
tolerant set of exit codes. A weak assertion is what let the fish and
xonsh renderers ship completely broken with a green suite: the previous
version of this file mostly invoked ``qwik run`` (the substitution
engine, already covered by unit tests) rather than the alias the
renderer actually emits, so it could never have caught a rendering bug.

Hook + invocation are joined with a newline, not a semicolon, and read
from a script file rather than passed as a single ``-c`` string. Both
bash and zsh only refresh their alias table at a line boundary; a
same-line ``hook; alias-name`` is parsed as one unit before the alias
definition takes effect and fails with "command not found" even though
the alias would work fine sourced from an rc file, which is exactly how
these hooks are used in practice.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

from qwik.cli import app

runner = CliRunner()

# Exact expected output of `git status` on a freshly committed, clean
# repo checked out on "trunk" (see the git_repo fixture), and of
# `git checkout main` from there. git always writes the checkout message
# to stderr, never stdout, regardless of shell.
GIT_STATUS_CLEAN = "On branch trunk\nnothing to commit, working tree clean\n"
SWITCHED_TO_MAIN = "Switched to branch 'main'\n"

# One append-mode alias whose command contains a single-quoted argument —
# the same adversarial case the render_all snapshot tests pin (see
# tests/test_shell_snapshots.py) — run for real here to prove the quoting
# each renderer applies actually round-trips through its shell.
QUOTED_ECHO_OUTPUT = "hello world\n"

_SCRIPT_EXT = {
    "bash": ".sh",
    "zsh": ".zsh",
    "fish": ".fish",
    "pwsh": ".ps1",
    "nu": ".nu",
    "xonsh": ".xsh",
}

# bash disables alias expansion in non-interactive shells unless told
# otherwise; an interactive shell (the only place a real .bashrc runs)
# has this on by default, so this is a test-harness accommodation, not a
# change in what's being tested.
_SHELL_PRELUDE = {"bash": "shopt -s expand_aliases"}

HOOK_TESTED_SHELLS = ["bash", "zsh", "fish", "pwsh", "nu", "xonsh"]


# Git for Windows always installs its own bash at one of these fixed
# locations. `bash` on PATH there commonly resolves instead to the WSL
# launcher stub at C:\Windows\System32\bash.exe — a shim that exists
# purely to print "install a WSL distribution" and exit, regardless of
# what's actually installed, and that GitHub's windows-latest runner
# image puts ahead of Git's bin directory on PATH.
_WINDOWS_GIT_BASH_CANDIDATES = (
    r"C:\Program Files\Git\bin\bash.exe",
    r"C:\Program Files\Git\usr\bin\bash.exe",
)


def _resolve_shell_binary(name: str) -> str | None:
    """Resolve *name* to the binary to invoke, working around PATH quirks."""
    if name == "bash" and sys.platform == "win32":
        for candidate in _WINDOWS_GIT_BASH_CANDIDATES:
            if Path(candidate).exists():
                return candidate
    return shutil.which(name)


def _shell_available(name: str) -> bool:
    return _resolve_shell_binary(name) is not None


def _require_shell(name: str) -> None:
    """Skip, unless ``QWIK_REQUIRE_SHELLS`` demands the shell exist.

    Silent skips are how a shell quietly falling out of a CI image goes
    unnoticed. Set ``QWIK_REQUIRE_SHELLS=1`` in CI once every shell under
    test is actually installed, and a missing one becomes a hard failure.
    """
    if _shell_available(name):
        return
    if os.environ.get("QWIK_REQUIRE_SHELLS"):
        pytest.fail(f"{name} is required by QWIK_REQUIRE_SHELLS but is not installed")
    pytest.skip(f"{name} not installed")


def _qwik_env() -> dict[str, str]:
    """Environment for qwik subprocesses: force UTF-8 stdio on Windows."""
    env = dict(os.environ)
    env.setdefault("PYTHONUTF8", "1")
    env.setdefault("PYTHONIOENCODING", "utf-8")
    return env


def _shell_invocation(shell: str, script: Path) -> list[str]:
    binary = _resolve_shell_binary(shell) or shell
    if shell == "pwsh":
        return [binary, "-NoProfile", "-File", str(script)]
    return [binary, str(script)]


def _render_hook(shell: str) -> str:
    return subprocess.run(
        ["qwik", "init", shell], capture_output=True, text=True, check=True, env=_qwik_env()
    ).stdout


def _run_hook_script(
    shell: str, hook: str, command: str, cwd: Path, tmp_path: Path
) -> subprocess.CompletedProcess[str]:
    lines = [_SHELL_PRELUDE[shell]] if shell in _SHELL_PRELUDE else []
    lines += [hook, command]
    script = tmp_path / f"hook_{shell}{_SCRIPT_EXT[shell]}"
    script.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return subprocess.run(
        _shell_invocation(shell, script),
        cwd=cwd,
        capture_output=True,
        text=True,
        env=_qwik_env(),
    )


@pytest.fixture
def qwik_store(tmp_path, monkeypatch):
    from qwik.config import _reset_config

    monkeypatch.setenv("QWIK_CONFIG_DIR", str(tmp_path))
    _reset_config()
    runner.invoke(app, ["add", "gs", "git", "status"])
    runner.invoke(app, ["add", "gco", "git", "checkout", "{1}"])
    runner.invoke(app, ["add", "lsg", "echo", "'hello", "world'"])
    return tmp_path


@pytest.fixture
def git_repo(tmp_path):
    """A real git repo with a ``main`` branch to check out into, on
    ``trunk`` so that a clean ``git status`` has deterministic, exact
    output regardless of this repository's own default branch name.
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
@pytest.mark.parametrize("shell", HOOK_TESTED_SHELLS)
def test_hook_runs_append_mode_alias(shell, qwik_store, git_repo, tmp_path):
    """``gs`` (append mode, no placeholders) prints exactly what
    ``git status`` prints, with nothing on stderr.
    """
    _require_shell(shell)
    hook = _render_hook(shell)
    result = _run_hook_script(shell, hook, "gs", git_repo, tmp_path)
    assert result.stderr == "", result.stderr
    assert result.stdout == GIT_STATUS_CLEAN


@pytest.mark.integration
@pytest.mark.parametrize("shell", HOOK_TESTED_SHELLS)
def test_hook_runs_template_mode_alias(shell, qwik_store, git_repo, tmp_path):
    """``gco main`` (template mode, ``{1}`` substitution) runs
    ``git checkout main`` exactly, with nothing on stdout.
    """
    _require_shell(shell)
    hook = _render_hook(shell)
    result = _run_hook_script(shell, hook, "gco main", git_repo, tmp_path)
    assert result.stdout == "", result.stdout
    assert result.stderr == SWITCHED_TO_MAIN


@pytest.mark.integration
@pytest.mark.parametrize("shell", HOOK_TESTED_SHELLS)
def test_hook_runs_quoted_append_mode_alias(shell, qwik_store, tmp_path):
    """``lsg`` carries a single-quoted argument in its command text —
    the adversarial case the render_all snapshots pin. Each renderer's
    escaping must round-trip through its own shell back to a literal
    ``hello world``, not a shell-interpreted fragment of it.
    """
    _require_shell(shell)
    hook = _render_hook(shell)
    result = _run_hook_script(shell, hook, "lsg", tmp_path, tmp_path)
    assert result.stderr == "", result.stderr
    assert result.stdout == QUOTED_ECHO_OUTPUT


@pytest.mark.integration
def test_zsh_completion_install_clean_startup(qwik_store, tmp_path):
    # Regression: the installed block called bare `compinit` with no
    # `autoload -Uz compinit` first, so every new zsh session printed
    # "command not found: compinit" and completions never activated.
    _require_shell("zsh")
    rc = tmp_path / ".zshrc"
    rc.write_text("", encoding="utf-8")
    env = _qwik_env()
    env["HOME"] = str(tmp_path)
    env["ZDOTDIR"] = str(tmp_path)
    result = subprocess.run(
        ["qwik", "completion", "zsh", "--install"],
        capture_output=True, text=True, env=env,
    )
    assert result.returncode == 0, result.stderr

    startup = subprocess.run(
        ["zsh", "-i", "-c", "true"],
        capture_output=True, text=True, env=env,
    )
    # The exact regression signature — a CI runner with no controlling
    # terminal can still legitimately print its own unrelated "not
    # interactive and can't open terminal" / "compinit: initialization
    # aborted" warnings here, which a blanket "compinit" not in stderr
    # check would misreport as this bug.
    assert "command not found" not in startup.stderr


# No hook-execution test for cmd: doskey macros are only expanded when
# cmd.exe reads commands through its own interactive line-input
# processing. Neither a .bat/.cmd script file nor piped stdin goes
# through that path — both were tried, and both leave `gs` "not
# recognized" even though the exact same doskey line works when typed
# at a real console. CmdRenderer is documented as best-effort for
# exactly this reason; the quoting test below (via `qwik run`, which
# doesn't depend on doskey at all) is the coverage cmd gets here.


@pytest.mark.integration
def test_run_cmd_quoting_preserves_spaced_argument(tmp_path):
    # Regression: shlex.quote()'s POSIX single-quote output means nothing
    # to cmd.exe, so a spaced argument used to arrive at the child program
    # split into two — this only runs for real on a Windows CI runner.
    if sys.platform != "win32":
        pytest.skip("cmd.exe quoting only applies on Windows")
    env = _qwik_env()
    env["QWIK_CONFIG_DIR"] = str(tmp_path)
    env["QWIK_SHELL"] = "cmd"

    marker = tmp_path / "argv.txt"
    script = tmp_path / "argecho.py"
    script.write_text(
        "import sys, pathlib\n"
        f"pathlib.Path(r'{marker}').write_text(repr(sys.argv[1:]))\n",
        encoding="utf-8",
    )
    alias_cmd = f'{sys.executable} "{script}" {{1}}'
    subprocess.run(["qwik", "add", "argecho", alias_cmd], check=True, env=env)
    result = subprocess.run(["qwik", "run", "argecho", "my branch"], env=env)
    assert result.returncode == 0
    assert marker.read_text(encoding="utf-8") == "['my branch']"


@pytest.mark.integration
def test_run_pwsh_quoting_preserves_spaced_argument(tmp_path):
    # Regression: even with correct PowerShell-style quoting, shell=True
    # on Windows always runs the string through cmd.exe (COMSPEC), not
    # pwsh/powershell.exe — so the quoting has to be paired with an
    # explicit interpreter choice, not just a different quote function.
    if sys.platform != "win32":
        pytest.skip("pwsh quoting only applies on Windows")
    env = _qwik_env()
    env["QWIK_CONFIG_DIR"] = str(tmp_path)
    env["QWIK_SHELL"] = "pwsh"

    marker = tmp_path / "argv.txt"
    script = tmp_path / "argecho.py"
    script.write_text(
        "import sys, pathlib\n"
        f"pathlib.Path(r'{marker}').write_text(repr(sys.argv[1:]))\n",
        encoding="utf-8",
    )
    alias_cmd = f'{sys.executable} "{script}" {{1}}'
    subprocess.run(["qwik", "add", "argecho", alias_cmd], check=True, env=env)
    result = subprocess.run(["qwik", "run", "argecho", "my branch"], env=env)
    assert result.returncode == 0
    assert marker.read_text(encoding="utf-8") == "['my branch']"
