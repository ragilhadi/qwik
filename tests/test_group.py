"""Tests for the group and ungroup commands plus --group support."""

from __future__ import annotations

from typer.testing import CliRunner

from qwik.cli import app
from qwik.core.models import AliasStore
from qwik.core.store import get_store

runner = CliRunner()


def _setup(tmp_path, monkeypatch) -> None:
    from qwik.config import _reset_config

    monkeypatch.setenv("QWIK_CONFIG_DIR", str(tmp_path))
    _reset_config()


class TestGroupUngroup:
    def test_group_sets_group(self, tmp_path, monkeypatch) -> None:
        _setup(tmp_path, monkeypatch)
        runner.invoke(app, ["add", "gs", "git", "status"])
        result = runner.invoke(app, ["group", "gs", "git"])
        assert result.exit_code == 0
        assert "Grouped" in result.output
        store = get_store().load()
        assert store.get("gs").group == "git"

    def test_ungroup_clears_group(self, tmp_path, monkeypatch) -> None:
        _setup(tmp_path, monkeypatch)
        runner.invoke(app, ["add", "gs", "git", "status", "--group", "git"])
        result = runner.invoke(app, ["ungroup", "gs"])
        assert result.exit_code == 0
        store = get_store().load()
        assert store.get("gs").group is None

    def test_group_unknown_alias_errors(self, tmp_path, monkeypatch) -> None:
        _setup(tmp_path, monkeypatch)
        result = runner.invoke(app, ["group", "nope", "git"])
        assert result.exit_code == 1
        assert "does not exist" in result.output

    def test_ungroup_unknown_alias_errors(self, tmp_path, monkeypatch) -> None:
        _setup(tmp_path, monkeypatch)
        result = runner.invoke(app, ["ungroup", "nope"])
        assert result.exit_code == 1
        assert "does not exist" in result.output

    def test_group_invalid_name_errors(self, tmp_path, monkeypatch) -> None:
        _setup(tmp_path, monkeypatch)
        runner.invoke(app, ["add", "gs", "git", "status"])
        result = runner.invoke(app, ["group", "gs", "1bad"])
        assert result.exit_code == 1
        assert "Invalid group" in result.output

    def test_group_command_strips_whitespace(self, tmp_path, monkeypatch) -> None:
        _setup(tmp_path, monkeypatch)
        runner.invoke(app, ["add", "gs", "git", "status"])
        result = runner.invoke(app, ["group", "gs", "  git  "])
        assert result.exit_code == 0
        assert "Grouped" in result.output
        store = get_store().load()
        assert store.get("gs").group == "git"

    def test_ungroup_noop_when_no_group(self, tmp_path, monkeypatch) -> None:
        _setup(tmp_path, monkeypatch)
        runner.invoke(app, ["add", "gs", "git", "status"])
        result = runner.invoke(app, ["ungroup", "gs"])
        assert result.exit_code == 0
        assert "no group" in result.output.lower()

    def test_group_persists_roundtrip(self, tmp_path, monkeypatch) -> None:
        _setup(tmp_path, monkeypatch)
        runner.invoke(app, ["add", "gs", "git", "status"])
        runner.invoke(app, ["group", "gs", "work"])
        store = get_store().load()
        assert store.get("gs").group == "work"
        store2 = get_store().load()
        assert store2.get("gs").group == "work"


class TestAddWithGroup:
    def test_add_with_group_long(self, tmp_path, monkeypatch) -> None:
        _setup(tmp_path, monkeypatch)
        result = runner.invoke(app, ["add", "gs", "git", "status", "--group", "git"])
        assert result.exit_code == 0
        assert "Added" in result.output
        store = get_store().load()
        assert store.get("gs").group == "git"

    def test_add_with_group_short(self, tmp_path, monkeypatch) -> None:
        _setup(tmp_path, monkeypatch)
        result = runner.invoke(app, ["add", "gs", "git", "status", "-g", "git"])
        assert result.exit_code == 0
        store = get_store().load()
        assert store.get("gs").group == "git"

    def test_add_global_flag_rejected(self, tmp_path, monkeypatch) -> None:
        _setup(tmp_path, monkeypatch)
        result = runner.invoke(app, ["add", "gs", "git", "status", "--global"])
        assert result.exit_code != 0

    def test_add_g_means_group_not_global(self, tmp_path, monkeypatch) -> None:
        _setup(tmp_path, monkeypatch)
        result = runner.invoke(app, ["add", "gs", "git", "status", "-g", "team"])
        assert result.exit_code == 0
        store = get_store().load()
        assert store.get("gs").group == "team"


class TestListGroupFilter:
    def test_list_group_filter(self, tmp_path, monkeypatch) -> None:
        _setup(tmp_path, monkeypatch)
        runner.invoke(app, ["add", "gs", "git", "status", "--group", "git"])
        runner.invoke(app, ["add", "ls", "ls", "-la"])
        result = runner.invoke(app, ["list", "--group", "git"])
        assert result.exit_code == 0
        assert "gs" in result.output
        assert "ls" not in result.output

    def test_list_group_filter_short(self, tmp_path, monkeypatch) -> None:
        _setup(tmp_path, monkeypatch)
        runner.invoke(app, ["add", "gs", "git", "status", "-g", "git"])
        result = runner.invoke(app, ["list", "-g", "git"])
        assert result.exit_code == 0
        assert "gs" in result.output


class TestSearchGroupFilter:
    def test_search_group_filter(self, tmp_path, monkeypatch) -> None:
        _setup(tmp_path, monkeypatch)
        runner.invoke(app, ["add", "gs", "git", "status", "--group", "git"])
        runner.invoke(app, ["add", "ls", "ls", "-la", "--group", "system"])
        result = runner.invoke(app, ["search", "status", "--group", "git"])
        assert result.exit_code == 0
        assert "gs" in result.output
        assert "ls" not in result.output


class TestGroupInStore:
    def test_group_survives_roundtrip_via_store(self, tmp_path, monkeypatch) -> None:
        _setup(tmp_path, monkeypatch)
        runner.invoke(app, ["add", "gs", "git", "status", "-g", "work"])
        store = get_store()
        data = store.load()
        assert data.get("gs").group == "work"
        data.get("gs").description = "edited"
        store.save_with_backup(data)
        reloaded = store.load()
        assert reloaded.get("gs").group == "work"
        assert reloaded.get("gs").description == "edited"


class TestAliasStoreGroupField:
    def test_group_defaults_none(self) -> None:
        from qwik.core.models import Alias

        a = Alias(command="echo hi")
        assert a.group is None

    def test_group_strips_whitespace(self) -> None:
        from qwik.core.models import Alias

        a = Alias(command="echo hi", group="  git  ")
        assert a.group == "git"

    def test_group_empty_becomes_none(self) -> None:
        from qwik.core.models import Alias

        a = Alias(command="echo hi", group="   ")
        assert a.group is None

    def test_group_invalid_name_rejected(self) -> None:
        import pytest
        from qwik.core.models import Alias

        with pytest.raises(ValueError):
            Alias(command="echo hi", group="1bad")

    def test_group_valid_name(self) -> None:
        from qwik.core.models import Alias

        a = Alias(command="echo hi", group="git_ops")
        assert a.group == "git_ops"
