"""Tests for the backup table renderer and relative-time helpers."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from rich.console import Console

from qwik.core.store import BackupInfo
from qwik.ui.tables import render_backup_table


def _info(stamp: str, count: int = 5, size: int = 2048) -> BackupInfo:
    return BackupInfo(
        path=Path(f"/tmp/aliases-{stamp}.toml"), stamp=stamp, alias_count=count, size=size
    )


def _render(table) -> str:  # type: ignore[no-untyped-def]
    console = Console(width=120, force_terminal=False, record=True)
    with console.capture() as capture:
        console.print(table)
    return capture.get()


class TestRenderBackupTable:
    NOW = datetime(2026, 10, 9, 12, 0, 0, tzinfo=UTC)

    def test_columns_and_rows(self) -> None:
        infos = [
            _info("20261009-115800-000000-0001"),
            _info("20261008-090000-000000-0000", 42, 3175),
        ]
        table = render_backup_table(infos, now=self.NOW)
        rendered = _render(table)
        assert "When" in rendered
        assert "Aliases" in rendered
        assert "Size" in rendered
        assert "Stamp" in rendered
        assert "20261009-115800-000000-0001" in rendered
        assert "2 min ago" in rendered
        assert "3.1 KB" in rendered

    def test_relative_times(self) -> None:
        base = self.NOW
        cases = [
            ("20261009-115930-000000-0000", "just now"),
            ("20261009-113000-000000-0000", "30 min ago"),
            ("20261009-090000-000000-0000", "3 hours ago"),
            ("20261008-120000-000000-0000", "yesterday"),
            ("20261005-120000-000000-0000", "4 days ago"),
            ("20260910-120000-000000-0000", "4 weeks ago"),
        ]
        infos = [_info(stamp) for stamp, _ in cases]
        table = render_backup_table(infos, now=base)
        text = _render(table)
        for stamp, expected in cases:
            assert expected in text, f"{expected} missing for {stamp}"

    def test_unparseable_stamp_shows_raw(self) -> None:
        infos = [_info("not-a-stamp")]
        text = _render(render_backup_table(infos, now=self.NOW))
        assert "not-a-stamp"[:15] in text or "not-a-stamp" in text

    def test_empty_list_renders_headers(self) -> None:
        text = _render(render_backup_table([], now=self.NOW))
        assert "When" in text

    def test_size_formatting(self) -> None:
        infos = [
            _info("20261009-100000-000000-0000", size=512),
            _info("20261009-110000-000000-0000", size=3 * 1024 * 1024),
        ]
        text = _render(render_backup_table(infos, now=self.NOW))
        assert "512 B" in text
        assert "3.0 MB" in text


class TestRelativeTimeBounds:
    def test_future_timestamp_clamped(self) -> None:
        future = datetime(2026, 10, 9, 13, 0, 0, tzinfo=UTC)
        infos = [_info("20261009-130000-000000-0000")]
        text = _render(render_backup_table(infos, now=future - timedelta(hours=1)))
        assert "just now" in text

    def test_years(self) -> None:
        infos = [_info("20200101-000000-000000-0000")]
        text = _render(render_backup_table(infos, now=datetime(2026, 10, 9, tzinfo=UTC)))
        assert "year" in text
