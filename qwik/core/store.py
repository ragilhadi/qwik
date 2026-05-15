"""Atomic TOML read/write and backup management."""

from __future__ import annotations

import shutil
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import tomlkit
from tomlkit import TOMLDocument

from qwik.config import Config, get_config
from qwik.core.models import AliasStore

__all__ = [
    "Store",
    "get_store",
]

# Maximum number of backup files to retain.
_MAX_BACKUPS: int = 20


def _now_stamp() -> str:
    """Return an ISO-like timestamp suitable for filenames.

    Returns:
        A string in the form ``YYYYMMDD-HHMMSS``.
    """
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


class Store:
    """Manages the on-disk alias database.

    All write operations are atomic (write to a temporary file then
    rename) and automatically create a dated backup copy in the backup
    directory before mutating the store.
    """

    def __init__(self, config: Config | None = None) -> None:
        """Initialise the store.

        Args:
            config: A :class:`~qwik.config.Config` instance.  If ``None``,
                the global default is used.
        """
        self._config = config or get_config()
        self._path = self._config.aliases_file
        self._backup_dir = self._config.backup_dir

    @property
    def path(self) -> Path:
        """Return the canonical path to ``aliases.toml``.

        Returns:
            A :class:`~pathlib.Path`.
        """
        return self._path

    def load(self) -> AliasStore:
        """Read the alias database from disk.

        Returns:
            An :class:`~qwik.core.models.AliasStore` populated from the TOML
            file.  If the file does not exist, an empty store is returned.
        """
        if not self._path.exists():
            return AliasStore()
        raw = self._path.read_text(encoding="utf-8")
        doc = tomlkit.parse(raw)
        data: dict[str, Any] = doc.unwrap()
        return AliasStore.model_validate(data)

    def save(self, store: AliasStore) -> None:
        """Persist *store* atomically to disk.

        Args:
            store: The in-memory alias database to write.
        """
        self._config.ensure_dirs()
        doc = self._store_to_document(store)
        temp = self._path.with_suffix(f".tmp-{os.getpid()}")
        temp.write_text(tomlkit.dumps(doc), encoding="utf-8")
        temp.replace(self._path)

    def save_with_backup(self, store: AliasStore) -> None:
        """Persist *store* after creating a backup of the existing file.

        Args:
            store: The in-memory alias database to write.
        """
        self._config.ensure_dirs()
        if self._path.exists():
            self._rotate_backups()
            backup_name = f"aliases-{_now_stamp()}.toml"
            shutil.copy2(self._path, self._backup_dir / backup_name)
        self.save(store)

    def _rotate_backups(self) -> None:
        """Prune old backups so that at most :data:`_MAX_BACKUPS` remain."""
        if not self._backup_dir.exists():
            return
        backups = sorted(self._backup_dir.glob("aliases-*.toml"))
        if len(backups) > _MAX_BACKUPS:
            for old in backups[: len(backups) - _MAX_BACKUPS]:
                old.unlink()

    @staticmethod
    def _store_to_document(store: AliasStore) -> TOMLDocument:
        """Convert an :class:`AliasStore` into a :class:`tomlkit.TOMLDocument`.

        Args:
            store: The alias database.

        Returns:
            A TOML document with a top-level ``version`` field and an
            ``aliases`` table containing each alias.
        """
        doc = tomlkit.document()
        doc.add("version", store.version)

        aliases_table = tomlkit.table()
        for name in sorted(store.aliases):
            alias = store.aliases[name]
            alias_table = tomlkit.table()
            alias_table.add("command", alias.command)
            if alias.tag:
                alias_table.add("tag", alias.tag)
            if alias.description:
                alias_table.add("description", alias.description)
            if not alias.enabled:
                alias_table.add("enabled", alias.enabled)
            alias_table.add("created_at", alias.created_at.isoformat())
            alias_table.add("updated_at", alias.updated_at.isoformat())
            if alias.last_used is not None:
                alias_table.add("last_used", alias.last_used.isoformat())
            if alias.run_count:
                alias_table.add("run_count", alias.run_count)
            aliases_table.add(name, alias_table)

        doc.add("aliases", aliases_table)
        return doc


def get_store() -> Store:
    """Return the global default :class:`Store` instance.

    Returns:
        A :class:`Store` backed by the default configuration.
    """
    return Store()
