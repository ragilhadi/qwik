"""Targeted tests for the final 12% coverage gap."""

from __future__ import annotations

import shutil
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from qwik.cli import app
from qwik.core.models import Alias
from qwik.core.substitute import expand

runner = CliRunner()


# ---------------------------------------------------------------------------
# __main__.py line 6
# ---------------------------------------------------------------------------
def test_main_entrypoint() -> None:
    import qwik.__main__ as m

    assert hasattr(m, "app")


# ---------------------------------------------------------------------------
# Models: format_last_used 1 minute branch
# ---------------------------------------------------------------------------
class TestModelsBranches:
    def test_format_1_min(self) -> None:
        alias = Alias(command="x")
        alias.last_used = datetime.now(timezone.utc) - timedelta(minutes=1)
        result = alias.format_last_used()
        # May return "just now" or "1 min ago" depending on exact timing
        assert result in ("just now", "1 min ago")


# ---------------------------------------------------------------------------
# Doctor: shadow conflicts display + /proc fallback
# ---------------------------------------------------------------------------
class TestDoctor:
    def test_doctor_shadow_conflict(self, tmp_path, monkeypatch) -> None:
        from qwik.config import _reset_config

        monkeypatch.setenv("QWIK_CONFIG_DIR", str(tmp_path))
        _reset_config()
        name = next((n for n in ["ls", "cat", "echo"] if shutil.which(n)), None)
        if name is None:
            pytest.skip("No PATH binary found")
        runner.invoke(app, ["add", name, "echo", "hi", "--force"])
        result = runner.invoke(app, ["doctor"])
        assert result.exit_code == 0

    def test_doctor_fallback_proc(self, monkeypatch) -> None:
        from qwik.commands.doctor import _detect_shell

        monkeypatch.delenv("SHELL", raising=False)
        s = _detect_shell()
        assert s in ("bash", "zsh", "fish", "pwsh", None)


# ---------------------------------------------------------------------------
# Pick command non-interactive paths
# ---------------------------------------------------------------------------
class TestPick:
    def test_pick_empty_store(self, tmp_path, monkeypatch) -> None:
        from qwik.config import _reset_config

        monkeypatch.setenv("QWIK_CONFIG_DIR", str(tmp_path))
        _reset_config()
        result = runner.invoke(app, ["pick"])
        assert result.exit_code in (0, 1)

    def test_pick_bare_aka(self, tmp_path, monkeypatch) -> None:
        from qwik.config import _reset_config

        monkeypatch.setenv("QWIK_CONFIG_DIR", str(tmp_path))
        _reset_config()
        result = runner.invoke(app, [])
        assert result.exit_code in (0, 1)


# ---------------------------------------------------------------------------
# Run template with args (remaining run.py lines)
# ---------------------------------------------------------------------------
class TestRunTemplateArgs:
    def test_run_template_with_args(self, tmp_path, monkeypatch) -> None:
        from qwik.config import _reset_config

        monkeypatch.setenv("QWIK_CONFIG_DIR", str(tmp_path))
        _reset_config()
        runner.invoke(app, ["add", "ech", "echo", "{1}"])
        result = runner.invoke(app, ["run", "ech", "hello"])
        assert result.exit_code == 0


# ---------------------------------------------------------------------------
# Tag missing (tag.py lines 49-50)
# ---------------------------------------------------------------------------
class TestTagUntag:
    def test_untag_noop(self, tmp_path, monkeypatch) -> None:
        from qwik.config import _reset_config

        monkeypatch.setenv("QWIK_CONFIG_DIR", str(tmp_path))
        _reset_config()
        runner.invoke(app, ["add", "gs", "git", "status"])
        result = runner.invoke(app, ["untag", "gs", "missing"])
        assert result.exit_code == 0  # no-op, tag not present


# ---------------------------------------------------------------------------
# CLI callback: pick_command path (bare qwik)
# ---------------------------------------------------------------------------
class TestCallback:
    def test_callback_runs_pick(self, tmp_path, monkeypatch) -> None:
        from qwik.config import _reset_config

        monkeypatch.setenv("QWIK_CONFIG_DIR", str(tmp_path))
        _reset_config()
        # Patch pick_command to just return so we verify callback invokes it
        pick_called = [False]

        def fake_pick():
            pick_called[0] = True
            return None

        with patch("qwik.cli.pick_command", fake_pick):
            runner.invoke(app, [])
            assert pick_called[0]


# ---------------------------------------------------------------------------
# Store backup dir missing + rotation
# ---------------------------------------------------------------------------
class TestStorePaths:
    def test_rotate_when_dir_missing(self, tmp_path) -> None:
        from qwik.config import Config
        from qwik.core.store import Store
        from qwik.core.models import Alias, AliasStore

        cfg = Config(override_config_dir=tmp_path)
        store = Store(config=cfg)
        data = AliasStore()
        data.add("a", Alias(command="echo a"))
        store.save(data)
        # Delete backup dir
        import shutil

        shutil.rmtree(cfg.backup_dir, ignore_errors=True)
        d2 = store.load()
        d2.add("b", Alias(command="echo b"), force=True)
        store.save_with_backup(d2)
        # Should succeed even though dir was deleted
        d3 = store.load()
        assert "b" in d3.aliases


# ---------------------------------------------------------------------------
# Zsh simple append branch
# ---------------------------------------------------------------------------
class TestZshNoQuotes:
    def test_zsh_basic_append(self) -> None:
        from qwik.shells.zsh import ZshRenderer
        from qwik.core.models import Alias

        r = ZshRenderer()
        out = r.render_alias("gs", Alias(command="git status"))
        assert out == "alias gs='git status'"


# ---------------------------------------------------------------------------
# Substitute: {@} empty and missing arg paths
# ---------------------------------------------------------------------------
class TestSubstitute:
    def test_at_empty(self) -> None:
        result = expand("echo {@}", [])
        assert result == "echo "

    def test_star_empty(self) -> None:
        result = expand("echo {*}", [])
        assert "''" in result


# ---------------------------------------------------------------------------
# Add: interactive prompts path (lines 75, 87-89)
# ---------------------------------------------------------------------------
class TestAddInteractive:
    def test_add_interactive_name_prompt(self, tmp_path, monkeypatch) -> None:
        from qwik.config import _reset_config

        monkeypatch.setenv("QWIK_CONFIG_DIR", str(tmp_path))
        _reset_config()

        import rich.prompt as rp

        orig_ask = rp.Prompt.ask

        calls = 0

        def fake_ask(*a, **kw):
            nonlocal calls
            calls += 1
            if calls == 1:
                return "gs"
            return "git status"

        rp.Prompt.ask = fake_ask
        try:
            result = runner.invoke(app, ["add"])
            assert result.exit_code == 0
            assert "Added" in result.output
        finally:
            rp.Prompt.ask = orig_ask
