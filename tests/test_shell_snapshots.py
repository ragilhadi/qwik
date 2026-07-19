"""Syrupy snapshots locking per-shell ``render_all`` output.

Covers bash, zsh, fish, pwsh and cmd against a fixed ``AliasStore`` so
that any cross-shell rendering change shows up as a readable diff.
"""

from __future__ import annotations

import pytest

from qwik.core.models import Alias, AliasStore
from qwik.shells.base import SUPPORTED_SHELLS, get_renderer


def _build_store() -> AliasStore:
    store = AliasStore()
    store.add("gco", Alias(command="git checkout {1}"))
    store.add("gs", Alias(command="git status"))
    store.add("lsg", Alias(command="echo 'hello world'"))
    store.add("envg", Alias(command="echo $HOME %USERPROFILE%"))
    return store


@pytest.mark.parametrize("shell", SUPPORTED_SHELLS)
def test_render_all_snapshot(shell: str, snapshot: str) -> None:
    store = _build_store()
    rendered = get_renderer(shell).render_all(store.aliases)
    assert rendered == snapshot