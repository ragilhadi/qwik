"""Tests for `qwik stats` — usage dashboard (issue #37)."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from typer.testing import CliRunner

from qwik.cli import app
from qwik.config import _reset_config
from qwik.core.models import Alias, AliasStore
from qwik.core.stats import (
    AliasUsage,
    compute_overview,
    compute_top,
    compute_unused,
    estimate_time_saved,
    format_timedelta,
    parse_since,
)
from qwik.core.store import get_store

runner = CliRunner()


def _setup(tmp_path: Any, monkeypatch: Any) -> None:
    monkeypatch.setenv("QWIK_CONFIG_DIR", str(tmp_path))
    _reset_config()


def _add_alias(name: str, command: str, **kwargs: Any) -> None:
    store = get_store()
    with store.mutate() as data:
        data.add(name, Alias(command=command, **kwargs), force=True)


def _seed_usage(name: str, run_count: int, ago: timedelta | None) -> None:
    store = get_store()
    now = datetime.now(UTC)
    with store.mutate() as data:
        alias = data.get(name)
        assert alias is not None
        alias.run_count = run_count
        alias.last_used = None if ago is None else now - ago


class TestParseSince:
    def test_days(self) -> None:
        assert parse_since("90d") == timedelta(days=90)

    def test_hours(self) -> None:
        assert parse_since("12h") == timedelta(hours=12)

    def test_weeks(self) -> None:
        assert parse_since("2w") == timedelta(weeks=2)

    def test_minutes(self) -> None:
        assert parse_since("30m") == timedelta(minutes=30)

    @pytest.mark.parametrize("bad", ["", "d", "bogus", "-7d", "0d", "7x"])
    def test_invalid(self, bad: str) -> None:
        with pytest.raises(ValueError):
            parse_since(bad)


class TestComputeFunctions:
    def _populate(self) -> AliasStore:
        store = AliasStore()
        store.add("gs", Alias(command="git status", group="git"))
        store.add("dcu", Alias(command="docker compose up -d", group="docker"))
        store.add("k9s", Alias(command="k9s"))
        _gs = store.get("gs")
        _dcu = store.get("dcu")
        store.aliases["gs"].run_count = 312
        store.aliases["gs"].last_used = datetime.now(UTC) - timedelta(minutes=2)
        store.aliases["dcu"].run_count = 188
        store.aliases["dcu"].last_used = datetime.now(UTC) - timedelta(hours=1)
        return store

    def test_compute_top_orders_by_runs(self) -> None:
        store = self._populate()
        top = compute_top(store, 2)
        assert [r.name for r in top] == ["gs", "dcu"]

    def test_compute_top_ties_broken_by_name(self) -> None:
        store = AliasStore()
        store.add("zz", Alias(command="a"))
        store.add("aa", Alias(command="b"))
        top = compute_top(store, 10)
        assert [r.name for r in top] == ["aa", "zz"]

    def test_compute_top_zero_or_negative(self) -> None:
        store = self._populate()
        assert compute_top(store, 0) == []
        assert compute_top(store, -1) == []

    def test_compute_unused_never_used(self) -> None:
        store = self._populate()
        unused = compute_unused(store)
        assert [r.name for r in unused] == ["k9s"]

    def test_compute_unused_with_since(self) -> None:
        store = self._populate()
        unused = compute_unused(store, since=timedelta(minutes=30))
        # dcu ran 1 hour ago → outside the 30 min window; k9s never ran.
        assert [r.name for r in unused] == ["dcu", "k9s"]

    def test_compute_overview_totals(self) -> None:
        store = self._populate()
        overview = compute_overview(store)
        assert overview.total_aliases == 3
        assert overview.total_runs == 500
        assert overview.busiest_group is not None
        assert overview.busiest_group.group == "git"

    def test_compute_overview_recency_window(self) -> None:
        store = self._populate()
        overview = compute_overview(store, since=timedelta(minutes=30))
        # only gs (2 min ago) falls inside the window
        assert overview.recent_used == 1


class TestFormatHelpers:
    def test_format_timedelta_zero(self) -> None:
        assert format_timedelta(timedelta(0)) == "~0 min"

    def test_format_timedelta_mixed(self) -> None:
        assert format_timedelta(timedelta(hours=4, minutes=12)) == "~4 h 12 min"

    def test_format_timedelta_seconds_only(self) -> None:
        assert format_timedelta(timedelta(seconds=35)) == "~35 s"

    def test_estimate_time_saved_scales_with_runs(self) -> None:
        alias = Alias(command="docker compose up -d")
        row = AliasUsage(name="dcu", alias=alias, is_overlay=False)
        one = estimate_time_saved([row])
        alias10 = Alias(command="docker compose up -d", run_count=10)
        ten = estimate_time_saved([AliasUsage(name="dcu", alias=alias10, is_overlay=False)])
        assert ten >= one * 10


class TestStatsCommand:
    def test_summary_numbers(self, tmp_path, monkeypatch) -> None:
        _setup(tmp_path, monkeypatch)
        _add_alias("gs", "git status", group="git")
        _seed_usage("gs", 312, timedelta(minutes=2))
        result = runner.invoke(app, ["stats"])
        assert result.exit_code == 0
        assert "1 alias" in result.output
        assert "312 runs" in result.output

    def test_top_view(self, tmp_path, monkeypatch) -> None:
        _setup(tmp_path, monkeypatch)
        _add_alias("gs", "git status")
        _add_alias("dcu", "docker compose up")
        _seed_usage("gs", 312, timedelta(minutes=2))
        _seed_usage("dcu", 188, timedelta(hours=1))
        result = runner.invoke(app, ["stats", "--top", "1"])
        assert result.exit_code == 0
        assert "gs" in result.output
        assert "dcu" not in result.output

    def test_unused_view(self, tmp_path, monkeypatch) -> None:
        _setup(tmp_path, monkeypatch)
        _add_alias("gs", "git status")
        _add_alias("k9s", "k9s")
        _seed_usage("gs", 5, timedelta(minutes=2))
        result = runner.invoke(app, ["stats", "--unused"])
        assert result.exit_code == 0
        assert "k9s" in result.output
        assert "gs" not in result.output
        assert "--prune" in result.output

    def test_unused_with_since(self, tmp_path, monkeypatch) -> None:
        _setup(tmp_path, monkeypatch)
        _add_alias("gs", "git status")
        _add_alias("stale", "st")
        _seed_usage("gs", 5, timedelta(minutes=5))
        result = runner.invoke(app, ["stats", "--unused", "--since", "1h"])
        assert result.exit_code == 0
        assert "stale" in result.output
        assert "gs" not in result.output

    def test_json_valid_no_markup(self, tmp_path, monkeypatch) -> None:
        _setup(tmp_path, monkeypatch)
        _add_alias("gs", "git status", group="git")
        _seed_usage("gs", 42, timedelta(minutes=2))
        result = runner.invoke(app, ["stats", "--json"])
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["total_aliases"] == 1
        assert payload["total_runs"] == 42
        top = payload["top"]  # bare --json has no --top request
        assert top == []

    def test_json_with_top_and_unused(self, tmp_path, monkeypatch) -> None:
        _setup(tmp_path, monkeypatch)
        _add_alias("gs", "git status")
        _add_alias("k9s", "k9s")
        _seed_usage("gs", 42, timedelta(minutes=2))
        result = runner.invoke(app, ["stats", "--top", "1", "--unused", "--json"])
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert [a["name"] for a in payload["top"]] == ["gs"]
        assert [a["name"] for a in payload["unused"]] == ["k9s"]

    def test_empty_store_friendly(self, tmp_path, monkeypatch) -> None:
        _setup(tmp_path, monkeypatch)
        result = runner.invoke(app, ["stats"])
        assert result.exit_code == 0
        assert "No aliases yet" in result.output

    def test_empty_store_json(self, tmp_path, monkeypatch) -> None:
        _setup(tmp_path, monkeypatch)
        result = runner.invoke(app, ["stats", "--json"])
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["total_aliases"] == 0
        assert payload["total_runs"] == 0
        assert payload["top"] == []
        assert payload["unused"] == []

    def test_invalid_since_errors(self, tmp_path, monkeypatch) -> None:
        _setup(tmp_path, monkeypatch)
        result = runner.invoke(app, ["stats", "--since", "bogus"])
        assert result.exit_code == 1
        assert "Invalid --since" in result.output

    def test_top_zero_errors(self, tmp_path, monkeypatch) -> None:
        _setup(tmp_path, monkeypatch)
        result = runner.invoke(app, ["stats", "--top", "0"])
        assert result.exit_code == 1
        assert "positive" in result.output

    def test_prune_requires_unused(self, tmp_path, monkeypatch) -> None:
        _setup(tmp_path, monkeypatch)
        result = runner.invoke(app, ["stats", "--prune"])
        assert result.exit_code == 1
        assert "--prune requires --unused" in result.output

    def test_prune_confirms_and_removes(self, tmp_path, monkeypatch) -> None:
        _setup(tmp_path, monkeypatch)
        _add_alias("gs", "git status")
        _add_alias("k9s", "k9s")
        result = runner.invoke(app, ["stats", "--unused", "--prune"], input="y\n")
        assert result.exit_code == 0
        assert "Pruned 2 aliases" in result.output
        assert list(get_store().load().aliases) == []

    def test_prune_writes_backup(self, tmp_path, monkeypatch) -> None:
        _setup(tmp_path, monkeypatch)
        _add_alias("k9s", "k9s")
        config_dir = tmp_path / "backups"
        result = runner.invoke(app, ["stats", "--unused", "--prune"], input="y\n")
        assert result.exit_code == 0
        backups = list(config_dir.glob("aliases-*.toml"))
        assert len(backups) >= 1

    def test_prune_declined_removes_nothing(self, tmp_path, monkeypatch) -> None:
        _setup(tmp_path, monkeypatch)
        _add_alias("k9s", "k9s")
        result = runner.invoke(app, ["stats", "--unused", "--prune"], input="n\n")
        assert result.exit_code == 0
        assert "cancelled" in result.output
        assert "k9s" in get_store().load().aliases

    def test_prune_skips_overlays(self, tmp_path, monkeypatch) -> None:
        _setup(tmp_path, monkeypatch)
        # A never-used overlay alias must not be removed by --prune.
        _add_alias("user-alias", "echo hi")
        import tomlkit

        (tmp_path / "overlay.toml").write_text(
            tomlkit.dumps({"url": "https://example.com", "branch": "main", "auto_update": False})
        )
        overlay_repo = tmp_path / "overlay-repo"
        overlay_repo.mkdir(parents=True)
        doc = tomlkit.document()
        doc.add("version", 1)
        aliases_table = tomlkit.table()
        overlay_alias_table = tomlkit.table()
        overlay_alias_table.add("command", "echo overlay")
        aliases_table.add("ov", overlay_alias_table)
        doc.add("aliases", aliases_table)
        (overlay_repo / "aliases.toml").write_text(tomlkit.dumps(doc))

        fresh = get_store().load()
        assert "ov" in fresh.overlay_aliases
        result = runner.invoke(app, ["stats", "--unused", "--prune"], input="y\n")
        assert result.exit_code == 0
        assert "read-only" in result.output
        after = get_store().load()
        assert "ov" in after.overlay_aliases
        assert "user-alias" not in after.aliases

    def test_prune_nothing_to_remove_message(self, tmp_path, monkeypatch) -> None:
        _setup(tmp_path, monkeypatch)
        result = runner.invoke(app, ["stats", "--unused"])
        assert result.exit_code == 0


class TestStatsRendering:
    def test_render_stats_overview_smoke(self) -> None:
        from qwik.ui.tables import render_stats

        store = AliasStore()
        store.add("gs", Alias(command="git status", group="git"))
        store.aliases["gs"].run_count = 3
        overview = compute_overview(store)
        table = render_stats(store, overview=overview)
        assert table is not None

    def test_render_stats_top_empty(self) -> None:
        from qwik.ui.tables import render_stats

        store = AliasStore()
        store.add("gs", Alias(command="git status"))
        table = render_stats(store, top_rows=[], unused_rows=None)
        assert table is not None

    def test_render_stats_marks_overlay(self) -> None:
        from qwik.ui.tables import render_stats

        store = AliasStore()
        store.add("gs", Alias(command="git status"))
        store.overlay_aliases["ov-alias"] = Alias(command="echo overlay")
        top = compute_top(store, 10)
        assert any(r.is_overlay for r in top)
        table = render_stats(store, top_rows=top, unused_rows=None)
        assert table is not None
