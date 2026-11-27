"""Argument-aware completions (``--complete-with`` / ``--complete-from``).

Pinned here:

1. **Key resolution** — positional keys map to argument slots directly,
   named keys through the substitution engine's first-appearance map.
2. **Per-shell emission** — bash ``complete -F`` + ``compgen -W``,
   zsh ``compdef`` + ``_describe``, fish ``complete -c`` with
   ``commandline -opc`` position conditions, pwsh
   ``Register-ArgumentCompleter``; unsupporting shells (cmd, nu, xonsh)
   emit nothing.
3. **Store round-trip** — the ``complete`` mapping survives save/load,
   export/import, and the edit snippet.
4. **Real-shell integration** — the generated completion, sourced by a
   real bash and zsh, yields the completion command's candidates.
"""

from __future__ import annotations

import shutil
import subprocess
import sys

import pytest
from typer.testing import CliRunner

from qwik.cli import app
from qwik.core.models import Alias
from qwik.core.substitute import _named_placeholder_index_map
from qwik.shells.base import get_renderer
from qwik.shells.completions import (
    bash_completion,
    fish_completion,
    pwsh_completion,
    resolve_completion_positions,
    zsh_completion,
)

runner = CliRunner()


# ---------------------------------------------------------------------------
# Key resolution
# ---------------------------------------------------------------------------


def test_positional_and_named_keys_resolve() -> None:
    named = Alias(command="git checkout {branch}", complete={"branch": "git branch"})
    assert resolve_completion_positions(named) == [(1, "git branch")]
    positional = Alias(command="cp {1} {2}", complete={"1": "ls -1", "2": "find . -maxdepth 1"})
    assert resolve_completion_positions(positional) == [
        (1, "ls -1"),
        (2, "find . -maxdepth 1"),
    ]


def test_unknown_key_and_out_of_range_rejected() -> None:
    alias = Alias(command="echo {1}", complete={"2": "ls", "who": "ls"})
    assert resolve_completion_positions(alias) == []


def test_inherit_key_ignored_by_position_resolution() -> None:
    alias = Alias(command="kubectl", complete={"inherit": "kubectl"})
    assert resolve_completion_positions(alias) == []


def test_named_map_matches_substitution_engine() -> None:
    alias = Alias(command="deploy {env} {region}")
    assert _named_placeholder_index_map(alias.command) == {"env": 1, "region": 2}
    with_completions = Alias(
        command="deploy {env} {region}",
        complete={"env": "echo dev", "region": "echo eu"},
    )
    assert resolve_completion_positions(with_completions) == [
        (1, "echo dev"),
        (2, "echo eu"),
    ]


# ---------------------------------------------------------------------------
# Per-shell emission
# ---------------------------------------------------------------------------


_GCO = Alias(
    command="git checkout {branch}",
    complete={"branch": "git branch --format='%(refname:short)'"},
)


def test_bash_completion_structure() -> None:
    out = bash_completion("gco", _GCO)
    assert "_qwik_complete_gco() {" in out
    assert "candidates=$(git branch --format='%(refname:short)')" in out
    assert "if (( COMP_CWORD == 1 )); then" in out
    assert 'COMPREPLY=( $(compgen -W "$candidates" -- "$cur") )' in out
    assert out.endswith("complete -F _qwik_complete_gco -- gco")


def test_zsh_completion_structure() -> None:
    out = zsh_completion("gco", _GCO)
    assert "_qwik_complete_gco() {" in out
    assert "if (( CURRENT == 2 )); then" in out  # zsh words[1] is the command
    assert "_describe 'values' candidates" in out
    assert out.endswith("compdef _qwik_complete_gco gco")


def test_fish_completion_structure() -> None:
    out = fish_completion("gco", _GCO)
    assert out.startswith("complete -c gco -f")
    assert "(count (commandline -opc) == 2)" in out  # fish word 1 is the command
    assert "git branch" in out


