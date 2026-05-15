"""Unit tests for alias store persistence."""

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
