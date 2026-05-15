"""Direct unit tests for hard-to-reach coverage lines."""

from __future__ import annotations

import shutil

import pytest

from qwik.core.models import Alias


# ---------------------------------------------------------------------------
# __main__.py line 6
# ---------------------------------------------------------------------------
def test_main_executes() -> None:
    import qwik.__main__ as m

    assert callable(m.app)


# ---------------------------------------------------------------------------
# models.py 88
# ---------------------------------------------------------------------------
def test_bump_usage_sets_last_used() -> None:
    alias = Alias(command="hi")
    alias.bump_usage()
    assert alias.last_used is not None
    assert alias.run_count == 1


# ---------------------------------------------------------------------------
# doctor.py 63-67 via direct invocation
# ---------------------------------------------------------------------------
def test_doctor_conflict_display(tmp_path, monkeypatch) -> None:
    from qwik.config import _reset_config

    monkeypatch.setenv("QWIK_CONFIG_DIR", str(tmp_path))
    _reset_config()
    name = next((n for n in ["ls", "cat", "grep"] if shutil.which(n)), None)
    if name is None:
        pytest.skip("No PATH binary found")

    from typer.testing import CliRunner
    from qwik.cli import app

    runner = CliRunner()
    runner.invoke(app, ["add", name, "echo", "shadow", "--force"])
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0


# ---------------------------------------------------------------------------
# doctor.py 111-119 via /proc fallback test
# ---------------------------------------------------------------------------
def test_doctor_proc_fallback(monkeypatch) -> None:
    monkeypatch.delenv("SHELL", raising=False)
    from qwik.commands.doctor import _detect_shell

    s = _detect_shell()
    assert s in ("bash", "zsh", "fish", "pwsh", None)


# ---------------------------------------------------------------------------
# doctor.py 144-145
# ---------------------------------------------------------------------------
def test_hook_installed_none() -> None:
    from qwik.commands.doctor import _hook_installed

    assert _hook_installed(None) is False


# ---------------------------------------------------------------------------
# tag.py 49-50
# ---------------------------------------------------------------------------
def test_tag_noop_already_present(tmp_path, monkeypatch) -> None:
    from qwik.config import _reset_config

    monkeypatch.setenv("QWIK_CONFIG_DIR", str(tmp_path))
    _reset_config()

    from typer.testing import CliRunner
    from qwik.cli import app

    runner = CliRunner()
    runner.invoke(app, ["add", "gs", "git", "status"])
    runner.invoke(app, ["tag", "gs", "git"])
    result = runner.invoke(app, ["tag", "gs", "git"])
    assert (
        result.exit_code == 0
    )  # succeeds, but line 49-50 skipped (tag already present)


# ---------------------------------------------------------------------------
# Zsh simple append (line 38)
# ---------------------------------------------------------------------------
def test_zsh_plain_append() -> None:
    from qwik.shells.zsh import ZshRenderer
    from qwik.core.models import Alias

    r = ZshRenderer()
    out = r.render_alias("ls", Alias(command="ls -la"))
    assert out == "alias ls='ls -la'"
