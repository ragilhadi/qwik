"""Tests for ``qwik undo`` and the shared backup API (issue #32)."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from qwik.cli import app
from qwik.config import Config, _reset_config
from qwik.core.diff import diff_stores
from qwik.core.models import Alias, AliasStore
from qwik.core.store import Store

runner = CliRunner()


@pytest.fixture(autouse=True)
def clean_store(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("QWIK_CONFIG_DIR", str(tmp_path))
    _reset_config()


def _add(*args: str) -> None:
    result = runner.invoke(app, ["add", *args])
    assert result.exit_code == 0, result.output


def _parse_backup_file(path: Path) -> AliasStore:
    import tomlkit

    return AliasStore.model_validate(tomlkit.parse(path.read_text(encoding="utf-8")).unwrap())


def _seed_two_aliases(tmp_path: Path) -> Store:
    """Create a store with gs, then a second state with gco added."""
    _add("gs", "git", "status")
    store = Store(Config(override_config_dir=tmp_path))
    # Backups: one per save_with_backup. First save (from add) had no
    # prior file. Force a backup of the 1-alias state, then add gco.
    data = store.load()
    store.save_with_backup(data)  # backup of {gs}
    with store.mutate() as fresh:
        fresh.add("gco", Alias(command="git checkout {1}"))
    return store


class TestDiff:
    def test_added_removed_changed(self) -> None:
        a = AliasStore()
        a.add("gs", Alias(command="git status"))
        a.add("old", Alias(command="echo old"))
        a.add("mod", Alias(command="echo v1"))
        b = AliasStore()
        b.add("gs", Alias(command="git status"))
        b.add("mod", Alias(command="echo v2"))
        b.add("new", Alias(command="echo new"))
        diff = diff_stores(a, b)
        assert [e.name for e in diff.added] == ["new"]
        assert [e.name for e in diff.removed] == ["old"]
        assert [e.name for e in diff.changed] == ["mod"]
        assert not diff.empty

    def test_identical_stores_empty(self) -> None:
        a = AliasStore()
        a.add("gs", Alias(command="git status"))
        assert diff_stores(a, a.model_copy()).empty

    def test_entry_kinds(self) -> None:
        a = AliasStore()
        a.add("x", Alias(command="one"))
        b = AliasStore()
        b.add("y", Alias(command="two"))
        diff = diff_stores(a, b)
        assert diff.added[0].kind == "add"
        assert diff.removed[0].kind == "remove"


class TestStoreBackupAPI:
    def test_list_backups_newest_first(self, tmp_path: Path) -> None:
        store = Store(Config(override_config_dir=tmp_path))
        data = AliasStore()
        data.add("gs", Alias(command="git status"))
        store.save(data)  # prime: no backup on first write
        data.add("gco", Alias(command="git checkout {1}"))
        store.save_with_backup(data)  # backup of {gs}
        data.add("k", Alias(command="kubectl"))
        store.save_with_backup(data)  # backup of {gs, gco}
        infos = store.list_backups()
        assert len(infos) == 2
        # newest first
        assert infos[0].stamp >= infos[1].stamp
        assert infos[0].alias_count == 2
        assert infos[1].alias_count == 1
        assert infos[0].size > 0

    def test_list_backups_skips_corrupt(self, tmp_path: Path) -> None:
        store = Store(Config(override_config_dir=tmp_path))
        data = AliasStore()
        data.add("gs", Alias(command="git status"))
        store.save(data)
        store.save_with_backup(data)  # one backup of that state
        corrupt = store._backup_dir / "aliases-99990101-000000-000000-9999.toml"
        corrupt.write_text("not-valid", encoding="utf-8")
        infos = store.list_backups()
        assert len(infos) == 1
        assert infos[0].stamp != "99990101-000000-000000-9999"

    def test_list_backups_empty_dir(self, tmp_path: Path) -> None:
        store = Store(Config(override_config_dir=tmp_path))
        assert store.list_backups() == []

    def test_find_backup_partial_stamp(self, tmp_path: Path) -> None:
        store = Store(Config(override_config_dir=tmp_path))
        data = AliasStore()
        data.add("gs", Alias(command="git status"))
        store.save(data)
        store.save_with_backup(data)  # produce exactly one backup
        info = store.list_backups()[0]
        # full stamp
        assert store.find_backup(info.stamp) is not None
        # date-only prefix
        date_prefix = info.stamp[:8]
        found = store.find_backup(date_prefix)
        assert found is not None
        assert found.stamp == info.stamp or found.stamp.startswith(date_prefix)

    def test_find_backup_no_match(self, tmp_path: Path) -> None:
        store = Store(Config(override_config_dir=tmp_path))
        assert store.find_backup("19990101") is None

    def test_restore_roundtrip(self, tmp_path: Path) -> None:
        store = Store(Config(override_config_dir=tmp_path))
        data = AliasStore()
        data.add("gs", Alias(command="git status"))
        store.save(data)
        store.save_with_backup(data)  # backup of state 1
        backup_of_state_1 = store.list_backups()[0]
        data.add("gco", Alias(command="git checkout {1}"))
        store.save_with_backup(data)  # backup of state 1 again + write state 2
        restored = store.restore(backup_of_state_1.path)
        assert "gs" in restored.aliases
        assert "gco" not in restored.aliases
        loaded = store.load()
        assert "gco" not in loaded.aliases

    def test_restore_creates_backup_of_current(self, tmp_path: Path) -> None:
        store = Store(Config(override_config_dir=tmp_path))
        data = AliasStore()
        data.add("gs", Alias(command="git status"))
        store.save(data)
        store.save_with_backup(data)  # backup of state 1
        first = store.list_backups()[0]
        data.add("gco", Alias(command="git checkout {1}"))
        store.save_with_backup(data)  # write state 2 (2 aliases)
        store.restore(first.path)
        # undo is itself undoable: current (2-alias) state was backed up
        assert len(store.list_backups()) >= 3

    def test_restore_unreadable_backup_raises(self, tmp_path: Path) -> None:
        store = Store(Config(override_config_dir=tmp_path))
        bad = store._backup_dir / "aliases-20260815-141803-000000-0000.toml"
        bad.parent.mkdir(parents=True, exist_ok=True)
        bad.write_text("garbage!", encoding="utf-8")
        with pytest.raises(RuntimeError, match="Could not read backup"):
            store.restore(bad)

    def test_restore_rejects_future_version(self, tmp_path: Path) -> None:
        """A backup bricked by a future version is restoreable as bytes.

        restore() copies the file's *document* verbatim (it does not
        migrate), so this must NOT raise — that's exactly the doctor
        --fix recovery path for a future-version store.
        """
        store = Store(Config(override_config_dir=tmp_path))
        bad = store._backup_dir / "aliases-20260815-141803-000000-0000.toml"
        bad.parent.mkdir(parents=True, exist_ok=True)
        bad.write_text("version = 99\n", encoding="utf-8")
        store.restore(bad)
        assert (store.path).read_text(encoding="utf-8") == "version = 99\n"
        # And loading it hits the future-version gate, as expected.
        with pytest.raises(RuntimeError, match="newer than supported"):
            store.load()


class TestUndoCommand:
    def test_undo_list_shows_backups(self, tmp_path: Path) -> None:
        _seed_two_aliases(tmp_path)
        result = runner.invoke(app, ["undo", "--list"])
        assert result.exit_code == 0, result.output
        assert "Stamp" in result.output or "min ago" in result.output or "just now" in result.output

    def test_undo_list_empty(self, tmp_path: Path) -> None:
        result = runner.invoke(app, ["undo", "--list"])
        assert result.exit_code == 0
        assert "No backups" in result.output

    def test_undo_requires_confirmation_and_restores(self, tmp_path: Path) -> None:
        store = _seed_two_aliases(tmp_path)
        before = store.load()
        assert "gco" in before.aliases
        # newest backup is the 1-alias state ({gs} only)
        result = runner.invoke(app, ["undo"], input="y\n")
        assert result.exit_code == 0, result.output
        after = store.load()
        assert "gco" not in after.aliases
        assert "gs" in after.aliases

    def test_undo_decline_changes_nothing(self, tmp_path: Path) -> None:
        store = _seed_two_aliases(tmp_path)
        result = runner.invoke(app, ["undo"], input="n\n")
        assert result.exit_code == 0, result.output
        assert "gco" in store.load().aliases

    def test_undo_twice_returns_to_start(self, tmp_path: Path) -> None:
        store = _seed_two_aliases(tmp_path)
        runner.invoke(app, ["undo"], input="y\n")
        assert "gco" not in store.load().aliases
        runner.invoke(app, ["undo"], input="y\n")
        assert "gco" in store.load().aliases

    def test_undo_yes_flag(self, tmp_path: Path) -> None:
        store = _seed_two_aliases(tmp_path)
        result = runner.invoke(app, ["undo", "--yes"])
        assert result.exit_code == 0, result.output
        assert "gco" not in store.load().aliases

    def test_undo_to_specific_stamp(self, tmp_path: Path) -> None:
        store = _seed_two_aliases(tmp_path)
        # oldest backup = the {gs}-only state
        oldest = store.list_backups()[-1].stamp
        result = runner.invoke(app, ["undo", "--to", oldest, "--yes"])
        assert result.exit_code == 0, result.output
        assert "gco" not in store.load().aliases

    def test_undo_to_partial_stamp(self, tmp_path: Path) -> None:
        store = _seed_two_aliases(tmp_path)
        oldest = store.list_backups()[-1].stamp
        result = runner.invoke(app, ["undo", "--to", oldest[:8], "--yes"])
        assert result.exit_code == 0, result.output

    def test_undo_to_unknown_stamp(self, tmp_path: Path) -> None:
        _seed_two_aliases(tmp_path)
        result = runner.invoke(app, ["undo", "--to", "19990101", "--yes"])
        assert result.exit_code == 1
        assert "No backup matching" in result.output

    def test_undo_no_backups(self, tmp_path: Path) -> None:
        result = runner.invoke(app, ["undo"])
        assert result.exit_code == 1
        assert "No valid backups" in result.output

    def test_undo_diff_flag(self, tmp_path: Path) -> None:
        store = _seed_two_aliases(tmp_path)
        data = store.load()
        data.add("k9s", Alias(command="k9s"))
        data.add("deploy", Alias(command="kubectl deploy"))
        store.save_with_backup(data)
        # The newest backup is the 2-alias state; live is 4 aliases, so
        # restoring would REMOVE k9s and deploy.
        result = runner.invoke(app, ["undo", "--diff"])
        assert result.exit_code == 0, result.output
        assert "- remove" in result.output

    def test_undo_diff_no_change(self, tmp_path: Path) -> None:
        store = _seed_two_aliases(tmp_path)
        # Write a backup whose content is identical to the live store, so
        # restoring it would change nothing.
        data = store.load()
        store.save_with_backup(data)
        newest = store.list_backups()[0]
        backup_store = _parse_backup_file(newest.path)
        live = store.load(include_overlay=False)
        from qwik.core.diff import diff_stores as ds

        assert ds(backup_store, live).empty

    def test_undo_shows_add_and_change_markers(self, tmp_path: Path) -> None:
        store = _seed_two_aliases(tmp_path)
        data = store.load()
        data.get("gs").command = "git status --short"
        store.save_with_backup(data)
        # Restore the OLDEST ({gs} 1-alias) backup: from live's
        # {gs(--short), gco} that means gco would be added and gs changed.
        oldest = store.list_backups()[-1]
        result = runner.invoke(app, ["undo", "--to", oldest.stamp, "--diff"])
        assert result.exit_code == 0, result.output
        assert "- remove" in result.output
        assert "~ change" in result.output or "change" in result.output

    def test_undo_empty_live_store_diffs_adds(self, tmp_path: Path) -> None:
        _add("gs", "git", "status")
        store = Store(Config(override_config_dir=tmp_path))
        data = store.load()
        store.save_with_backup(data)  # guarantee one backup exists
        # corrupt the live store so the snapshot degrades to empty:
        # restoring should then ADD the aliases back.
        store.path.write_text("garbage!!", encoding="utf-8")
        result = runner.invoke(app, ["undo", "--diff"])
        assert result.exit_code == 0, result.output
        assert "+ add" in result.output

    def test_undo_when_live_corrupt_still_restores(self, tmp_path: Path) -> None:
        _add("gs", "git", "status")
        store = Store(Config(override_config_dir=tmp_path))
        data = store.load()
        store.save_with_backup(data)  # guarantee one backup exists
        store.path.write_text("garbage!!", encoding="utf-8")
        result = runner.invoke(app, ["undo", "--yes"])
        assert result.exit_code == 0, result.output
        restored = store.load()
        assert "gs" in restored.aliases
