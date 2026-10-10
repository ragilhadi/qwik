"""Tests for the suggest engine (issue #36)."""

from __future__ import annotations

from datetime import UTC, datetime

from qwik.core.history import HistoryEntry
from qwik.core.models import Alias, AliasStore
from qwik.core.suggest import (
    Suggestion,
    analyze_history,
    generate_name,
    is_aliasable,
    normalize_command,
)


def _entries(*commands: str, base_ts: int = 1750000000) -> list[HistoryEntry]:
    return [
        HistoryEntry(
            command=c, timestamp=datetime.fromtimestamp(base_ts + i, tz=UTC), source="test"
        )
        for i, c in enumerate(commands)
    ]


def _store_with(*names_commands: tuple[str, str]) -> AliasStore:
    store = AliasStore()
    for name, cmd in names_commands:
        store.add(name, Alias(command=cmd))
    return store


class TestNormalize:
    def test_keeps_flags_in_shape(self) -> None:
        assert normalize_command("git status --short") == "git status --short"

    def test_distinct_flag_values_stay_distinct(self) -> None:
        assert normalize_command("kubectl get pods -n prod") == "kubectl get pods -n prod"
        assert normalize_command("kubectl get pods -n staging") == "kubectl get pods -n staging"

    def test_strips_leading_env(self) -> None:
        assert normalize_command("FOO=bar git status") == "git status"

    def test_env_assignment_inside_command_kept(self) -> None:
        assert normalize_command("git -c FOO=bar status") == "git -c FOO=bar status"

    def test_empty(self) -> None:
        assert normalize_command("   ") == ""


class TestAliasable:
    def test_single_word_not_aliasable(self) -> None:
        assert not is_aliasable("ls")
        assert not is_aliasable("gs")

    def test_multiword_ok(self) -> None:
        assert is_aliasable("git status")

    def test_uuid_excluded(self) -> None:
        assert not is_aliasable("kubectl describe pod 550e8400-e29b-41d4-a716-446655440000")

    def test_long_path_excluded(self) -> None:
        assert not is_aliasable("cp /very/long/path/structure/file.txt /other/place/here.txt")

    def test_hash_excluded(self) -> None:
        assert not is_aliasable("git checkout a" + "b" * 39)

    def test_piped_command_excluded(self) -> None:
        assert not is_aliasable("docker logs app | grep error")

    def test_chained_command_excluded(self) -> None:
        assert not is_aliasable("cd /tmp && make all")

    def test_cd_never_suggested(self) -> None:
        assert not is_aliasable("cd somewhere")

    def test_qwik_subcommands_not_suggested(self) -> None:
        assert not is_aliasable("qwik add gs")


class TestGenerateName:
    def test_initials(self) -> None:
        assert generate_name("git status") == "gs"

    def test_multiword(self) -> None:
        assert generate_name("docker compose up") == "dcu"

    def test_flags_included(self) -> None:
        assert generate_name("kubectl get pods -n prod") == "kgp-p"

    def test_flag_only_command(self) -> None:
        assert generate_name("--help") == "-"  # degenerate; conflict gate rejects invalid syntax


class TestAnalyzeHistory:
    def test_ranks_by_time_saved(self) -> None:
        entries = _entries(
            *[  # git status x5 (short)
                "git status",
            ]
            * 5
            + [
                *[
                    "kubectl get pods -n production",
                ]
                * 4
            ]
        )
        store = AliasStore()
        suggestions = analyze_history(entries, store, min_count=2)
        assert suggestions, "expected suggestions"
        # kgp saves far more chars per run than gs — must rank first
        # despite fewer runs (ranking is by est. keystrokes saved).
        assert suggestions[0].command == "kubectl get pods -n production"

    def test_excludes_existing_alias_commands(self) -> None:
        entries = _entries(*["git status"] * 5)
        store = _store_with(("gs", "git status"))
        assert analyze_history(entries, store) == []

    def test_name_collision_extended(self) -> None:
        entries = _entries(*["git status"] * 5 + ["git switch main"] * 5)
        store = AliasStore()
        suggestions = analyze_history(entries, store)
        names = sorted(s.alias for s in suggestions)
        assert len(set(names)) == 2, f"collision not broken: {names}"
        assert all(len(n) >= 2 for n in names)

    def test_builtin_names_rejected(self) -> None:
        # `echo hello` would generate name "eh"—fine; but something like
        # `command X` whose initials form a builtin must be skipped.
        entries = _entries(*["cd path"] * 5)  # cd is single-word anyway
        store = AliasStore()
        assert analyze_history(entries, store) == []

    def test_min_count_filter(self) -> None:
        entries = _entries(*["git status"] * 2)
        assert analyze_history(entries, AliasStore(), min_count=3) == []
        assert len(analyze_history(entries, AliasStore(), min_count=2)) == 1

    def test_limit(self) -> None:
        cmds = [f"pkg{i} install thing{i}" for i in range(10)]
        entries = _entries(*[c for c in cmds for _ in range(4)])
        assert len(analyze_history(entries, AliasStore(), min_count=4)) <= 10
        assert len(analyze_history(entries, AliasStore(), min_count=4, limit=3)) == 3

    def test_secrets_excluded_entirely(self) -> None:
        entries = _entries(*["mysql -u root -p secret"] * 9)
        assert analyze_history(entries, AliasStore()) == []

    def test_conflict_checker_filters_builtin_names(self) -> None:
        # `cargo download` initials → "cd", a genuine bash builtin: the
        # suggestion must be dropped rather than proposed. (is_aliasable
        # requires 2+ words, which this satisfies.)
        entries = _entries(*["cargo download"] * 5)
        store = AliasStore()
        suggestions = analyze_history(entries, store, shell="bash")
        assert suggestions == []

    def test_collision_extension_avoids_builtin(self) -> None:
        # "cargo download file" → "cdf" (no builtin) — extension works.
        entries = _entries(*["cargo download file"] * 5)
        suggestions = analyze_history(entries, AliasStore(), shell="bash")
        assert suggestions and suggestions[0].alias == "cdf"

    def test_time_saved_display(self) -> None:
        entries = _entries(*["git status --short -b"] * 50)
        s = analyze_history(entries, AliasStore(), min_count=10)[0]
        assert s.time_saved_display.startswith("~")

    def test_overlay_aliases_count_as_taken(self) -> None:
        entries = _entries(*["git status"] * 5)
        store = AliasStore()
        store.overlay_aliases["gs"] = Alias(command="git status")
        assert analyze_history(entries, store) == []


class TestScoringConsistency:
    def test_score_is_count_times_saved(self) -> None:
        s = Suggestion(command="git push --force-with-lease", count=10, alias="gpf", saved_chars=20)
        assert s.score == 200
