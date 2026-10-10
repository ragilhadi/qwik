"""Shell-history readers for ``qwik suggest``.

Each supported shell gets a parser behind one
:meth:`HistoryReader.read` returning :class:`HistoryEntry` records.
Registration mirrors the shell-renderer plugin pattern (entry-point
group ``qwik.history_readers``), so new shells can be added without
touching core.

Privacy: this module reads local history files only. Nothing it does
touches the network. Unavailable or unparseable sources degrade to an
empty result with a warning message — never an exception.
"""

from __future__ import annotations

import functools
import importlib.metadata
import os
import re
import sqlite3
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

__all__ = [
    "BashHistoryReader",
    "FishHistoryReader",
    "HistoryEntry",
    "HistoryReader",
    "NuHistoryReader",
    "PwshHistoryReader",
    "ZshHistoryReader",
    "available_history_shells",
    "default_history_paths",
    "history_reader_for",
    "read_history",
]

_HISTORY_ENTRY_POINT_GROUP = "qwik.history_readers"


@dataclass(frozen=True)
class HistoryEntry:
    """One parsed history record.

    Attributes:
        command: The command line as typed.
        timestamp: When it was run (UTC); ``None`` when the source format
            doesn't record one.
        duration: Command runtime in seconds when recorded (fish), else
            ``None``.
    """

    command: str
    timestamp: datetime | None = None
    duration: float | None = None
    source: str = ""

    @property
    def words(self) -> list[str]:
        """Split the command into whitespace-separated words."""
        return self.command.split()


class HistoryReader(ABC):
    """Base class for per-shell history parsers."""

    shell_name: str

    @abstractmethod
    def default_paths(self) -> tuple[Path, ...]:
        """Return candidate history file locations, in priority order."""
        ...

    @abstractmethod
    def _parse(self, path: Path) -> list[HistoryEntry]:
        """Shell-specific parse of an existing file; may raise."""
        ...

    def parse_file(self, path: Path) -> list[HistoryEntry]:
        """Parse *path* into entries; return what could be read.

        Degrades: a missing or unparseable file returns ``[]`` rather
        than raising — the caller surfaces an empty result plus its own
        message, never a traceback.
        """
        try:
            if not path.is_file():
                return []
            return self._parse(path)
        except Exception:
            return []

    def read(self, path: Path | None = None) -> list[HistoryEntry]:
        """Read history from *path* or the first existing default path.

        Always returns a list — a missing or unreadable file degrades to
        ``[]`` rather than raising, so callers can warn and continue.
        An explicitly given *path* is used as-is (``--history-file``).
        """
        candidates = [path] if path is not None else list(self.default_paths())
        for candidate in candidates:
            if candidate is None:
                continue
            entries = self.parse_file(candidate)
            if entries:
                return entries
        return []


class BashHistoryReader(HistoryReader):
    """``~/.bash_history`` — one command per line, ``#`` comments are
    timestamp markers when ``HISTTIMEFORMAT`` is active."""

    shell_name = "bash"

    def default_paths(self) -> tuple[Path, ...]:
        override = os.environ.get("HISTFILE")
        if override:
            return (Path(override),)
        return (Path.home() / ".bash_history",)

    def _parse(self, path: Path) -> list[HistoryEntry]:
        raw = path.read_text(encoding="utf-8", errors="replace")
        entries: list[HistoryEntry] = []
        timestamp: datetime | None = None
        for line in raw.splitlines():
            if line.startswith("#") and len(line) > 1:
                body = line[1:].strip()
                if body.isdigit():
                    # HISTTIMEFORMAT marker: epoch of the NEXT command.
                    timestamp = datetime.fromtimestamp(int(body), tz=UTC)
                    continue
            command = line.strip()
            if not command or command.startswith("#"):
                continue
            entries.append(HistoryEntry(command=command, timestamp=timestamp, source="bash"))
        return entries


_ZSH_META_RE = re.compile(r"^: (\d+):\d+;(.*)$")


