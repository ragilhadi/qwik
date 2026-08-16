"""Atomic TOML read/write and backup management."""

from __future__ import annotations

import itertools
import os
import shutil
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import tomlkit
from tomlkit import TOMLDocument
from tomlkit.exceptions import ParseError as TOMLDecodeError

from qwik.config import Config, get_config
from qwik.core.models import AliasStore

__all__ = [
    "Store",
    "get_store",
]

# Maximum number of backup files to retain.
_MAX_BACKUPS: int = 20


# Monotonic counter appended to backup timestamps to guarantee filename
# uniqueness even when ``datetime.now()`` returns the same value twice in
# a tight loop (Windows clock resolution is ~15 ms, so microsecond stamps
# can still collide).
_backup_counter: itertools.count[int] = itertools.count()


def _now_stamp() -> str:
    """Return an ISO-like timestamp with microseconds and a per-process counter.

    The counter suffix guarantees filename uniqueness across rapid writes
    on platforms where ``datetime.now()`` resolution is coarser than the
    call interval.
    """
    return f"{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S-%f')}-{next(_backup_counter):04d}"


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

    def load(self, include_overlay: bool = True) -> AliasStore:
        """Read the alias database from disk.

        Args:
            include_overlay: If ``True`` and an overlay config exists, merge
                overlay aliases into ``store.overlay_aliases`` (read-only).

        Returns:
            An :class:`~qwik.core.models.AliasStore` populated from the TOML
            file.  If the file does not exist, an empty store is returned.
        """
        if not self._path.exists():
            store = AliasStore()
        else:
            try:
                raw = self._path.read_text(encoding="utf-8")
                doc = tomlkit.parse(raw)
                data: dict[str, Any] = doc.unwrap()
                from qwik.core.migrations import migrate

                pre_version = data.get("version")
                data = migrate(data)
                migrated = data.get("version") != pre_version
                store = AliasStore.model_validate(data)
                if migrated:
                    self.save_with_backup(store)
            except (TOMLDecodeError, ValueError) as exc:
                raise RuntimeError(
                    f"Could not read alias store at {self._path}: {exc}. "
                    f"Run `qwik doctor` to diagnose or restore from "
                    f"{self._backup_dir}."
                ) from exc

        if include_overlay:
            self._merge_overlay(store)
        return store

    def _merge_overlay(self, store: AliasStore) -> None:
        """Merge overlay aliases into ``store.overlay_aliases`` (non-fatal)."""
        config_file = self._config.overlay_config_file
        if not config_file.exists():
            return
        overlay_file = self._config.overlay_aliases_file
        if not overlay_file.exists():
            return
        try:
            from qwik.core.migrations import migrate as do_migrate

            raw = overlay_file.read_text(encoding="utf-8")
            data: dict[str, Any] = dict(tomlkit.parse(raw).unwrap())
            data = do_migrate(data)
            overlay_store = AliasStore.model_validate(data)
            for name, alias in overlay_store.aliases.items():
                if name not in store.aliases:
                    store.overlay_aliases[name] = alias
        except Exception:
            pass

    def save(self, store: AliasStore) -> None:
        """Persist *store* atomically to disk.

        Args:
            store: The in-memory alias database to write.
        """
        self._config.ensure_dirs()
        doc = self._store_to_document(store)
        # A PID-suffixed name is not unique enough: PIDs are recycled and
        # are not unique across containers or network-mounted config dirs.
        # mkstemp in the destination directory guarantees a unique name and
        # keeps the final os.replace() on the same filesystem (atomic).
        fd, temp_name = tempfile.mkstemp(
            prefix=f"{self._path.name}.tmp-", dir=self._path.parent
        )
        temp = Path(temp_name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(tomlkit.dumps(doc))
            temp.replace(self._path)
        except BaseException:
            temp.unlink(missing_ok=True)
            raise

    def bump_usage(self, name: str) -> None:
        """Increment ``run_count`` / update ``last_used`` for *name* only.

        Performs a read-modify-write under :class:`FileLock`. Does NOT
        create a backup (reserves backups for mutating operations).
        """
        from qwik.core.locking import FileLock

        lock = FileLock(self._path.with_suffix(".toml.lock"))
        with lock:
            data = self.load()
            alias = data.get(name)
            if alias is None:
                return
            alias.bump_usage()
            self.save(data)

    @contextmanager
    def mutate(self, *, include_overlay: bool = True) -> Iterator[AliasStore]:
        """Load the freshest on-disk state under the store lock, mutate, save.

        Acquires the store's file lock, (re)loads the current on-disk
        state, and yields it for in-place mutation. If the ``with`` block
        exits normally, the store is saved (with backup) before the lock
        is released — but only if the yielded store actually changed, so
        a no-op mutation does not create a needless backup. If the block
        raises (including ``typer.Exit``), nothing is saved.

        This exists so that no command can perform an unlocked
        read-modify-write: two concurrent commands that both read the
        store before either writes back would otherwise silently lose
        whichever write lost the race.

        Any interactive prompt (confirmation, ``$EDITOR``, ...) must
        happen *before* entering this context manager — holding the lock
        across a blocking prompt would stall every other qwik process for
        the lock's timeout. Re-validate against the freshly loaded store
        yielded here rather than trusting an earlier unlocked read, since
        another process may have mutated the store in the meantime.

        Args:
            include_overlay: Forwarded to :meth:`load`.

        Yields:
            The freshly loaded :class:`AliasStore`, safe to mutate in place.
        """
        from qwik.core.locking import FileLock

        lock = FileLock(self._path.with_suffix(".toml.lock"))
        with lock:
            data = self.load(include_overlay=include_overlay)
            before = data.model_dump(exclude={"overlay_aliases"})
            yield data
            after = data.model_dump(exclude={"overlay_aliases"})
            if after != before:
                self.save_with_backup(data)

    def save_with_backup(self, store: AliasStore) -> Path | None:
        """Persist *store* after creating a backup of the existing file.

        Args:
            store: The in-memory alias database to write.

        Returns:
            The path of the backup file created, or ``None`` if there was
            no existing store to back up.
        """
        self._config.ensure_dirs()
        backup_path: Path | None = None
        if self._path.exists():
            backup_name = f"aliases-{_now_stamp()}.toml"
            backup_path = self._backup_dir / backup_name
            shutil.copy2(self._path, backup_path)
            self._rotate_backups()
        self.save(store)
        return backup_path

    def _rotate_backups(self) -> None:
        """Prune old backups so that at most :data:`_MAX_BACKUPS` remain."""
        if not self._backup_dir.exists():
            return
        backups = sorted(self._backup_dir.glob("aliases-*.toml"))
        for old in backups[: len(backups) - _MAX_BACKUPS]:
            old.unlink(missing_ok=True)

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
            if alias.group:
                alias_table.add("group", alias.group)
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
