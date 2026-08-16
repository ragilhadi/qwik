"""Tests for theme, tables, prompts, and search coverage gaps."""

from datetime import UTC, datetime, timedelta

import pytest

from qwik.core.models import Alias, AliasStore
from qwik.core.search import search_aliases
from qwik.ui.tables import render_list_table
from qwik.ui.theme import get_console, style


class TestTheme:
    def test_get_console_returns_console(self) -> None:
        c = get_console()
        assert c is not None

    def test_style_lookup(self) -> None:
        """Line 58 in theme.py - style() function."""
        s = style("qwik.success")
        assert s is not None

    def test_no_color_env(self, monkeypatch) -> None:
        """Cover NO_COLOR branch (lazy env read)."""
        monkeypatch.setenv("NO_COLOR", "1")
        import qwik.ui.theme as theme_mod

        assert theme_mod._no_color_active() is True
        monkeypatch.delenv("NO_COLOR", raising=False)
        assert theme_mod._no_color_active() is False


class TestTables:
    def test_search_query_filter(self) -> None:
        """Cover lines 56, 58-60 in tables.py."""
        store = AliasStore()
        store.add("gs", Alias(command="git status"))
        store.add("ls", Alias(command="ls -la"))
        table = render_list_table(store, search_query="status")
        # Table should render; we verify no crash
        assert table is not None
        # "gs" would be highlighted but "ls" filtered

    def test_tag_filter(self) -> None:
        store = AliasStore()
        store.add("gs", Alias(command="git status", tag=["git"]))
        store.add("ls", Alias(command="ls -la", tag=["system"]))
        table = render_list_table(store, tag_filter="git")
        assert table is not None

    def test_disabled_alias_dim(self) -> None:
        store = AliasStore()
        alias = Alias(command="echo hi", enabled=False)
        store.add("h", alias)
        table = render_list_table(store)
        assert table is not None


class TestSearch:
    def test_enabled_only_filter(self) -> None:
        """Cover line 72/74/79 in search.py."""
        store = AliasStore()
        alias = Alias(command="echo hi", enabled=False)
        store.add("h", alias)
        # Without filter, disabled alias appears
        results = search_aliases(store, "h")
        assert len(results) == 1
        # With enabled_only, filtered out
        results = search_aliases(store, "h", enabled_only=True)
        assert len(results) == 0

    def test_search_empty_query(self) -> None:
        store = AliasStore()
        store.add("a", Alias(command="echo a"))
        store.add("b", Alias(command="echo b"))
        results = search_aliases(store, "")
        assert len(results) == 2

    def test_search_with_tag_filter(self) -> None:
        store = AliasStore()
        store.add("gs", Alias(command="git status", tag=["git"]))
        store.add("ls", Alias(command="ls -la"))
        results = search_aliases(store, "git", tag="git")
        assert len(results) == 1
        assert results[0][0] == "gs"

    def test_search_empty_query_respects_limit(self) -> None:
        # Regression: the empty-query early return skipped the limit
        # slice entirely, so a caller asking for e.g. 20 results could
        # get back every alias in the store — on the picker's hot path,
        # called on every keystroke including the initial empty render.
        store = AliasStore()
        for i in range(500):
            store.add(f"a{i}", Alias(command="x"))
        results = search_aliases(store, "", limit=20)
        assert len(results) == 20

    def test_search_whitespace_query_respects_limit(self) -> None:
        store = AliasStore()
        for i in range(500):
            store.add(f"a{i}", Alias(command="x"))
        results = search_aliases(store, "   ", limit=20)
        assert len(results) == 20

    def test_search_non_matching_query_respects_limit(self) -> None:
        store = AliasStore()
        for i in range(500):
            store.add(f"a{i}", Alias(command="x"))
        results = search_aliases(store, "zzz-does-not-match-anything", limit=20)
        assert len(results) == 20

    def test_search_empty_query_alphabetical_order_preserved(self) -> None:
        # The limit fix must not disturb the empty-query path's
        # alphabetical sort.
        store = AliasStore()
        for name in ["charlie", "alpha", "bravo"]:
            store.add(name, Alias(command="x"))
        results = search_aliases(store, "", limit=10)
        assert [name for name, _, _ in results] == ["alpha", "bravo", "charlie"]

    def test_search_empty_query_limit_larger_than_store(self) -> None:
        store = AliasStore()
        store.add("a", Alias(command="x"))
        results = search_aliases(store, "", limit=50)
        assert len(results) == 1


class TestModelsCoverage:
    def test_format_last_used_hours(self) -> None:
        """Cover format_last_used 'hour(s) ago' branch (line 108)."""
        alias = Alias(command="echo hi")
        alias.last_used = datetime.now(UTC) - timedelta(hours=2)
        assert "hour" in alias.format_last_used()

    def test_format_last_used_days(self) -> None:
        """Cover format_last_used 'day(s) ago' branch (line 106)."""
        alias = Alias(command="echo hi")
        alias.last_used = datetime.now(UTC) - timedelta(days=3)
        assert "day" in alias.format_last_used()

    def test_format_last_used_just_now(self) -> None:
        """Cover format_last_used 'just now' branch (line 113)."""
        alias = Alias(command="echo hi")
        alias.bump_usage()
        assert alias.format_last_used() == "just now"

    def test_alias_add_duplicate(self) -> None:
        """Cover line 161: KeyError in AliasStore.add."""
        store = AliasStore()
        store.add("h", Alias(command="echo hi"))
        with pytest.raises(KeyError):
            store.add("h", Alias(command="echo again"))

    def test_alias_remove_missing(self) -> None:
        """Cover line 177: KeyError in AliasStore.remove."""
        store = AliasStore()
        with pytest.raises(KeyError):
            store.remove("missing")

    def test_alias_rename_target_exists(self) -> None:
        """Cover line 193/195: KeyError in AliasStore.rename."""
        store = AliasStore()
        store.add("a", Alias(command="echo a"))
        store.add("b", Alias(command="echo b"))
        with pytest.raises(KeyError):
            store.rename("a", "b")

    def test_alias_rename_missing_source(self) -> None:
        """Cover line 193: KeyError for missing source."""
        store = AliasStore()
        with pytest.raises(KeyError):
            store.rename("missing", "new")

    def test_validate_alias_name_invalid(self) -> None:
        from qwik.core.models import validate_alias_name

        with pytest.raises(ValueError):
            validate_alias_name("123bad")

    def test_alias_store_coerce_tag_string(self) -> None:
        """Cover line 78-79: tag coercion from string."""
        alias = Alias(command="hi", tag="git, work")
        assert alias.tag == ["git", "work"]

    def test_alias_store_coerce_tag_none(self) -> None:
        """Cover line 80-81: tag coercion from None."""
        alias = Alias(command="hi", tag=None)
        assert alias.tag == []

    def test_bump_usage_updates_stats(self) -> None:
        alias = Alias(command="echo hi")
        assert alias.run_count == 0
        assert alias.last_used is None
        alias.bump_usage()
        assert alias.run_count == 1
        assert alias.last_used is not None
