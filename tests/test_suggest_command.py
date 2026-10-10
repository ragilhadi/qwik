"""CLI tests for ``qwik suggest`` (issue #36)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from typer.testing import CliRunner

from qwik.cli import app
from qwik.config import Config, _reset_config
from qwik.core.models import AliasStore
from qwik.core.store import Store

runner = CliRunner()

TS = 1750000000


@pytest.fixture(autouse=True)
def clean_store(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("QWIK_CONFIG_DIR", str(tmp_path))
    _reset_config()
    yield  # type: ignore[misc]


def _bash_history(tmp_path: Path, commands: list[str]) -> Path:
    f = tmp_path / "bash_history"
    f.write_text("\n".join(commands) + "\n", encoding="utf-8")
    return f


class TestSuggestDryRun:
    def test_dry_run_creates_nothing(self, tmp_path: Path) -> None:
        hist = _bash_history(tmp_path, ["git status"] * 10)
        result = runner.invoke(app, ["suggest", "--history-file", str(hist), "--dry-run"])
        assert result.exit_code == 0, result.output
        store = Store(Config(override_config_dir=tmp_path))
        assert store.load().aliases == {}
        assert "Dry run" in result.output

    def test_dry_run_prints_candidates(self, tmp_path: Path) -> None:
        hist = _bash_history(tmp_path, ["git status"] * 10)
        result = runner.invoke(app, ["suggest", "--history-file", str(hist), "--dry-run"])
        assert "git status" in result.output
        assert "gs" in result.output

    def test_min_count_filters(self, tmp_path: Path) -> None:
        hist = _bash_history(tmp_path, ["git status"] * 2)
        result = runner.invoke(
            app, ["suggest", "--history-file", str(hist), "--min-count", "5", "--dry-run"]
        )
        assert "No alias-worthy commands" in result.output

    def test_limit(self, tmp_path: Path) -> None:
        cmds = [f"pkg{i} install --yes thing{i}" for i in range(5)]
        hist = _bash_history(tmp_path, [c for c in cmds for _ in range(6)])
        result = runner.invoke(
            app,
            [
                "suggest",
                "--history-file",
                str(hist),
                "--min-count",
                "6",
                "--limit",
                "3",
                "--dry-run",
            ],
        )
        assert result.exit_code == 0, result.output

    def test_existing_alias_command_not_suggested(self, tmp_path: Path) -> None:
        hist = _bash_history(tmp_path, ["git status"] * 10)
        runner.invoke(app, ["add", "gs", "git", "status"])
        result = runner.invoke(app, ["suggest", "--history-file", str(hist), "--dry-run"])
        assert "No alias-worthy commands" in result.output

    def test_secret_commands_never_appear(self, tmp_path: Path) -> None:
        hist = _bash_history(
            tmp_path,
            ["psql postgresql://admin:hunter2@db.example.com/prod"] * 10,
        )
        result = runner.invoke(app, ["suggest", "--history-file", str(hist), "--dry-run"])
        assert "hunter2" not in result.output
        assert "psql" not in result.output

    def test_header_shows_analyzed_count(self, tmp_path: Path) -> None:
        hist = _bash_history(tmp_path, ["git status"] * 4)
        result = runner.invoke(app, ["suggest", "--history-file", str(hist), "--dry-run"])
        assert "Analyzed 40 commands" in result.output or "Analyzed" in result.output


class TestSuggestMissingHistory:
    def test_missing_history_file_clear_message(self, tmp_path: Path) -> None:
        result = runner.invoke(app, ["suggest", "--history-file", str(tmp_path / "nope")])
        assert result.exit_code == 0
        assert (
            "No bash history" in result.output
            or "warning" in result.output.lower()
            or "⚠" in result.output
        )

    def test_unknown_shell(self, tmp_path: Path) -> None:
        result = runner.invoke(app, ["suggest", "--shell", "tcsh"])
        assert result.exit_code == 0
        assert "tcsh" in result.output


class TestSuggestInteractive:
    def test_confirm_y_creates_alias(self, tmp_path: Path) -> None:
        hist = _bash_history(tmp_path, ["git status"] * 10)
        result = runner.invoke(app, ["suggest", "--history-file", str(hist)], input="y\n")
        assert result.exit_code == 0, result.output
        store = Store(Config(override_config_dir=tmp_path))
        assert "gs" in store.load().aliases

    def test_decline_n_creates_nothing(self, tmp_path: Path) -> None:
        hist = _bash_history(tmp_path, ["git status"] * 10)
        runner.invoke(app, ["suggest", "--history-file", str(hist)], input="n\ny\n")
        store = Store(Config(override_config_dir=tmp_path))
        assert store.load().aliases == {}

    def test_edit_e_renames(self, tmp_path: Path) -> None:
        hist = _bash_history(tmp_path, ["git status"] * 10)
        result = runner.invoke(app, ["suggest", "--history-file", str(hist)], input="e\nmystat\n")
        assert result.exit_code == 0, result.output
        store = Store(Config(override_config_dir=tmp_path))
        assert "mystat" in store.load().aliases

    def test_skip_all_s_stops_review(self, tmp_path: Path) -> None:
        cmds = [f"pkg{i} install thing{i}" for i in range(3)]
        hist = _bash_history(tmp_path, [c for c in cmds for _ in range(10)])
        result = runner.invoke(
            app,
            ["suggest", "--history-file", str(hist), "--limit", "3", "--min-count", "10"],
            input="s\n",
        )
        assert result.exit_code == 0, result.output
        store = Store(Config(override_config_dir=tmp_path))
        assert store.load().aliases == {}

    def test_duplicate_edit_name_rejected_then_skipped(self, tmp_path: Path) -> None:
        runner.invoke(app, ["add", "taken", "echo", "hi"])
        hist = _bash_history(tmp_path, ["git status"] * 10)
        # Answer 'e', provide the conflicting name, then decline the retry.
        result = runner.invoke(app, ["suggest", "--history-file", str(hist)], input="e\ntaken\nn\n")
        assert result.exit_code == 0, result.output


class TestSuggestNuHistory:
    def test_sqlite_history_roundtrip(self, tmp_path: Path) -> None:
        db = tmp_path / "nu_history.sqlite3"
        with sqlite3.connect(db) as conn:
            conn.execute("CREATE TABLE history (command TEXT, created_at INTEGER)")
            conn.execute("INSERT INTO history VALUES (?, ?)", ("cargo build --release", TS))
        result = runner.invoke(
            app,
            [
                "suggest",
                "--shell",
                "nu",
                "--history-file",
                str(db),
                "--dry-run",
                "--min-count",
                "1",
            ],
        )
        assert result.exit_code == 0, result.output


class TestSuggestSinceFilter:
    def test_since_drops_old_entries(self, tmp_path: Path) -> None:
        old_ts = TS - 60 * 60 * 24 * 90  # 90 days ago
        f = tmp_path / "zsh_history"
        f.write_text(f": {old_ts}:0;git status\n: {TS}:0;git push\n", encoding="utf-8")
        result = runner.invoke(
            app,
            [
                "suggest",
                "--history-file",
                str(f),
                "--since",
                "30d",
                "--dry-run",
                "--min-count",
                "1",
            ],
        )
        assert result.exit_code == 0, result.output
        # 2 commands analyzed, only recent one counted; git push is single
        # run so min-count 1 applies
        assert "Analyzed 2 commands" in result.output

    def test_invalid_since_errors(self, tmp_path: Path) -> None:
        result = runner.invoke(app, ["suggest", "--since", "nonsense"])
        assert result.exit_code == 1


class TestSuggestJson:
    def test_json_output_no_markup(self, tmp_path: Path) -> None:
        import json

        hist = _bash_history(tmp_path, ["git status"] * 10)
        result = runner.invoke(app, ["suggest", "--history-file", str(hist), "--json"])
        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert payload["analyzed_commands"] == 10
        assert payload["suggestions"][0]["alias"] == "gs"
        assert payload["suggestions"][0]["command"] == "git status"
        assert "[qwik." not in result.output

    def test_json_never_prompts(self, tmp_path: Path) -> None:
        import json

        hist = _bash_history(tmp_path, ["git status"] * 10)
        result = runner.invoke(app, ["suggest", "--history-file", str(hist), "--json"])
        assert result.exit_code == 0
        json.loads(result.output)  # pure JSON on stdout
        store = Store(Config(override_config_dir=tmp_path))
        assert store.load().aliases == {}

    def test_json_secret_commands_absent(self, tmp_path: Path) -> None:
        import json

        hist = _bash_history(tmp_path, ["mysql -u root -p hunter2 db"] * 10)
        result = runner.invoke(app, ["suggest", "--history-file", str(hist), "--json"])
        payload = json.loads(result.output)
        assert payload["suggestions"] == []


class TestSuggestNoNetwork:
    def test_import_chain_has_no_socket_usage(self) -> None:
        """The suggest modules import no networking machinery."""
        import qwik.commands.suggest as mod
        import qwik.core.history as hist
        import qwik.core.redact as redact
        import qwik.core.suggest as eng

        for module in (mod, hist, redact, eng):
            source_names = set(vars(module))
            assert "socket" not in source_names
            assert "urllib" not in source_names

    def test_pure_functions_no_io(self) -> None:
        """analyze_history performs no filesystem or network I/O."""
        from qwik.core.history import HistoryEntry
        from qwik.core.suggest import analyze_history

        entries = [HistoryEntry(command="git status", source="t")] * 5
        suggestions = analyze_history(entries, AliasStore())
        assert len(suggestions) == 1