def test_pwsh_completion_structure() -> None:
    out = pwsh_completion("gco", _GCO)
    assert "Register-ArgumentCompleter -CommandName 'gco'" in out
    assert "if ($args.Count -eq 0) {" in out
    assert "[System.Management.Automation.CompletionResult]::new($_)" in out


def test_unsupporting_shells_emit_nothing() -> None:
    for shell in ("cmd", "nu", "xonsh"):
        renderer = get_renderer(shell)
        assert not renderer.supports_completions
        assert renderer.render_completion_alias("gco", _GCO) == ""


def test_alias_without_complete_renders_nothing() -> None:
    assert bash_completion("gs", Alias(command="git status")) == ""
    assert zsh_completion("gs", Alias(command="git status")) == ""


def test_render_all_appends_completions_after_aliases() -> None:
    store = _store_with_completions()
    out = get_renderer("bash").render_all(store.aliases)
    alias_part, completion_part = out.split("complete -F", 1)
    assert "gco() {" in alias_part
    assert "gco() {" in alias_part.split("complete")[0]
    assert "_qwik_complete_gco" in "complete -F" + completion_part
    # Completions come after every alias definition.
    assert out.index("complete -F") > out.index("gco() {")


def _store_with_completions():
    from qwik.core.models import AliasStore

    store = AliasStore()
    store.add("gs", Alias(command="git status"))
    store.add("gco", _GCO)
    return store


# ---------------------------------------------------------------------------
# Store round-trip
# ---------------------------------------------------------------------------


def test_complete_survives_save_load(tmp_path, monkeypatch) -> None:
    from qwik.config import _reset_config

    monkeypatch.setenv("QWIK_CONFIG_DIR", str(tmp_path))
    _reset_config()
    runner.invoke(
        app, ["add", "gco", "git", "checkout", "{branch}", "--complete-with", "branch=git branch"]
    )
    from qwik.core.store import get_store

    loaded = get_store().load()
    alias = loaded.get("gco")
    assert alias is not None
    assert alias.complete == {"branch": "git branch"}


def test_complete_table_on_disk(tmp_path, monkeypatch) -> None:
    from qwik.config import _reset_config

    monkeypatch.setenv("QWIK_CONFIG_DIR", str(tmp_path))
    _reset_config()
    runner.invoke(
        app, ["add", "gco", "git", "checkout", "{branch}", "--complete-with", "branch=git branch"]
    )
    on_disk = (tmp_path / "aliases.toml").read_text(encoding="utf-8")
    assert "[aliases.gco.complete]" in on_disk
    assert 'branch = "git branch"' in on_disk
    assert "version = 3" in on_disk


def test_complete_survives_export_import(tmp_path, monkeypatch) -> None:
    from qwik.config import _reset_config

    monkeypatch.setenv("QWIK_CONFIG_DIR", str(tmp_path))
    _reset_config()
    runner.invoke(
        app, ["add", "gco", "git", "checkout", "{branch}", "--complete-with", "branch=git branch"]
    )
    export_path = tmp_path / "export.json"
    result = runner.invoke(app, ["export", str(export_path)])
    assert result.exit_code == 0, result.output

    import json

    payload = json.loads(export_path.read_text(encoding="utf-8"))
    assert payload["aliases"]["gco"]["complete"] == {"branch": "git branch"}

    # Import into a fresh store and confirm.
    fresh = tmp_path / "fresh"
    fresh.mkdir()
    import os

    os.environ["QWIK_CONFIG_DIR"] = str(fresh)
    _reset_config()
    result = runner.invoke(app, ["import", str(export_path), "-y"])
    assert result.exit_code == 0, result.output
    from qwik.core.store import get_store

    alias = get_store().load().get("gco")
    assert alias is not None
    assert alias.complete == {"branch": "git branch"}


