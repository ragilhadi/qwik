"""Unit tests for shell renderers."""

import pytest

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
        assert "[ScriptBlock]::Create('git status')" in out
        assert "@args" in out

    def test_pwsh_function_escapes_embedded_quote(self) -> None:
        renderer = get_renderer("pwsh")
        out = renderer.render_alias("q", Alias(command="echo it's fine"))
        assert "[ScriptBlock]::Create('echo it''s fine')" in out

    def test_pwsh_function_brace_cannot_break_out(self) -> None:
        # Regression: a `}` in the command used to be spliced as raw
        # PowerShell source and close the function early.
        renderer = get_renderer("pwsh")
        payload = "echo hi } ; Write-Host PWNED ; function dummy {"
        out = renderer.render_alias("brace", Alias(command=payload))
        # The whole payload — including its literal `}` and the text
        # "function dummy {" — ends up inert inside one string literal,
        # never reaching PowerShell's own parser as code.
        assert out == (
            "function brace {\n"
            f"    & ([ScriptBlock]::Create('{payload}')) @args\n"
            "}"
        )

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
        assert out == "doskey gs=git status $*"

    def test_cmd_skips_template(self) -> None:
        renderer = get_renderer("cmd")
        out = renderer.render_alias("gco", Alias(command="git checkout {1}"))
        assert "omitted" in out or out == ""

    def test_cmd_skips_multiline(self) -> None:
        renderer = get_renderer("cmd")
        out = renderer.render_alias("multi", Alias(command="echo hi\necho bye"))
        assert "omitted" in out
        assert "doskey" not in out

    def test_cmd_escapes_metacharacters(self) -> None:
        renderer = get_renderer("cmd")
        out = renderer.render_alias("danger", Alias(command="echo hi & del /q *"))
        assert out == "doskey danger=echo hi ^& del /q * $*"

    def test_cmd_doubles_dollar_sign(self) -> None:
        # A literal $ must not be misread as a doskey $N/$*/$$ substitution.
        renderer = get_renderer("cmd")
        out = renderer.render_alias("p", Alias(command="echo $HOME"))
        assert out == "doskey p=echo $$HOME $*"

    def test_cmd_brace_payload_has_no_live_ampersand(self) -> None:
        # The pwsh-flavored injection payload from the issue repro: `;`
        # isn't special to cmd.exe (no separator meaning), but `&` is,
        # and there is none in this payload, so it renders as inert text.
        renderer = get_renderer("cmd")
        payload = "echo hi } ; Write-Host PWNED ; function dummy {"
        out = renderer.render_alias("brace", Alias(command=payload))
        assert out == f"doskey brace={payload} $*"

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
        # Nu has no safe way to splice an arbitrary command string into
        # source (unlike pwsh's ScriptBlock.Create), so append mode now
        # delegates to `qwik run` the same way template mode does.
        renderer = get_renderer("nu")
        out = renderer.render_alias("gs", Alias(command="git status"))
        assert out == 'def gs [...args] {\n    qwik run "gs" ...$args\n}'

    def test_nu_brace_payload_cannot_break_out(self) -> None:
        renderer = get_renderer("nu")
        payload = "echo hi } ; Write-Host PWNED ; function dummy {"
        out = renderer.render_alias("brace", Alias(command=payload))
        assert out == 'def brace [...args] {\n    qwik run "brace" ...$args\n}'
        assert out.count("def ") == 1

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
        assert out == 'aliases["gco"] = ["qwik", "run", "gco"]'
        # Must be a list alias (xonsh appends CLI args to it), not a Python
        # call expression like `qwik run(...)`, which is a SyntaxError.
        compile(out, "<xonsh-hook>", "exec")

    def test_xonsh_template_function_is_valid_python(self) -> None:
        renderer = get_renderer("xonsh")
        store = {
            "gco": Alias(command="git checkout {1}"),
            "gs": Alias(command="git status"),
        }
        rendered = renderer.render_all(store)
        compile(rendered, "<xonsh-hook>", "exec")

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


class TestAdversarialCommandMatrix:
    """One adversarial command set x every renderer.

    Each command below is chosen to probe a specific escaping rule this
    renderer or another one in the same family needs: quote characters,
    shell metacharacters, and characters with a special meaning to only
    one of the seven target shells. None of these should ever let text
    escape its containing string/quote and become live code — every
    assertion below is a structural containment check, not a full parse
    (that's what the real-shell integration tests do where the shell is
    available).
    """

    ADVERSARIAL_COMMANDS = [
        'echo "double quoted"',
        "echo 'single quoted'",
        "echo `backtick`",
        "echo $HOME",
        "echo %USERPROFILE%",
        "echo a & b",
        "echo a | b",
        "echo a ^ b",
        "echo a ; b",
        "echo hi } ; function dummy {",
    ]

    def test_every_renderer_survives_every_adversarial_command(self) -> None:
        for shell in supported_shells():
            renderer = get_renderer(shell)
            for command in self.ADVERSARIAL_COMMANDS:
                # Must not raise, and must produce non-empty output for
                # every renderer (cmd's template-mode skip doesn't apply
                # here since none of these are template commands).
                out = renderer.render_alias("adv", Alias(command=command))
                assert out, f"{shell} produced empty output for {command!r}"

    def test_pwsh_every_command_fully_contained_in_scriptblock_literal(self) -> None:
        renderer = get_renderer("pwsh")
        for command in self.ADVERSARIAL_COMMANDS:
            out = renderer.render_alias("adv", Alias(command=command))
            escaped = command.replace("'", "''")
            assert f"[ScriptBlock]::Create('{escaped}')" in out

    def test_cmd_every_command_has_no_live_metacharacter(self) -> None:
        from qwik.shells.cmd import _CMD_METACHARACTERS, _escape_doskey_body

        for command in self.ADVERSARIAL_COMMANDS:
            escaped = _escape_doskey_body(command)
            # Walk the escaped body treating every "^X" as one consumed
            # escape sequence; anything left over must not be a bare
            # metacharacter (a caret always escapes the char right after
            # it, including another caret — "^^" is a literal caret).
            i = 0
            while i < len(escaped):
                if escaped[i] == "^":
                    i += 2
                    continue
                assert escaped[i] not in _CMD_METACHARACTERS, (
                    f"unescaped {escaped[i]!r} in {escaped!r} (from {command!r})"
                )
                i += 1

    def test_nu_every_command_delegates_to_qwik_run(self) -> None:
        renderer = get_renderer("nu")
        for command in self.ADVERSARIAL_COMMANDS:
            out = renderer.render_alias("adv", Alias(command=command))
            assert out == 'def adv [...args] {\n    qwik run "adv" ...$args\n}'
            assert command not in out
