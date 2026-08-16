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


def test_list_shows_overlay_only_aliases(tmp_path, monkeypatch):
    # Regression: `list` gated on data.aliases (user-only) while init,
    # pick, and search all use all_aliases() (which includes the
    # overlay) — a user whose aliases all come from a team overlay was
    # told they had none, while their shell hook simultaneously
    # generated all of them.
    _setup_with_overlay(tmp_path, monkeypatch, {"team_alias": "echo hello"})
    result = runner.invoke(app, ["list"])
    assert result.exit_code == 0
    assert "team_alias" in result.output
    assert "No aliases yet" not in result.output


def test_list_marks_overlay_provenance(tmp_path, monkeypatch):
    _setup_with_overlay(tmp_path, monkeypatch, {"team_alias": "echo hello"})
    result = runner.invoke(app, ["list"])
    assert "(overlay)" in result.output


def test_search_shows_overlay_only_aliases(tmp_path, monkeypatch):
    _setup_with_overlay(tmp_path, monkeypatch, {"team_alias": "echo hello"})
    result = runner.invoke(app, ["search", "team"])
    assert result.exit_code == 0
    assert "team_alias" in result.output
    assert "No aliases yet" not in result.output


def test_list_overlay_only_store_no_user_aliases(tmp_path, monkeypatch):
    # An overlay-only store (no user aliases at all) is the primary use
    # case the bug broke: `data.aliases` is empty in exactly this case.
    from qwik.config import _reset_config

    monkeypatch.setenv("QWIK_CONFIG_DIR", str(tmp_path))
    _reset_config()

    config = tmp_path / "overlay.toml"
    import tomlkit

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
    t = tomlkit.table()
    t.add("command", "echo team")
    aliases_table.add("teamalias", t)
    doc.add("aliases", aliases_table)
    (overlay_repo / "aliases.toml").write_text(tomlkit.dumps(doc))

    result = runner.invoke(app, ["list"])
    assert result.exit_code == 0
    assert "teamalias" in result.output
    assert "No aliases yet" not in result.output


def test_list_mixed_store_shows_both(tmp_path, monkeypatch):
    _setup_with_overlay(tmp_path, monkeypatch, {"team_alias": "echo hello"})
    result = runner.invoke(app, ["list"])
    assert "gs" in result.output
    assert "team_alias" in result.output
    # Only the overlay-sourced row gets the marker.
    lines = result.output.splitlines()
    gs_line = next(line for line in lines if "gs" in line and "team_alias" not in line)
    assert "(overlay)" not in gs_line


def test_list_user_alias_shadows_overlay_alias(tmp_path, monkeypatch):
    _setup_with_overlay(tmp_path, monkeypatch, {"shared": "echo overlay-version"})
    runner.invoke(app, ["add", "shared", "echo", "user-version", "--force"])

    result = runner.invoke(app, ["list"])
    assert result.exit_code == 0
    # Shown once, as the user's own command, with no overlay marker.
    assert result.output.count("shared") == 1
    assert "user-version" in result.output
    assert "overlay-version" not in result.output
    assert "(overlay)" not in result.output


def test_list_tag_filter_applies_to_overlay_aliases(tmp_path, monkeypatch):
    from qwik.config import _reset_config

    monkeypatch.setenv("QWIK_CONFIG_DIR", str(tmp_path))
    _reset_config()

    config = tmp_path / "overlay.toml"
    import tomlkit

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
    t = tomlkit.table()
    t.add("command", "echo team")
    t.add("tag", ["work"])
    aliases_table.add("teamalias", t)
    doc.add("aliases", aliases_table)
    (overlay_repo / "aliases.toml").write_text(tomlkit.dumps(doc))

    result = runner.invoke(app, ["list", "--tag", "work"])
    assert "teamalias" in result.output
    result_no_match = runner.invoke(app, ["list", "--tag", "nonexistent"])
    assert "teamalias" not in result_no_match.output


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