def test_edit_snippet_round_trips_complete(tmp_path, monkeypatch) -> None:
    from qwik.config import _reset_config

    monkeypatch.setenv("QWIK_CONFIG_DIR", str(tmp_path))
    _reset_config()
    runner.invoke(
        app, ["add", "gco", "git", "checkout", "{branch}", "--complete-with", "branch=git branch"]
    )
    from qwik.commands.edit import edit_alias

    # Simulate $EDITOR rewriting the snippet: change one completion value.
    snippet_text: dict[str, str] = {}

    def fake_run(cmd, **kwargs):
        path = cmd[-1]
        snippet_text["original"] = open(path, encoding="utf-8").read()
        edited = snippet_text["original"].replace(
            'branch = "git branch"', 'branch = "git branch -a"'
        )
        open(path, "w", encoding="utf-8").write(edited)
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr("qwik.commands.edit.subprocess.run", fake_run)
    monkeypatch.setenv("EDITOR", "true")
    edit_alias("gco")

    from qwik.core.store import get_store

    alias = get_store().load().get("gco")
    assert alias is not None
    assert alias.complete == {"branch": "git branch -a"}


def test_edit_removes_complete_when_table_deleted(tmp_path, monkeypatch) -> None:
    from qwik.config import _reset_config

    monkeypatch.setenv("QWIK_CONFIG_DIR", str(tmp_path))
    _reset_config()
    runner.invoke(
        app, ["add", "gco", "git", "checkout", "{branch}", "--complete-with", "branch=git branch"]
    )

    from qwik.commands.edit import edit_alias

    def fake_run(cmd, **kwargs):
        path = cmd[-1]
        original = open(path, encoding="utf-8").read()
        # Drop the [complete] table entirely (comment header + table body).
        marker = "# Completions ([complete.KEY]"
        head, _, _ = original.partition(marker)
        open(path, "w", encoding="utf-8").write(head.rstrip() + "\n")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr("qwik.commands.edit.subprocess.run", fake_run)
    monkeypatch.setenv("EDITOR", "true")
    edit_alias("gco")

    from qwik.core.store import get_store

    alias = get_store().load().get("gco")
    assert alias is not None
    assert alias.complete == {}


# ---------------------------------------------------------------------------
# add command option validation
# ---------------------------------------------------------------------------


def test_add_rejects_complete_with_for_unknown_key(tmp_path, monkeypatch) -> None:
    from qwik.config import _reset_config

    monkeypatch.setenv("QWIK_CONFIG_DIR", str(tmp_path))
    _reset_config()
    result = runner.invoke(
        app, ["add", "gco", "git", "checkout", "{branch}", "--complete-with", "nope=git branch"]
    )
    assert result.exit_code == 1
    assert "not a placeholder" in result.output


def test_add_rejects_complete_with_malformed_entry(tmp_path, monkeypatch) -> None:
    from qwik.config import _reset_config

    monkeypatch.setenv("QWIK_CONFIG_DIR", str(tmp_path))
    _reset_config()
    result = runner.invoke(
        app, ["add", "gco", "git", "checkout", "{1}", "--complete-with", "1git branch"]
    )
    assert result.exit_code == 1


def test_add_rejects_out_of_range_position(tmp_path, monkeypatch) -> None:
    from qwik.config import _reset_config

    monkeypatch.setenv("QWIK_CONFIG_DIR", str(tmp_path))
    _reset_config()
    result = runner.invoke(app, ["add", "cp2", "cp", "{1}", "{2}", "--complete-with", "3=ls"])
    assert result.exit_code == 1


def test_add_complete_with_positional(tmp_path, monkeypatch) -> None:
    from qwik.config import _reset_config

    monkeypatch.setenv("QWIK_CONFIG_DIR", str(tmp_path))
    _reset_config()
    result = runner.invoke(
        app,
        [
            "add",
            "cp2",
            "cp",
            "{1}",
            "{2}",
            "--complete-with",
            "1=ls -1",
            "--complete-with",
            "2=find . -maxdepth 1",
        ],
    )
    assert result.exit_code == 0, result.output
    from qwik.core.store import get_store

    alias = get_store().load().get("cp2")
    assert alias is not None
    assert alias.complete == {"1": "ls -1", "2": "find . -maxdepth 1"}


