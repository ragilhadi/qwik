"""Tests for shell-history parsing (issue #36)."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

from qwik.core.history import (
    BashHistoryReader,
    FishHistoryReader,
    HistoryEntry,
    NuHistoryReader,
    PwshHistoryReader,
    ZshHistoryReader,
    available_history_shells,
    history_reader_for,
    read_history,
)

TS = 1750000000  # 2025-06-15-ish epoch


class TestBashParser:
    def test_basic_lines(self, tmp_path: Path) -> None:
        f = tmp_path / "bash_history"
        f.write_text("git status\nls -la\ngit push\n", encoding="utf-8")
        entries = BashHistoryReader().parse_file(f)
        assert [e.command for e in entries] == ["git status", "ls -la", "git push"]
        assert all(e.source == "bash" for e in entries)

    def test_timestamp_lines(self, tmp_path: Path) -> None:
        f = tmp_path / "bash_history"
        f.write_text("#1234567890\ngit status\n#1234567891\nls\n", encoding="utf-8")
        entries = BashHistoryReader().parse_file(f)
        assert entries[0].timestamp == datetime.fromtimestamp(1234567890, tz=UTC)
        assert entries[1].timestamp == datetime.fromtimestamp(1234567891, tz=UTC)

    def test_plain_comments_not_timestamps(self, tmp_path: Path) -> None:
        f = tmp_path / "bash_history"
        f.write_text("# this is a comment\necho hi\n", encoding="utf-8")
        entries = BashHistoryReader().parse_file(f)
        assert len(entries) == 1
        assert entries[0].command == "echo hi"
        assert entries[0].timestamp is None

    def test_missing_file_returns_empty(self, tmp_path: Path) -> None:
        assert BashHistoryReader().parse_file(tmp_path / "nope") == []

    def test_hISTFILE_override(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setenv("HISTFILE", str(tmp_path / "custom"))
        paths = BashHistoryReader().default_paths()
        assert paths == (tmp_path / "custom",)


class TestZshParser:
    def test_plain_format(self, tmp_path: Path) -> None:
        f = tmp_path / "zsh_history"
        f.write_text("git status\nls -la\n", encoding="utf-8")
        entries = ZshHistoryReader().parse_file(f)
        assert [e.command for e in entries] == ["git status", "ls -la"]

    def test_extended_format(self, tmp_path: Path) -> None:
        f = tmp_path / "zsh_history"
        f.write_text(f": {TS}:0;git status\n: {TS + 5}:2;ls -la\n", encoding="utf-8")
        entries = ZshHistoryReader().parse_file(f)
        assert entries[0].command == "git status"
        assert entries[0].timestamp == datetime.fromtimestamp(TS, tz=UTC)
        assert entries[1].command == "ls -la"
        assert entries[1].timestamp == datetime.fromtimestamp(TS + 5, tz=UTC)

    def test_multiline_continuation(self, tmp_path: Path) -> None:
        f = tmp_path / "zsh_history"
        # Real zsh writes the meta prefix once; continuation lines are
        # literal (the trailing backslash is kept by zsh itself).
        f.write_text(": 100:0;echo one \\\ntwo\n: 200:0;ls\n", encoding="utf-8")
        entries = ZshHistoryReader().parse_file(f)
        assert entries[0].command == "echo one two"
        assert entries[1].command == "ls"

    def test_meta_line_inside_continuation_is_literal(self, tmp_path: Path) -> None:
        f = tmp_path / "zsh_history"
        f.write_text(": 100:0;echo a \\\n: 100:0;weird:0;literal\n", encoding="utf-8")
        entries = ZshHistoryReader().parse_file(f)
        assert entries[0].command == "echo a : 100:0;weird:0;literal"

    def test_missing_file(self, tmp_path: Path) -> None:
        assert ZshHistoryReader().parse_file(tmp_path / "nope") == []


class TestFishParser:
    def test_yamlish_format(self, tmp_path: Path) -> None:
        f = tmp_path / "fish_history"
        f.write_text(
            f"- cmd: git status\n  when: {TS}\n- cmd: ls -la\n  when: {TS + 10}\n",
            encoding="utf-8",
        )
        entries = FishHistoryReader().parse_file(f)
        assert [e.command for e in entries] == ["git status", "ls -la"]
        assert entries[0].timestamp == datetime.fromtimestamp(TS, tz=UTC)

    def test_multiline_cmd_continuation(self, tmp_path: Path) -> None:
        f = tmp_path / "fish_history"
        f.write_text("- cmd: echo line1\n  line2\n  when: 1\n", encoding="utf-8")
        entries = FishHistoryReader().parse_file(f)
        assert entries[0].command == "echo line1\nline2"

    def test_missing_file(self, tmp_path: Path) -> None:
        assert FishHistoryReader().parse_file(tmp_path / "nope") == []

    def test_xdg_data_home(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
        paths = FishHistoryReader().default_paths()
        assert paths[0] == tmp_path / "fish" / "fish_history"


class TestPwshParser:
    def test_one_command_per_line(self, tmp_path: Path) -> None:
        f = tmp_path / "ConsoleHost_history.txt"
        f.write_text("git status\nGet-ChildItem\n", encoding="utf-8")
        entries = PwshHistoryReader().parse_file(f)
        assert [e.command for e in entries] == ["git status", "Get-ChildItem"]
        assert all(e.source == "pwsh" for e in entries)

    def test_default_path_layout(self) -> None:
        paths = PwshHistoryReader().default_paths()
        assert "PSReadLine" in str(paths[0])
        assert paths[0].name == "ConsoleHost_history.txt"

    def test_missing_file(self, tmp_path: Path) -> None:
        assert PwshHistoryReader().parse_file(tmp_path / "nope") == []


class TestNuParser:
    def test_sqlite_history(self, tmp_path: Path) -> None:
        f = tmp_path / "history.sqlite3"
        with sqlite3.connect(f) as conn:
            conn.execute("CREATE TABLE history (command TEXT, created_at INTEGER)")
            conn.execute("INSERT INTO history VALUES ('git status', ?)", (TS,))
            conn.execute("INSERT INTO history VALUES ('ls -la', ?)", (TS + 5,))
        entries = NuHistoryReader().parse_file(f)
        assert [e.command for e in entries] == ["git status", "ls -la"]
        assert entries[0].timestamp == datetime.fromtimestamp(TS, tz=UTC)

    def test_sqlite_text_created_at(self, tmp_path: Path) -> None:
        f = tmp_path / "history.sqlite3"
        with sqlite3.connect(f) as conn:
            conn.execute("CREATE TABLE history (command TEXT)")
            conn.execute("INSERT INTO history VALUES ('echo hi')")
        entries = NuHistoryReader().parse_file(f)
        assert [e.command for e in entries] == ["echo hi"]

    def test_sqlite_missing_table(self, tmp_path: Path) -> None:
        f = tmp_path / "history.sqlite3"
        with sqlite3.connect(f) as conn:
            conn.execute("CREATE TABLE other (x INTEGER)")
        entries = NuHistoryReader().parse_file(f)
        assert entries == []

    def test_sqlite_corrupt_degrades_to_empty(self, tmp_path: Path) -> None:
        f = tmp_path / "history.sqlite3"
        f.write_bytes(b"definitely not sqlite")
        assert NuHistoryReader().parse_file(f) == []

    def test_text_history_fallback(self, tmp_path: Path) -> None:
        f = tmp_path / "history.txt"
        f.write_text("git status\necho hi\n", encoding="utf-8")
        entries = NuHistoryReader().parse_file(f)
        assert [e.command for e in entries] == ["git status", "echo hi"]


class TestRegistry:
    def test_builtin_shells_registered(self) -> None:
        shells = available_history_shells()
        for s in ("bash", "zsh", "fish", "pwsh", "nu"):
            assert s in shells

    def test_reader_for_unknown_shell(self) -> None:
        assert history_reader_for("tcsh") is None

    def test_entry_point_registration_mirrors_renderer_pattern(self) -> None:
        # The pyproject entry points resolve through the same mechanism
        # qwik.shell_renderers uses.
        reader = history_reader_for("zsh")
        assert reader is not None
        assert reader.shell_name == "zsh"


class TestReadHistory:
    def test_missing_history_warns(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setenv("HISTFILE", str(tmp_path / "nope"))
        entries, warnings = read_history("bash", history_file=tmp_path / "nope")
        assert entries == []
        assert warnings
        assert "No bash history file" in warnings[0] or "could not be read" in warnings[0]

    def test_history_file_override(self, tmp_path: Path) -> None:
        f = tmp_path / "custom_history"
        f.write_text("git status\n", encoding="utf-8")
        entries, warnings = read_history("bash", history_file=f)
        assert warnings == []
        assert len(entries) == 1

    def test_since_filter(self, tmp_path: Path) -> None:
        f = tmp_path / "zsh_history"
        old_ts = TS - 100000
        f.write_text(f": {old_ts}:0;old cmd\n: {TS}:0;new cmd\n", encoding="utf-8")
        entries, _ = read_history(
            "zsh",
            since=timedelta(days=1),
            history_file=f,
            now=datetime.fromtimestamp(TS + 10, tz=UTC),
        )
        # old cmd is 100000s ≈ 27h old → filtered; entries without a valid
        # timestamp can't be windowed so they're kept.
        assert [e.command for e in entries] == ["new cmd"]

    def test_unknown_shell_warns(self) -> None:
        entries, warnings = read_history("tcsh")
        assert entries == []
        assert any("tcsh" in w for w in warnings)

    def test_no_network_import_guarantee(self) -> None:
        """The history module imports no networking machinery."""
        import qwik.core.history as h

        banned = ("socket", "urllib", "requests", "httpx", "http")
        loaded = set(h.sys.modules) if hasattr(h, "sys") else set()
        import sys

        loaded = set(sys.modules)
        assert not any(b in loaded for b in banned if b == "requests" or b == "httpx")

    def test_entries_default_source(self, tmp_path: Path) -> None:
        f = tmp_path / "h"
        f.write_text("echo hi\n", encoding="utf-8")
        entries = BashHistoryReader().parse_file(f)
        assert entries[0] == HistoryEntry(
            command="echo hi",
            timestamp=None,
            duration=None,
            source="bash",
        )