class ZshHistoryReader(HistoryReader):
    """``~/.zsh_history`` — both the plain and the extended
    ``: <ts>:<dur>;<cmd>`` formats (the latter when EXTENDED_HISTORY is
    set). Multi-line commands are joined with a space."""

    shell_name = "zsh"

    def default_paths(self) -> tuple[Path, ...]:
        override = os.environ.get("HISTFILE")
        if override:
            return (Path(override),)
        return (Path.home() / ".zsh_history",)

    def _parse(self, path: Path) -> list[HistoryEntry]:
        raw = path.read_text(encoding="utf-8", errors="replace")
        entries: list[HistoryEntry] = []
        pending: list[str] = []  # backslash-continuation accumulation
        pending_meta: tuple[datetime | None, float | None] = (None, None)

        def flush() -> None:
            if not pending:
                return
            command = " ".join(part.strip() for part in pending).strip()
            ts, dur = pending_meta
            if command:
                entries.append(
                    HistoryEntry(command=command, timestamp=ts, duration=dur, source="zsh")
                )
            pending.clear()

        for line in raw.splitlines():
            match = _ZSH_META_RE.match(line)
            if match and not pending:
                # A meta line starts a new entry only when nothing is
                # pending; inside a multi-line command a `: ts:dur;`
                # prefix is part of the literal command text.
                flush()
                epoch = int(match.group(1))
                pending_meta = (datetime.fromtimestamp(epoch, tz=UTC), None)
                rest = match.group(2)
            else:
                rest = line
            if rest.endswith("\\"):
                pending.append(rest[:-1])
                continue
            pending.append(rest)
            flush()
        flush()
        return entries


class FishHistoryReader(HistoryReader):
    """``~/.local/share/fish/fish_history`` — the YAML-ish
    ``- cmd: ...`` / ``when: ...`` format."""

    shell_name = "fish"

    def default_paths(self) -> tuple[Path, ...]:
        env_val = os.environ.get("__fish_user_data_dir") or os.environ.get("__fish_config_dir")
        if env_val:
            return (Path(env_val) / "fish_history",)
        xdg = os.environ.get("XDG_DATA_HOME")
        if xdg:
            return (Path(xdg) / "fish" / "fish_history",)
        return (Path.home() / ".local" / "share" / "fish" / "fish_history",)

    def _parse(self, path: Path) -> list[HistoryEntry]:
        raw = path.read_text(encoding="utf-8", errors="replace")
        entries: list[HistoryEntry] = []
        command: str | None = None
        timestamp: datetime | None = None

        def flush() -> None:
            nonlocal command, timestamp
            if command is not None:
                cmd = command.strip()
                if cmd:
                    entries.append(HistoryEntry(command=cmd, timestamp=timestamp, source="fish"))

        for line in raw.splitlines():
            stripped = line.strip()
            if stripped.startswith("- cmd:"):
                flush()
                command = stripped[len("- cmd:") :].strip()
                timestamp = None
            elif stripped.startswith("when:"):
                when = stripped[len("when:") :].strip()
                if when.isdigit():
                    timestamp = datetime.fromtimestamp(int(when), tz=UTC)
            elif command is not None:
                # Continuation of a multi-line fish command (“  <text>”).
                command += "\n" + stripped
        flush()
        return entries


class PwshHistoryReader(HistoryReader):
    """``(Get-PSReadLineOption).HistorySavePath`` — typically
    ``%APPDATA%\\Microsoft\\Windows\\PowerShell\\PSReadLine\\ConsoleHost_history.txt``;
    one command per line."""

    shell_name = "pwsh"

    def default_paths(self) -> tuple[Path, ...]:
        appdata = os.environ.get("APPDATA")
        if appdata:
            base = Path(appdata)
        elif sys_platform_windows():
            userprofile = os.environ.get("USERPROFILE")
            base = (Path(userprofile) / "AppData" / "Roaming") if userprofile else Path.home()
        else:
            # Non-Windows pwsh (rare) keeps the same relative layout.
            base = Path.home() / ".local" / "share"
        return (
            base
            / "Microsoft"
            / "Windows"
            / "PowerShell"
            / "PSReadLine"
            / "ConsoleHost_history.txt",
        )

    def _parse(self, path: Path) -> list[HistoryEntry]:
        raw = path.read_text(encoding="utf-8", errors="replace")
        return [
            HistoryEntry(command=line.strip(), source="pwsh")
            for line in raw.splitlines()
            if line.strip()
        ]


def sys_platform_windows() -> bool:
    import sys

    return sys.platform == "win32"


