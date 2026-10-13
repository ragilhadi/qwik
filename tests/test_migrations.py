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
    def test_migrates_v0_to_latest(self, temp_store: Store) -> None:
        _write_raw(temp_store, _GS_ALIAS_TOML)
        loaded = temp_store.load()
        assert loaded.version == 2
        assert loaded.get("gs").command == "git status"
        on_disk = temp_store.path.read_text(encoding="utf-8")
        assert "version = 2" in on_disk

    def test_migrates_creates_backup(self, temp_store: Store) -> None:
        _write_raw(temp_store, _GS_ALIAS_TOML)
        temp_store.load()
        backups = list(temp_store._backup_dir.glob("aliases-*.toml"))
        assert len(backups) == 1

    def test_migrates_v1_to_v2_identity(self, temp_store: Store) -> None:
        # v1 → v2 is the platform-variants bump: a pure version-key step
        # with no data transformation.
        _write_raw(temp_store, "version = 1\n\n" + _GS_ALIAS_TOML)
        loaded = temp_store.load()
        assert loaded.version == 2
        assert loaded.get("gs").command == "git status"
        assert loaded.get("gs").command_variants == {}
        on_disk = temp_store.path.read_text(encoding="utf-8")
        assert "version = 2" in on_disk
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
        _write_raw(temp_store, "version = 2\n\n" + _GS_ALIAS_TOML)
        loaded = temp_store.load()
        assert loaded.version == 2
        backups = list(temp_store._backup_dir.glob("aliases-*.toml"))
        assert len(backups) == 0

    def test_migrator_chain(self, temp_store: Store, monkeypatch: pytest.MonkeyPatch) -> None:
        # migrator(2) rather than migrator(1): the real _v1_to_v2 ships in
        # qwik.core.migrations now, and registering over it would clobber
        # (then pop) the production migrator for every test in this session.
        @migrations.migrator(2)
        def _v2_to_v3(data: dict[str, object]) -> dict[str, object]:
            data["version"] = 3
            data["aliases"]["gs"]["description"] = "migrated"
            return data

        monkeypatch.setattr(migrations, "LATEST_VERSION", 3)
        try:
            _write_raw(temp_store, "version = 2\n\n" + _GS_ALIAS_TOML)
            loaded = temp_store.load()
            assert loaded.version == 3
            assert loaded.get("gs").description == "migrated"
            on_disk = temp_store.path.read_text(encoding="utf-8")
            assert "version = 3" in on_disk
        finally:
            migrations._MIGRATORS.pop(2, None)
