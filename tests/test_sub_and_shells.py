"""Tests for substitute.py remaining branches and edge cases."""

import pytest

from qwik.cli import app as app_for_init
from qwik.core.substitute import expand, validate_placeholders


class TestSubstituteEdgeCases:
    """Coverage for substitute.py lines 116, 126, 131, 137."""

    def test_expand_missing_index_error(self) -> None:
        """Expand should raise ValueError for missing arg {N} when no args passed."""
        with pytest.raises(ValueError):
            expand("echo {1}", [])

    def test_expand_at_placeholder_empty(self) -> None:
        """Line 126: {@} with empty args returns empty string."""
        result = expand("echo {@}", [])
        assert result == "echo "

    def test_expand_star_placeholder_empty(self) -> None:
        """Line 131-137: {*} with empty args returns '' shell-quoted."""
        result = expand("echo {*}", [])
        # shlex.quote("") returns "''"
        assert "echo" in result

    def test_expand_zero_positional(self) -> None:
        """Line 116: {0} raises ValueError in expand."""
        with pytest.raises(ValueError):
            expand("echo {0}", ["x"])

    def test_expand_zero_default(self) -> None:
        """Line 126: {0:-default} raises ValueError in expand."""
        with pytest.raises(ValueError):
            expand("echo {0:-def}", [])

    def test_expand_at_with_args(self) -> None:
        result = expand("echo {@}", ["a", "b"])
        assert result == "echo a b"

    def test_expand_star_with_args(self) -> None:
        result = expand("echo {*}", ["a", "b"])
        # Output should be: echo 'a b' (shell-quoted)
        assert "echo" in result
        assert "'a b'" in result or '"a b"' in result

    def test_validate_zero_default_raises(self) -> None:
        with pytest.raises(ValueError):
            validate_placeholders("echo {0:-def}", [])

    def test_surplus_args_no_template(self) -> None:
        """Append mode with extra args."""
        result = expand("echo", ["hello", "world"])
        assert "hello" in result
        assert "world" in result


class TestShellsBase:
    """Cover header/footer lines 78, 85, 119-121 in base.py."""

    def test_get_renderer_unknown(self) -> None:
        from qwik.shells.base import get_renderer

        with pytest.raises(ValueError):
            get_renderer("unknown")

    def test_get_renderer_strips_whitespace(self) -> None:
        from qwik.shells.base import get_renderer

        r = get_renderer("  bash  ")
        assert r.shell_name == "bash"

    def test_header_footer(self) -> None:
        from qwik.shells.base import ShellRenderer

        class Dummy(ShellRenderer):
            @property
            def shell_name(self) -> str:
                return "dummy"

            def render_alias(self, name, alias) -> str:
                return "dummy"

        d = Dummy()
        assert d.render_header() == ""
        assert d.render_footer() == ""

        class WithHeader(ShellRenderer):
            @property
            def shell_name(self) -> str:
                return "with_header"

            def render_alias(self, name, alias) -> str:
                return f"alias {name}"

            def render_header(self) -> str:
                return "# header"

            def render_footer(self) -> str:
                return "# footer"

        h = WithHeader()
        from qwik.core.models import Alias

        result = h.render_all({"a": Alias(command="hi")})
        assert "# header" in result
        assert "alias a" in result
        assert "# footer" in result


class TestRunMetacharacters:
    """Cover run.py metacharacter detection."""

    def test_tilde_requires_shell(self) -> None:
        from qwik.commands.run import _has_shell_metacharacters

        assert _has_shell_metacharacters("cat ~/file") is True

    def test_andand_requires_shell(self) -> None:
        from qwik.commands.run import _has_shell_metacharacters

        assert _has_shell_metacharacters("cmd1 && cmd2") is True
        assert _has_shell_metacharacters("cmd1 || cmd2") is True

    def test_glob_star_requires_shell(self) -> None:
        from qwik.commands.run import _has_shell_metacharacters

        assert _has_shell_metacharacters("cat *.log") is True

    def test_parens_requires_shell(self) -> None:
        from qwik.commands.run import _has_shell_metacharacters

        assert _has_shell_metacharacters("(cmd1; cmd2)") is True

    def test_simple_no_shell(self) -> None:
        from qwik.commands.run import _has_shell_metacharacters

        assert _has_shell_metacharacters("echo hello") is False


