"""Unit tests for shell renderers."""

from qwik.core.models import Alias
from qwik.shells.base import supported_shells, get_renderer
from qwik.shells.bash import BashRenderer
from qwik.shells.zsh import ZshRenderer


class TestRenderers:
    def test_all_shells_supported(self) -> None:
        for shell in supported_shells():
            renderer = get_renderer(shell)
            assert renderer.shell_name == shell

    def test_bash_append_alias(self) -> None:
        renderer = get_renderer("bash")
        out = renderer.render_alias("gs", Alias(command="git status"))
        assert out == "alias gs='git status'"

    def test_bash_append_alias_with_quotes(self) -> None:
        """Single quotes inside commands must be escaped (issue #2)."""
        renderer = get_renderer("bash")
        out = renderer.render_alias("e", Alias(command="echo 'hello'"))
        assert "'\"'\"'" in out
        assert "alias e=" in out

    def test_bash_template_function(self) -> None:
        renderer = get_renderer("bash")
        out = renderer.render_alias("gco", Alias(command="git checkout {1}"))
        assert 'qwik run "gco" "$@"' in out

    def test_bash_append_alias_with_trailing_backslash(self) -> None:
        """Bash single quotes are literal; backslash needs no escaping."""
        out = BashRenderer().render_alias("bsg", Alias(command="echo hello\\"))
        assert out == "alias bsg='echo hello\\'"

    def test_zsh_append_alias_with_trailing_backslash(self) -> None:
        """Zsh single quotes are literal; backslash needs no escaping."""
        out = ZshRenderer().render_alias("bsg", Alias(command="echo hello\\"))
        assert out == "alias bsg='echo hello\\'"

    def test_zsh_append_alias_with_quotes(self) -> None:
        renderer = get_renderer("zsh")
        out = renderer.render_alias("e", Alias(command="echo 'hello'"))
        assert "'\"'\"'" in out

    def test_pwsh_function(self) -> None:
        renderer = get_renderer("pwsh")
        out = renderer.render_alias("gs", Alias(command="git status"))
        assert "function gs" in out
        assert "git status @args" in out

    def test_fish_alias(self) -> None:
        renderer = get_renderer("fish")
        out = renderer.render_alias("gs", Alias(command="git status"))
        assert out == "alias gs 'git status'"

    def test_fish_alias_with_quotes(self) -> None:
        renderer = get_renderer("fish")
        out = renderer.render_alias("e", Alias(command="echo 'hello'"))
        assert out == "alias e 'echo \\'hello\\''"

    def test_fish_append_quoted(self) -> None:
        from qwik.core.models import Alias
        from qwik.shells.fish import FishRenderer

        out = FishRenderer().render_alias("gco", Alias(command="git checkout 'main'"))
        # The command must be wrapped in single quotes so the embedded \' escapes work
        assert out == "alias gco 'git checkout \\'main\\''"

    def test_fish_template_alias_still_uses_function(self) -> None:
        renderer = get_renderer("fish")
        out = renderer.render_alias("gco", Alias(command="git checkout {1}"))
        assert "function gco" in out
        assert 'qwik run "gco" $argv' in out

    def test_cmd_best_effort(self) -> None:
        renderer = get_renderer("cmd")
        out = renderer.render_alias("gs", Alias(command="git status"))
        assert "doskey" in out

    def test_cmd_skips_template(self) -> None:
        renderer = get_renderer("cmd")
        out = renderer.render_alias("gco", Alias(command="git checkout {1}"))
        assert "omitted" in out or out == ""

    def test_render_all_respects_disabled(self) -> None:
        renderer = get_renderer("bash")
        aliases = {
            "gs": Alias(command="git status"),
            "gd": Alias(command="git diff", enabled=False),
        }
        out = renderer.render_all(aliases)
        assert "alias gs" in out
        assert "gd" not in out

    def test_nu_template_function(self) -> None:
        renderer = get_renderer("nu")
        out = renderer.render_alias("gco", Alias(command="git checkout {1}"))
        assert 'qwik run "gco"' in out
        assert "...$args" in out

    def test_nu_append_function(self) -> None:
        renderer = get_renderer("nu")
        out = renderer.render_alias("gs", Alias(command="git status"))
        assert "def gs" in out
        assert "^git status" in out

    def test_nu_rc_path(self, tmp_path, monkeypatch) -> None:
        from qwik.shells.nu import NuRenderer

        monkeypatch.delenv("NU_CONFIG_DIR", raising=False)
        monkeypatch.setenv("HOME", str(tmp_path))
        rc = NuRenderer().rc_path()
        assert rc is not None
        assert "nushell" in str(rc).lower()

    def test_nu_rc_path_env_override(self, tmp_path, monkeypatch) -> None:
        from qwik.shells.nu import NuRenderer

        custom = tmp_path / "nuconfig"
        monkeypatch.setenv("NU_CONFIG_DIR", str(custom))
        rc = NuRenderer().rc_path()
        assert rc == custom / "config.nu"

    def test_xonsh_template_function(self) -> None:
        renderer = get_renderer("xonsh")
        out = renderer.render_alias("gco", Alias(command="git checkout {1}"))
        assert 'qwik run' in out
        assert "gco" in out

    def test_xonsh_append_alias(self) -> None:
        renderer = get_renderer("xonsh")
        out = renderer.render_alias("gs", Alias(command="git status"))
        assert "aliases" in out
        assert "git status" in out

    def test_xonsh_rc_path(self, tmp_path, monkeypatch) -> None:
        from qwik.shells.xonsh import XonshRenderer

        monkeypatch.delenv("XONSHRC", raising=False)
        monkeypatch.setenv("HOME", str(tmp_path))
        rc = XonshRenderer().rc_path()
        assert rc is not None
        assert rc.name == ".xonshrc"

    def test_xonsh_rc_path_env_override(self, tmp_path, monkeypatch) -> None:
        from qwik.shells.xonsh import XonshRenderer

        custom = tmp_path / "custom.xonshrc"
        monkeypatch.setenv("XONSHRC", str(custom))
        rc = XonshRenderer().rc_path()
        assert rc == custom