def test_add_complete_from_stores_inherit(tmp_path, monkeypatch) -> None:
    from qwik.config import _reset_config

    monkeypatch.setenv("QWIK_CONFIG_DIR", str(tmp_path))
    _reset_config()
    result = runner.invoke(app, ["add", "k", "kubectl", "--complete-from", "kubectl"])
    assert result.exit_code == 0, result.output
    from qwik.core.store import get_store

    alias = get_store().load().get("k")
    assert alias is not None
    assert alias.complete == {"inherit": "kubectl"}


def test_add_complete_from_conflicts_with_complete_with(tmp_path, monkeypatch) -> None:
    from qwik.config import _reset_config

    monkeypatch.setenv("QWIK_CONFIG_DIR", str(tmp_path))
    _reset_config()
    result = runner.invoke(
        app,
        [
            "add",
            "gco",
            "git",
            "checkout",
            "{branch}",
            "--complete-with",
            "inherit=git branch",
            "--complete-from",
            "git",
        ],
    )
    # "inherit" isn't a placeholder of the command, so the name check fires
    # before the reserved-key conflict can.
    assert result.exit_code == 1
    assert "not a placeholder" in result.output


def test_bash_delegation_emitted_for_inherit() -> None:
    alias = Alias(command="kubectl", complete={"inherit": "kubectl"})
    out = bash_completion("k", alias)
    assert "__qwik_delegate_k() {" in out
    assert 'src="$(dirname "$(command -v kubectl)")/kubectl_completion"' in out
    assert out.endswith("complete -F __qwik_delegate_k -o bashdefault -o default -- k")


# ---------------------------------------------------------------------------
# Real-shell integration
# ---------------------------------------------------------------------------

_COMPLETION_TESTED = [s for s in ("bash", "zsh") if shutil.which(s)]


def _invoke_completion(shell: str, script_lines: list[str]) -> tuple[int, str]:
    from tests._shells import resolve_shell_binary

    binary = resolve_shell_binary(shell)
    assert binary is not None
    script = "\n".join(script_lines) + "\n"
    result = subprocess.run(
        [binary, "-c", script],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode, result.stdout + result.stderr


@pytest.mark.integration
@pytest.mark.skipif(not shutil.which("bash"), reason="bash not installed")
@pytest.mark.skipif(sys.platform == "win32", reason="POSIX shell fixture script")
def test_bash_completion_offers_branches(tmp_path, monkeypatch) -> None:
    from qwik.config import _reset_config
    from qwik.core.store import get_store

    monkeypatch.setenv("QWIK_CONFIG_DIR", str(tmp_path))
    _reset_config()
    runner.invoke(
        app,
        ["add", "gco", "git", "checkout", "{branch}", "--complete-with", "branch=echo main dev"],
    )
    hook = get_renderer("bash").render_all(get_store().load().aliases)
    # Simulate <Tab> at argument position 1 of `gco `: bash's completion
    # machinery invoked manually with a single-word command line.
    script = [
        hook,
        "COMP_WORDS=(gco '')",
        "COMP_CWORD=1",
        "_qwik_complete_gco",
        'printf "%s\\n" "${COMPREPLY[@]}"',
    ]
    rc, out = _invoke_completion("bash", script)
    assert rc == 0
    assert sorted(out.split()) == ["dev", "main"]


@pytest.mark.integration
@pytest.mark.skipif(not shutil.which("zsh"), reason="zsh not installed")
def test_zsh_completion_offers_candidates(tmp_path, monkeypatch) -> None:
    from qwik.config import _reset_config

    monkeypatch.setenv("QWIK_CONFIG_DIR", str(tmp_path))
    _reset_config()
    runner.invoke(
        app,
        ["add", "gco", "git", "checkout", "{branch}", "--complete-with", "branch=echo main dev"],
    )
    store = _store_with_completions()
    hook = get_renderer("zsh").render_all(store.aliases)
    assert "compdef _qwik_complete_gco gco" in hook
