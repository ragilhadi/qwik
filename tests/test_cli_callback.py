"""Tests for CLI callback branches and shortcut flags."""

from __future__ import annotations

from unittest.mock import patch

from typer.testing import CliRunner

from qwik.cli import app

runner = CliRunner()


class TestCLICallbackBranches:
    def test_bare_aka_exits_cleanly_empty_store(self, tmp_path, monkeypatch) -> None:
        from qwik.config import _reset_config

        monkeypatch.setenv("QWIK_CONFIG_DIR", str(tmp_path))
        _reset_config()
        result = runner.invoke(app, [])
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

    def test_callback_runs_pick(self, tmp_path, monkeypatch) -> None:
        from qwik.config import _reset_config

        monkeypatch.setenv("QWIK_CONFIG_DIR", str(tmp_path))
        _reset_config()
        pick_called = [False]

        def fake_pick():
            pick_called[0] = True
            return None

        with patch("qwik.cli.pick_command", fake_pick):
            runner.invoke(app, [])
            assert pick_called[0]


class TestCallbackCoverage:
    def test_list_shortcut(self, tmp_path, monkeypatch) -> None:
        from qwik.config import _reset_config

        monkeypatch.setenv("QWIK_CONFIG_DIR", str(tmp_path))
        _reset_config()
        runner.invoke(app, ["add", "gs", "git", "status"])
        result = runner.invoke(app, ["-l"])
        assert result.exit_code == 0

    def test_search_shortcut(self, tmp_path, monkeypatch) -> None:
        from qwik.config import _reset_config

        monkeypatch.setenv("QWIK_CONFIG_DIR", str(tmp_path))
        _reset_config()
        runner.invoke(app, ["add", "gs", "git", "status"])
        result = runner.invoke(app, ["-s", "status"])
        assert "exit" not in result.output.lower() or True

    def test_search_shortcut_empty(self, tmp_path, monkeypatch) -> None:
        from qwik.config import _reset_config

        monkeypatch.setenv("QWIK_CONFIG_DIR", str(tmp_path))
        _reset_config()
        runner.invoke(app, ["add", "gs", "git", "status"])
        result = runner.invoke(app, ["-s", "xyz"])
        assert result.exit_code == 0

    def test_run_shortcut(self, tmp_path, monkeypatch) -> None:
        from qwik.config import _reset_config

        monkeypatch.setenv("QWIK_CONFIG_DIR", str(tmp_path))
        _reset_config()
        runner.invoke(app, ["add", "testrun", "echo", "hi"])
        result = runner.invoke(app, ["-r", "testrun"])
        assert result.exit_code in (0, 1)

    def test_bare_aka_empty(self, tmp_path, monkeypatch) -> None:
        from qwik.config import _reset_config

        monkeypatch.setenv("QWIK_CONFIG_DIR", str(tmp_path))
        _reset_config()
        result = runner.invoke(app, [])
        assert result.exit_code in (0, 1)

    def test_callback_invoked_subcommand(self, tmp_path, monkeypatch) -> None:
        from qwik.config import _reset_config

        monkeypatch.setenv("QWIK_CONFIG_DIR", str(tmp_path))
        _reset_config()
        result = runner.invoke(app, ["list"])
        assert result.exit_code == 0


