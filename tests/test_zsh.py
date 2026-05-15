"""Tests for zsh shell renderer."""

from __future__ import annotations

from qwik.core.models import Alias
from qwik.shells.zsh import ZshRenderer


class TestZshRenderer:
    def test_zsh_basic_append(self) -> None:
        r = ZshRenderer()
        out = r.render_alias("gs", Alias(command="git status"))
        assert out == "alias gs='git status'"

    def test_zsh_append_no_quotes(self) -> None:
        r = ZshRenderer()
        out = r.render_alias("ls", Alias(command="ls -la"))
        assert out == "alias ls='ls -la'"

    def test_zsh_append_quotes(self) -> None:
        r = ZshRenderer()
        out = r.render_alias("e", Alias(command="echo 'hello'"))
        assert "'\"'\"'" in out
