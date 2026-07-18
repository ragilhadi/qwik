"""Unit tests for alias store persistence."""

import shutil
from pathlib import Path

import pytest

from qwik.config import Config
from qwik.core.models import Alias, AliasStore
from qwik.core.store import Store


@pytest.fixture
def temp_store(tmp_path: Path) -> Store:
    config = Config(override_config_dir=tmp_path)
    return Store(config)


class TestStore:
    def test_load_empty(self, temp_store: Store) -> None:
        data = temp_store.load()
        assert data.aliases == {}

    def test_roundtrip(self, temp_store: Store) -> None:
        data = AliasStore()
        data.add("gs", Alias(command="git status"))
        temp_store.save(data)
        loaded = temp_store.load()
        assert loaded.get("gs").command == "git status"

    def test_backup_created(self, temp_store: Store) -> None:
        data = AliasStore()
        data.add("gs", Alias(command="git status"))
        temp_store.save_with_backup(data)
        backups = list(temp_store._backup_dir.glob("aliases-*.toml"))
        assert len(backups) == 0  # first write, no prior file → no backup

        data.add("gco", Alias(command="git checkout {1}"), force=True)
        temp_store.save_with_backup(data)
        backups = list(temp_store._backup_dir.glob("aliases-*.toml"))
        assert len(backups) == 1

    def test_atomic_write(self, temp_store: Store) -> None:
        data = AliasStore()
        data.add("gs", Alias(command="git status"))
        temp_store.save(data)
        assert temp_store.path.exists()
        assert not (temp_store.path.parent / "aliases.tmp").exists()

    def test_backup_rotation_caps_at_20(self, temp_store: Store) -> None:
        """Backups should never exceed 20 (PRD §6.6)."""
        data = AliasStore()
        data.add("gs", Alias(command="git status"))

        # Prime the store with an initial file
        temp_store.save_with_backup(data)

        # Generate 25 backups
        for i in range(25):
            loaded = temp_store.load()
            loaded.add(f"a{i}", Alias(command=f"echo {i}"), force=True)
            temp_store.save_with_backup(loaded)

        backups = sorted(temp_store._backup_dir.glob("aliases-*.toml"))
        assert len(backups) <= 20


class TestLoadCorruption:
    def test_load_corrupt_toml_raises_actionable_error(self, temp_store):
        temp_store.path.parent.mkdir(parents=True, exist_ok=True)
        temp_store.path.write_text("not = valid = toml", encoding="utf-8")
        with pytest.raises(Exception) as exc_info:
            temp_store.load()
        assert "aliases.toml" in str(exc_info.value) or "doctor" in str(exc_info.value).lower()

    def test_load_invalid_schema_raises_actionable_error(self, temp_store):
        temp_store.path.parent.mkdir(parents=True, exist_ok=True)
        temp_store.path.write_text('version = "not-an-int"', encoding="utf-8")
        with pytest.raises(Exception):
            temp_store.load()


class TestSubsecondBackups:
    def test_rapid_writes_do_not_collide(self, temp_store):
        data = AliasStore()
        data.add("gs", Alias(command="git status"))
        temp_store.save_with_backup(data)
        for _ in range(5):
            loaded = temp_store.load()
            loaded.add("gs", Alias(command="git log"), force=True)
            temp_store.save_with_backup(loaded)
        backups = list(temp_store._backup_dir.glob("aliases-*.toml"))
        assert len(backups) == 5  # prime write has no prior file → no backup; 5 loop writes all unique


class TestBackupRecovery:
    def test_restore_from_latest_backup(self, temp_store):
        data = AliasStore()
        data.add("gs", Alias(command="git status"))
        temp_store.save_with_backup(data)
        data.add("gco", Alias(command="git checkout {1}"))
        temp_store.save_with_backup(data)
        # Corrupt the live store
        temp_store.path.write_text("garbage", encoding="utf-8")
        with pytest.raises(RuntimeError):
            temp_store.load()
        backups = sorted(temp_store._backup_dir.glob("aliases-*.toml"))
        assert backups, "expected at least one backup"
        # save_with_backup backs up the PREVIOUS state before writing the
        # new one, so the latest backup contains the state from before the
        # most recent write (here: the {gs} state). Restoring it yields a
        # usable store, even if not the very latest.
        latest = backups[-1]
        shutil.copy2(latest, temp_store.path)
        recovered = temp_store.load()
        assert "gs" in recovered.aliases

    def test_rm_creates_backup(self, temp_store):
        data = AliasStore()
        data.add("gs", Alias(command="git status"))
        temp_store.save_with_backup(data)
        # Simulate the rm flow: load, remove, save_with_backup
        loaded = temp_store.load()
        loaded.remove("gs")
        temp_store.save_with_backup(loaded)
        assert any(temp_store._backup_dir.glob("aliases-*.toml"))