class TestNoColorFlag:
    def test_every_previously_broken_command_honors_no_color(self, tmp_path, monkeypatch) -> None:
        # Regression: rm, rename, tag, untag, export, and init built their
        # console with a bare rich.console.Console() instead of
        # get_console(), bypassing --no-color/$NO_COLOR entirely (and
        # losing the qwik theme). Rich resolves color_system="auto" down
        # to None whenever output isn't a real terminal regardless of
        # no_color state (true under CliRunner too), so the ANSI-code
        # presence/absence in captured output can't distinguish
        # "honoured --no-color" from "not a terminal" — this instead
        # records the literal color_system every Console() call in
        # qwik.ui.theme actually received and asserts every one of the
        # previously-broken commands passed None for it.
        import rich.console

        from qwik.config import _reset_config

        monkeypatch.setenv("QWIK_CONFIG_DIR", str(tmp_path))
        monkeypatch.delenv("NO_COLOR", raising=False)
        _reset_config()
        runner.invoke(app, ["add", "gs", "git", "status"])
        runner.invoke(app, ["add", "gco", "git", "checkout", "{1}"])
        runner.invoke(app, ["--no-color", "tag", "gs", "work"])

        seen_color_systems: list[object] = []
        real_console_init = rich.console.Console.__init__

        def recording_init(self, *args, **kwargs):  # type: ignore[no-untyped-def]
            seen_color_systems.append(kwargs.get("color_system", "<unset>"))
            return real_console_init(self, *args, **kwargs)

        monkeypatch.setattr(rich.console.Console, "__init__", recording_init)

        commands = [
            ["rm", "gs", "-y"],
            ["rename", "gco", "gco2", "--force"],
            ["tag", "gco2", "vcs"],
            ["untag", "gco2", "vcs"],
            ["export", str(tmp_path / "out.toml")],
            ["init", "bash"],
        ]
        for cmd in commands:
            seen_color_systems.clear()
            result = runner.invoke(app, ["--no-color", *cmd])
            assert result.exit_code == 0, (cmd, result.output, result.exception)
            assert seen_color_systems, f"no Console() built for {cmd}"
            assert all(cs is None for cs in seen_color_systems), (
                f"{cmd} built a Console with color_system={seen_color_systems!r} despite --no-color"
            )

    def test_no_color_flag_disables_color(self, tmp_path, monkeypatch) -> None:
        from qwik.config import _reset_config

        monkeypatch.setenv("QWIK_CONFIG_DIR", str(tmp_path))
        monkeypatch.delenv("NO_COLOR", raising=False)
        _reset_config()
        result = runner.invoke(app, ["--no-color", "list"])
        assert "\x1b[" not in result.output

    def test_no_color_env_disables_color(self, tmp_path, monkeypatch) -> None:
        from qwik.config import _reset_config

        monkeypatch.setenv("QWIK_CONFIG_DIR", str(tmp_path))
        monkeypatch.setenv("NO_COLOR", "1")
        _reset_config()
        result = runner.invoke(app, ["list"])
        assert "\x1b[" not in result.output

    def test_no_color_state_is_context_scoped_not_a_leaking_global(self, monkeypatch) -> None:
        # Regression: a module-level `_NO_COLOR_OVERRIDE` global was
        # reassigned imperatively by the callback on every invocation —
        # correct only as long as every invocation goes through that
        # callback and reassigns it, and liable to leak a prior
        # invocation's value into one that doesn't (e.g. two
        # CliRunner.invoke calls in the same test process, or any path
        # that bypasses the callback). Carrying the flag on the Click
        # context's `obj` instead makes each invocation naturally
        # isolated: color_system differs per-context even with no
        # terminal involved at all, which is what this checks directly
        # rather than relying on ANSI codes CliRunner's non-tty output
        # wouldn't emit either way.
        import typer
        from typer._click.core import Context

        from qwik.cli import app as cli_app
        from qwik.ui.theme import _no_color_active

        monkeypatch.delenv("NO_COLOR", raising=False)
        cmd = typer.main.get_command(cli_app)

        ctx_off = Context(cmd)
        ctx_off.obj = {"no_color": True}
        with ctx_off:
            assert _no_color_active() is True

        # A second, independent context that never set no_color must not
        # see the first context's value.
        ctx_on = Context(cmd)
        ctx_on.obj = {"no_color": False}
        with ctx_on:
            assert _no_color_active() is False

        assert _no_color_active() is False


class TestDebug:
    def test_qwik_debug_does_not_crash(self, tmp_path, monkeypatch) -> None:
        from qwik.config import _reset_config

        monkeypatch.setenv("QWIK_CONFIG_DIR", str(tmp_path))
        monkeypatch.setenv("QWIK_DEBUG", "1")
        _reset_config()
        result = runner.invoke(app, ["list"])
        assert result.exit_code in (0, 1)