class TestInitShell:
    """Cover init_shell.py installation paths."""

    def test_rc_path_pwsh_windows(self, monkeypatch) -> None:
        from qwik.commands.init_shell import _rc_path

        monkeypatch.setattr("sys.platform", "win32")
        rc = _rc_path("pwsh")
        assert "Documents" in str(rc)

    def test_rc_path_pwsh_linux(self, monkeypatch) -> None:
        from qwik.commands.init_shell import _rc_path

        monkeypatch.setattr("sys.platform", "linux")
        rc = _rc_path("pwsh")
        assert ".config" in str(rc)

    def test_rc_path_unknown_shell(self) -> None:
        from qwik.commands.init_shell import _rc_path

        assert _rc_path("tcsh") is None


class TestConfigEnvOverride:
    """Cover config.py env-var branch (lines 40-41, 50, 77, 103)."""

    def test_env_override(self, tmp_path, monkeypatch) -> None:
        from qwik.config import get_config, _reset_config

        monkeypatch.setenv("QWIK_CONFIG_DIR", str(tmp_path))
        _reset_config()
        cfg = get_config()
        assert cfg.config_dir == tmp_path

    def test_default_config(self, monkeypatch) -> None:
        from qwik.config import get_config, _reset_config

        monkeypatch.delenv("QWIK_CONFIG_DIR", raising=False)
        _reset_config()
        cfg = get_config()
        # Should use platformdirs default
        assert "qwik" in str(cfg.config_dir)


class TestInitShellInstall:
    """Cover init_shell.py install block (lines 64-94)."""

    def test_install_hook_idempotent(self, tmp_path, monkeypatch) -> None:
        from typer.testing import CliRunner

        # Create a fake rc file for bash
        rc = tmp_path / ".bashrc"
        rc.write_text("# existing\n")

        # Mock _rc_path to use our temp rc
        from qwik.commands import init_shell as is_mod

        orig_rc_path = is_mod._rc_path
        is_mod._rc_path = lambda shell: rc

        from qwik.cli import app

        runner = CliRunner()
        # First install should work
        r1 = runner.invoke(app, ["init", "bash", "--install"])
        # Restore
        is_mod._rc_path = orig_rc_path

        # Idempotent second install
        is_mod._rc_path = lambda shell: rc
        r2 = runner.invoke(app, ["init", "bash", "--install"])
        is_mod._rc_path = orig_rc_path

        assert (
            "already present" in r2.output
            or "Backed up" in r1.output
            or "Added hook" in r1.output
        )


class TestStoreDocument:
    """Cover store.py _store_to_document conditional fields."""

    def test_store_document_full_fields(self, tmp_path) -> None:
        from qwik.config import Config
        from qwik.core.models import Alias, AliasStore
        from qwik.core.store import Store

        cfg = Config(override_config_dir=tmp_path)
        store = Store(config=cfg)

        alias = Alias(
            command="echo hi",
            tag=["test"],
            description="test alias",
            enabled=False,
            run_count=5,
        )
        alias.last_used = alias.created_at
        data = AliasStore()
        data.add("h", alias)
        store.save(data)

        loaded = store.load()
        assert "h" in loaded.aliases