class NuHistoryReader(HistoryReader):
    """Nushell keeps commands in a SQLite db
    (``$nu-history-path``, typically ``~/.local/share/nushell/history.sqlite3``)."""

    shell_name = "nu"

    def default_paths(self) -> tuple[Path, ...]:
        env_val = os.environ.get("NU_CONFIG_DIR")
        if env_val:
            base = Path(env_val)
            candidates = [base / "history.sqlite3", base / "history.txt"]
        else:
            xdg = os.environ.get("XDG_DATA_HOME")
            base = Path(xdg) if xdg else Path.home() / ".local" / "share"
            candidates = [
                base / "nushell" / "history.sqlite3",
                Path.home() / ".config" / "nushell" / "history.txt",
            ]
        return tuple(candidates)

    def _parse(self, path: Path) -> list[HistoryEntry]:
        if path.suffix == ".sqlite3":
            return self._parse_sqlite(path)
        return self._parse_text(path)

    def _parse_sqlite(self, path: Path) -> list[HistoryEntry]:
        # Open read-only so a live nushell can't be disturbed, and copy
        # the -wal tail into memory implicitly by querying within one
        # snapshot; errors degrade to [] via HistoryReader.read.
        uri = f"file:{path}?mode=ro"
        entries: list[HistoryEntry] = []
        with sqlite3.connect(uri, uri=True) as conn:
            # Newer format: history(command, created_at);
            # older: history(id, command, created_at is TEXT).
            table_names = {
                row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
            }
            if "history" not in table_names:
                return []
            # Determine column shape once.
            columns = {row[1] for row in conn.execute("PRAGMA table_info(history)")}
            created_is_int = "created_at" in columns
            if created_is_int:
                rows = conn.execute("SELECT command, created_at FROM history ORDER BY created_at")
            else:
                rows = conn.execute("SELECT command FROM history ORDER BY rowid")
            for row in rows:
                command = str(row[0]).strip() if row[0] is not None else ""
                if not command:
                    continue
                ts = None
                if created_is_int and row[1] is not None:
                    try:
                        ts = datetime.fromtimestamp(int(row[1]), tz=UTC)
                    except (ValueError, OverflowError, OSError):
                        ts = None
                entries.append(HistoryEntry(command=command, timestamp=ts, source="nu"))
        return entries

    def _parse_text(self, path: Path) -> list[HistoryEntry]:
        raw = path.read_text(encoding="utf-8", errors="replace")
        return [
            HistoryEntry(command=line.strip(), source="nu")
            for line in raw.splitlines()
            if line.strip()
        ]


_READERS: dict[str, type[HistoryReader]] = {
    "bash": BashHistoryReader,
    "zsh": ZshHistoryReader,
    "fish": FishHistoryReader,
    "pwsh": PwshHistoryReader,
    "nu": NuHistoryReader,
}


@functools.cache
def _entry_point_readers() -> dict[str, type[HistoryReader]]:
    """Load plugin-registered readers from ``qwik.history_readers``."""
    try:
        eps = importlib.metadata.entry_points(group=_HISTORY_ENTRY_POINT_GROUP)
    except Exception:
        return {}
    loaded: dict[str, type[HistoryReader]] = {}
    for ep in eps:
        try:
            cls = ep.load()
        except Exception:
            continue
        loaded[ep.name] = cls
    return loaded


def history_reader_for(shell: str) -> HistoryReader | None:
    """Return the reader for *shell*, or ``None`` if unsupported.

    Plugin-registered entry points take precedence over built-ins so a
    plugin can override a core parser.

    Args:
        shell: Lowercase shell identifier (``bash``, ``zsh`` …).
    """
    shell = shell.lower().strip()
    plugin = _entry_point_readers().get(shell)
    if plugin is not None:
        return plugin()
    builtin = _READERS.get(shell)
    return builtin() if builtin is not None else None


def available_history_shells() -> tuple[str, ...]:
    """All shells with a history reader (built-in + plugins), sorted."""
    return tuple(sorted({*_READERS, *_entry_point_readers()}))


def default_history_paths(shell: str) -> tuple[Path, ...]:
    """Documented convenience: which files would be read for *shell*."""
    reader = history_reader_for(shell)
    return reader.default_paths() if reader else ()


def read_history(
    shell: str | None,
    *,
    since: timedelta | None = None,
    history_file: Path | None = None,
    now: datetime | None = None,
) -> tuple[list[HistoryEntry], list[str]]:
    """Read history for *shell*; return ``(entries, warnings)``.

    Args:
        shell: Shell identifier; ``None`` falls back to bash.
        since: If set, only entries running within the window are kept.
        history_file: Override the default history location.
        now: Override current time (tests).

    Returns:
        A tuple of the parsed entries and human-readable warnings for
        sources that could not be read (missing file, parse failure).
        A missing/unreadable history file is a warning, never an
        exception — callers print the warning and proceed.
    """
    warnings: list[str] = []
    effective_shell = shell or "bash"
    reader = history_reader_for(effective_shell)
    if reader is None:
        warnings.append(f"No history reader for shell '{effective_shell}'.")
        return [], warnings

    path = history_file
    if path is None:
        candidates = reader.default_paths()
        path = next((p for p in candidates if p.is_file()), None)
        if path is None:
            expected = ", ".join(str(p) for p in candidates)
            warnings.append(f"No {effective_shell} history file found (looked for: {expected}).")
            return [], warnings

    entries = reader.read(path)
    if not entries:
        warnings.append(f"{path} exists but could not be read as {effective_shell} history.")

    if since is not None:
        cutoff = (now or datetime.now(UTC)) - since
        entries = [e for e in entries if e.timestamp is None or e.timestamp >= cutoff]
    return entries, warnings
