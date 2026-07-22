"""Tests for AliasStore overlay_aliases field and all_aliases()."""

from __future__ import annotations

from qwik.core.models import Alias, AliasStore


def test_overlay_aliases_default_empty() -> None:
    store = AliasStore()
    assert store.overlay_aliases == {}


def test_all_aliases_user_wins() -> None:
    store = AliasStore()
    store.add("gs", Alias(command="git status"))
    store.overlay_aliases["gs"] = Alias(command="git stash")
    store.overlay_aliases["gco"] = Alias(command="git checkout {1}")
    merged = store.all_aliases()
    assert merged["gs"].command == "git status"
    assert merged["gco"].command == "git checkout {1}"


def test_all_aliases_no_overlay() -> None:
    store = AliasStore()
    store.add("gs", Alias(command="git status"))
    merged = store.all_aliases()
    assert merged == store.aliases


def test_overlay_aliases_not_serialized(tmp_path) -> None:
    import tomlkit

    from qwik.core.store import Store

    store = AliasStore()
    store.add("gs", Alias(command="git status"))
    store.overlay_aliases["gco"] = Alias(command="git checkout {1}")
    doc = Store._store_to_document(store)
    raw = tomlkit.dumps(doc)
    assert "overlay" not in raw
    assert "gco" not in raw
