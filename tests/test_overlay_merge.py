"""Tests for overlay merge at load time and overlay alias protection."""

from __future__ import annotations

import tomlkit
from typer.testing import CliRunner

from qwik.cli import app

runner = CliRunner()


def _setup_with_overlay(tmp_path, monkeypatch, overlay_aliases: dict[str, str]):
    from qwik.config import _reset_config

    monkeypatch.setenv("QWIK_CONFIG_DIR", str(tmp_path))
    _reset_config()
    runner.invoke(app, ["add", "gs", "git", "status"])

    config = tmp_path / "overlay.toml"
    config.write_text(
        tomlkit.dumps(
            {"url": "https://example.com", "branch": "main", "auto_update": False}
        )
    )

    overlay_repo = tmp_path / "overlay-repo"
    overlay_repo.mkdir(parents=True)
    doc = tomlkit.document()
    doc.add("version", 1)
    aliases_table = tomlkit.table()
    for name, cmd in overlay_aliases.items():
        t = tomlkit.table()
        t.add("command", cmd)
        aliases_table.add(name, t)
    doc.add("aliases", aliases_table)
    (overlay_repo / "aliases.toml").write_text(tomlkit.dumps(doc))


def test_load_merges_overlay(tmp_path, monkeypatch):
    _setup_with_overlay(tmp_path, monkeypatch, {"team_alias": "echo hello"})
    from qwik.core.store import get_store

    store = get_store()
    data = store.load()
    assert "gs" in data.aliases
    assert "team_alias" in data.overlay_aliases
    assert "team_alias" not in data.aliases


def test_all_aliases_merges_overlay(tmp_path, monkeypatch):
    _setup_with_overlay(tmp_path, monkeypatch, {"team_alias": "echo hello"})
    from qwik.core.store import get_store

    store = get_store()
    data = store.load()
    merged = data.all_aliases()
    assert "gs" in merged
    assert "team_alias" in merged


def test_load_without_overlay(tmp_path, monkeypatch):
    from qwik.config import _reset_config

    monkeypatch.setenv("QWIK_CONFIG_DIR", str(tmp_path))
    _reset_config()
    runner.invoke(app, ["add", "gs", "git", "status"])

    from qwik.core.store import get_store

    store = get_store()
    data = store.load()
    assert data.overlay_aliases == {}


def test_rm_overlay_alias_blocked(tmp_path, monkeypatch):
    _setup_with_overlay(tmp_path, monkeypatch, {"team_alias": "echo hello"})
    result = runner.invoke(app, ["rm", "team_alias", "--yes"])
    assert result.exit_code == 1
    assert "overlay" in result.output.lower()


def test_edit_overlay_alias_blocked(tmp_path, monkeypatch):
    _setup_with_overlay(tmp_path, monkeypatch, {"team_alias": "echo hello"})
    result = runner.invoke(app, ["edit", "team_alias"])
    assert result.exit_code == 1
    assert "overlay" in result.output.lower()


def test_rename_overlay_alias_blocked(tmp_path, monkeypatch):
    _setup_with_overlay(tmp_path, monkeypatch, {"team_alias": "echo hello"})
    result = runner.invoke(app, ["rename", "team_alias", "new_name", "--force"])
    assert result.exit_code == 1
    assert "overlay" in result.output.lower()


def test_copy_on_run(tmp_path, monkeypatch):
    _setup_with_overlay(tmp_path, monkeypatch, {"zz_echo": "echo hello"})
    from qwik.core.store import get_store

    store = get_store()
    data = store.load()
    assert "zz_echo" in data.overlay_aliases
    assert "zz_echo" not in data.aliases

    runner.invoke(app, ["run", "zz_echo"])

    data = store.load()
    assert "zz_echo" in data.aliases
