"""Tests for the schema migration framework."""

from __future__ import annotations

from pathlib import Path

import pytest

from qwik.config import Config
from qwik.core import migrations
from qwik.core.store import Store


@pytest.fixture
def temp_store(tmp_path: Path) -> Store:
    config = Config(override_config_dir=tmp_path)
    return Store(config)


def _write_raw(store: Store, text: str) -> None:
    store.path.parent.mkdir(parents=True, exist_ok=True)
    store.path.write_text(text, encoding="utf-8")


_GS_ALIAS_TOML = (
    '[aliases.gs]\ncommand = "git status"\n'
    'created_at = "2026-05-10T10:00:00Z"\nupdated_at = "2026-05-10T10:00:00Z"\n'
)


class TestMigrations:
    def test_migrates_v0_to_v1(self, temp_store: Store) -> None:
        _write_raw(temp_store, _GS_ALIAS_TOML)
        loaded = temp_store.load()
        assert loaded.version == 1
        assert loaded.get("gs").command == "git status"
        on_disk = temp_store.path.read_text(encoding="utf-8")
        assert "version = 1" in on_disk

    def test_migrates_creates_backup(self, temp_store: Store) -> None:
        _write_raw(temp_store, _GS_ALIAS_TOML)
        temp_store.load()
        backups = list(temp_store._backup_dir.glob("aliases-*.toml"))
        assert len(backups) == 1

    def test_newer_version_raises(self, temp_store: Store) -> None:
        _write_raw(temp_store, "version = 99\n")
        with pytest.raises(RuntimeError) as exc_info:
            temp_store.load()
        msg = str(exc_info.value)
        assert "99" in msg
        assert "doctor" in msg.lower()

    def test_identity_when_already_latest(self, temp_store: Store) -> None:
        _write_raw(temp_store, "version = 1\n\n" + _GS_ALIAS_TOML)
        loaded = temp_store.load()
        assert loaded.version == 1
        backups = list(temp_store._backup_dir.glob("aliases-*.toml"))
        assert len(backups) == 0

    def test_migrator_chain(self, temp_store: Store, monkeypatch: pytest.MonkeyPatch) -> None:
        @migrations.migrator(1)
        def _v1_to_v2(data: dict[str, object]) -> dict[str, object]:
            data["version"] = 2
            data["aliases"]["gs"]["description"] = "migrated"
            return data

        monkeypatch.setattr(migrations, "LATEST_VERSION", 2)
        try:
            _write_raw(temp_store, "version = 1\n\n" + _GS_ALIAS_TOML)
            loaded = temp_store.load()
            assert loaded.version == 2
            assert loaded.get("gs").description == "migrated"
            on_disk = temp_store.path.read_text(encoding="utf-8")
            assert "version = 2" in on_disk
        finally:
            migrations._MIGRATORS.pop(1, None)
