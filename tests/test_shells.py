"""Unit tests for shell renderers."""

from qwik.core.models import Alias
from qwik.shells.base import SUPPORTED_SHELLS, get_renderer


class TestRenderers:
    def test_all_shells_supported(self) -> None:
        for shell in SUPPORTED_SHELLS:
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
        assert "function gs" in out
        assert "git status $argv" in out

    def test_fish_alias_with_quotes(self) -> None:
        renderer = get_renderer("fish")
        out = renderer.render_alias("e", Alias(command="echo 'hello'"))
        assert "function e" in out
        assert "echo \\'hello\\'" in out

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