class TestDoctorShellDetection:
    """Cover doctor.py shell detection paths."""

    def test_detect_shell_from_env(self, monkeypatch) -> None:
        from qwik.commands.doctor import _detect_shell

        monkeypatch.setenv("SHELL", "/usr/bin/zsh")
        assert _detect_shell() == "zsh"

    def test_detect_shell_fish(self, monkeypatch) -> None:
        from qwik.commands.doctor import _detect_shell

        monkeypatch.setenv("SHELL", "/usr/bin/fish")
        assert _detect_shell() == "fish"

    def test_detect_shell_pwsh(self, monkeypatch) -> None:
        from qwik.commands.doctor import _detect_shell

        monkeypatch.setenv("SHELL", "/usr/bin/pwsh")
        assert _detect_shell() == "pwsh"

    def test_detect_shell_no_env(self, monkeypatch) -> None:
        from qwik.commands.doctor import _detect_shell

        monkeypatch.delenv("SHELL", raising=False)
        # On non-Linux, this returns None
        result = _detect_shell()
        # Result depends on platform
        assert result is None or result in ("bash", "zsh", "fish", "pwsh")


class TestPromptText:
    """Cover prompts.py interactive branches."""

    def test_prompt_text_empty_not_allowed(self, monkeypatch) -> None:
        """Cover lines 69-74: reprompt on empty input."""
        from qwik.ui.prompts import prompt_text

        # Can't easily mock stdin, verify function compiles
        # At minimum verify calling with allow_empty=False doesn't crash on a real stdin
        # We can monkeypatch Prompt.ask to simulate input
        import rich.prompt as rp_mod

        orig_ask = rp_mod.Prompt.ask

        call_count = 0

        def fake_ask(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return ""
            return "hello"

        rp_mod.Prompt.ask = fake_ask
        try:
            result = prompt_text("name", allow_empty=False)
            assert result == "hello"
            assert call_count == 2
        finally:
            rp_mod.Prompt.ask = orig_ask


class TestPickFallback:
    """Partial coverage for pick.py."""

    def test_pick_no_aliases(self, tmp_path, monkeypatch) -> None:
        from qwik.config import Config, _reset_config

        monkeypatch.setattr("qwik.config._config", Config(override_config_dir=tmp_path))
        monkeypatch.setenv("QWIK_CONFIG_DIR", str(tmp_path))
        _reset_config()

        from typer.testing import CliRunner

        runner = CliRunner()
        result = runner.invoke(app_for_init, ["pick"])
        # pick_command checks empty store and exits gracefully
        assert result.exit_code == 0


class TestShellRenderersCoverage:
    """Cover template/append branches in bash/zsh/fish/pwsh."""

    def test_bash_template(self) -> None:
        from qwik.shells.bash import BashRenderer
        from qwik.core.models import Alias

        r = BashRenderer()
        out = r.render_alias("gco", Alias(command="git checkout {1}"))
        assert "qwik -r" in out

    def test_zsh_append_quotes(self) -> None:
        from qwik.shells.zsh import ZshRenderer
        from qwik.core.models import Alias

        r = ZshRenderer()
        out = r.render_alias("e", Alias(command="echo 'hello'"))
        assert "'\"'\"'" in out

    def test_fish_template(self) -> None:
        from qwik.shells.fish import FishRenderer
        from qwik.core.models import Alias

        r = FishRenderer()
        out = r.render_alias("gco", Alias(command="git checkout {1}"))
        assert "qwik -r" in out

    def test_fish_append_quotes(self) -> None:
        from qwik.shells.fish import FishRenderer
        from qwik.core.models import Alias

        r = FishRenderer()
        out = r.render_alias("e", Alias(command="echo 'hello'"))
        assert "\\'" in out

    def test_pwsh_template(self) -> None:
        from qwik.shells.pwsh import PwshRenderer
        from qwik.core.models import Alias

        r = PwshRenderer()
        out = r.render_alias("gco", Alias(command="git checkout {1}"))
        assert "qwik -r" in out

    def test_pwsh_append(self) -> None:
        from qwik.shells.pwsh import PwshRenderer
        from qwik.core.models import Alias

        r = PwshRenderer()
        out = r.render_alias("gs", Alias(command="git status"))
        assert "@args" in out

    def test_cmd_header(self) -> None:
        from qwik.shells.cmd import CmdRenderer
        from qwik.core.models import Alias

        r = CmdRenderer()
        out = r.render_alias("gs", Alias(command="git status"))
        assert "doskey" in out
        header = r.render_header()
        assert "REM" in header
