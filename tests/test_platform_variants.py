"""Tests for platform-conditional alias command variants (issue #34)."""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from qwik.cli import app
from qwik.config import Config
from qwik.core.models import Alias, AliasStore
from qwik.core.platform import PLATFORMS, current_platform, validate_platform
from qwik.core.store import Store
from qwik.core.substitute import placeholder_arity, placeholders_compatible
from qwik.shells.base import get_renderer
from qwik.ui.picker import PickerAction, PickerResult
from tests.test_sync import FakeGit, _make_dirty, _setup_env

runner = CliRunner()

# Alias names used below.  CI runners ship a real `open` binary on every
# platform (macOS /usr/bin/open, Ubuntu /usr/bin/open, R's open.EXE on
# Windows), so the conflict gate would prompt "Continue? [y/n]" and abort
# under CliRunner's empty stdin.  The autouse fixture neutralises only the
# PATH lookup for these names; `git` must remain findable for the sync test.
_TEST_ALIAS_NAMES = frozenset({"open", "gs", "gco", "hi"})
_REAL_WHICH = shutil.which


@pytest.fixture(autouse=True)
def _store_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from qwik.config import _reset_config

    monkeypatch.setenv("QWIK_CONFIG_DIR", str(tmp_path))
    _reset_config()
    monkeypatch.setattr(
        "qwik.core.conflicts.shutil.which",
        lambda name, *a, **kw: None if name in _TEST_ALIAS_NAMES else _REAL_WHICH(name, *a, **kw),
    )
    yield
    _reset_config()


def _loaded() -> Store:
    from qwik.core.store import get_store

    return get_store()


def _add_editor(path: Path, contents: str) -> Path:
    if sys.platform == "win32":
        writer = path / "editor.bat"
        payload = path / "payload.txt"
        payload.write_text(contents, encoding="utf-8")
        writer.write_text(
            f'@echo off\r\n"{sys.executable}" -c "'
            "import sys; "
            "open(sys.argv[1], 'w', encoding='utf-8')"
            ".write(open(sys.argv[2], encoding='utf-8').read())"
            f'" "%~1" "{payload}"\r\n',
            encoding="utf-8",
        )
        return writer
    writer = path / "editor.sh"
    writer.write_text(
        f"#!/usr/bin/env bash\ncat > \"$1\" <<'EDOFSNIPPET'\n{contents}\nEDOFSNIPPET\n",
        encoding="utf-8",
    )
    os.chmod(writer, 0o700)
    return writer


# --------------------------------------------------------------------------- #
# platform module
# --------------------------------------------------------------------------- #


class TestPlatform:
    @pytest.mark.parametrize(
        ("sys_platform", "expected"),
        [
            ("win32", "windows"),
            ("darwin", "macos"),
            ("linux", "linux"),
            ("cygwin", "linux"),
        ],
    )
    def test_current_platform_mapping(
        self, monkeypatch: pytest.MonkeyPatch, sys_platform: str, expected: str
    ) -> None:
        monkeypatch.setattr(sys, "platform", sys_platform)
        assert current_platform() == expected

    def test_validate_platform_accepts_known(self) -> None:
        for name in PLATFORMS:
            assert validate_platform(name) == name

    def test_validate_platform_normalises(self) -> None:
        assert validate_platform("  macOS ") == "macos"

    def test_validate_platform_rejects_unknown(self) -> None:
        with pytest.raises(ValueError, match="Invalid platform"):
            validate_platform("bsd")


# --------------------------------------------------------------------------- #
# model: variant collection and resolution
# --------------------------------------------------------------------------- #


class TestVariantModel:
    def test_flat_keys_collected(self) -> None:
        alias = Alias.model_validate({"command": "xdg-open {1}", "command_macos": "open {1}"})
        assert alias.command_variants == {"command_macos": "open {1}"}

    def test_platform_shell_flat_keys_collected(self) -> None:
        alias = Alias.model_validate({"command": "x", "command_windows_pwsh": "start {1}"})
        assert alias.command_variants == {"command_windows_pwsh": "start {1}"}

    def test_variants_dict_accepted(self) -> None:
        alias = Alias.model_validate({"command": "x", "command_variants": {"command_macos": "y"}})
        assert alias.command_variants == {"command_macos": "y"}

    def test_dict_and_flat_keys_merge(self) -> None:
        alias = Alias.model_validate(
            {
                "command": "x",
                "command_variants": {"command_macos": "y"},
                "command_windows": "z",
            }
        )
        assert alias.command_variants == {"command_macos": "y", "command_windows": "z"}

    def test_empty_variant_values_dropped(self) -> None:
        alias = Alias.model_validate({"command": "x", "command_macos": "   ", "command_linux": "y"})
        assert alias.command_variants == {"command_linux": "y"}

    def test_invalid_variant_key_rejected(self) -> None:
        with pytest.raises(Exception, match='Invalid variant key "command_bsd"'):
            Alias.model_validate({"command": "x", "command_bsd": "y"})

    def test_invalid_shell_suffix_rejected(self) -> None:
        with pytest.raises(Exception, match="Invalid variant key"):
            Alias.model_validate({"command": "x", "command_linux_ksh": "y"})

    def test_extra_forbid_still_enforced(self) -> None:
        with pytest.raises(Exception, match="Extra inputs are not permitted"):
            Alias.model_validate({"command": "x", "bogus_field": "y"})

    def test_command_still_required(self) -> None:
        with pytest.raises(ValidationError):
            Alias.model_validate({"command_macos": "y"})

    def test_default_no_variants(self) -> None:
        assert Alias(command="x").command_variants == {}

    def test_resolve_command_full_precedence(self) -> None:
        alias = Alias.model_validate(
            {
                "command": "base",
                "command_macos": "mac",
                "command_macos_bash": "mac-bash",
                "command_windows_pwsh": "win-pwsh",
            }
        )
        assert alias.resolve_command("macos", "bash") == "mac-bash"
        assert alias.resolve_command("macos", "zsh") == "mac"
        assert alias.resolve_command("macos", None) == "mac"
        assert alias.resolve_command("windows", "pwsh") == "win-pwsh"
        assert alias.resolve_command("windows", "bash") == "base"
        assert alias.resolve_command("linux", "bash") == "base"
        assert alias.resolve_command(None, "bash") == "base"
        assert alias.resolve_command(None, None) == "base"

    def test_resolve_command_base_only(self) -> None:
        alias = Alias(command="base")
        assert alias.resolve_command("macos", "zsh") == "base"


# --------------------------------------------------------------------------- #
# substitute: placeholder arity compatibility
# --------------------------------------------------------------------------- #


class TestPlaceholderArity:
    @pytest.mark.parametrize(
        ("command", "expected"),
        [
            ("echo hello", 0),
            ("echo {1}", 1),
            ("echo {1} {2}", 2),
            ("echo {2}", 2),
            ("echo {1:-x}", 1),
            ("echo {name}", 1),
            ("echo {name:-x} {2}", 2),
            ("echo {@}", None),
            ("echo {*}", None),
            ("echo {1} {@}", None),
        ],
    )
    def test_placeholder_arity(self, command: str, expected: int | None) -> None:
        assert placeholder_arity(command) == expected

    @pytest.mark.parametrize(
        ("base", "variant", "expected"),
        [
            ("echo {1}", "echo {1}", True),
            ("echo {1}", "echo {1} {2}", False),
            ("echo", "echo", True),
            ("echo", "echo {1}", False),
            ("echo {@}", "echo {1}", True),
            ("echo {1}", "echo {*}", True),
            ("echo {name}", "echo {1}", True),
        ],
    )
    def test_placeholders_compatible(self, base: str, variant: str, expected: bool) -> None:
        assert placeholders_compatible(base, variant) is expected


# --------------------------------------------------------------------------- #
# store: v1 → v2 migration with variants
# --------------------------------------------------------------------------- #


class TestV2Migration:
    @staticmethod
    def _store(tmp_path: Path) -> Store:
        return Store(Config(override_config_dir=tmp_path))

    @staticmethod
    def _write(tmp_path: Path, body: str) -> None:
        tmp_path.mkdir(parents=True, exist_ok=True)
        (tmp_path / "aliases.toml").write_text(body, encoding="utf-8")

    def test_v1_store_with_variants_migrates_forward(self, tmp_path: Path) -> None:
        self._write(
            tmp_path,
            (
                "[aliases.open]\n"
                'command = "xdg-open {1}"\n'
                'command_macos = "open {1}"\n'
                'created_at = "2026-05-10T10:00:00Z"\n'
                'updated_at = "2026-05-10T10:00:00Z"\n'
            ),
        )
        store = self._store(tmp_path)
        loaded = store.load()
        assert loaded.version == 2
        alias = loaded.get("open")
        assert alias is not None
        assert alias.command == "xdg-open {1}"
        assert alias.command_variants == {"command_macos": "open {1}"}
        on_disk = store.path.read_text(encoding="utf-8")
        assert "version = 2" in on_disk
        assert len(list(store._backup_dir.glob("aliases-*.toml"))) == 1

    def test_v1_store_without_variants_migrates_cleanly(self, tmp_path: Path) -> None:
        self._write(
            tmp_path,
            (
                "[aliases.gs]\n"
                'command = "git status"\n'
                'created_at = "2026-05-10T10:00:00Z"\n'
                'updated_at = "2026-05-10T10:00:00Z"\n'
            ),
        )
        store = self._store(tmp_path)
        loaded = store.load()
        assert loaded.version == 2
        assert loaded.get("gs") is not None
        assert loaded.get("gs").command_variants == {}


# --------------------------------------------------------------------------- #
# CLI add --platform
# --------------------------------------------------------------------------- #


class TestAddPlatform:
    def test_new_alias_sets_base_and_variant(self) -> None:
        result = runner.invoke(app, ["add", "open", "open {1}", "--platform", "macos"])
        assert result.exit_code == 0, result.output
        assert "base + macos variant" in result.output
        alias = _loaded().load().get("open")
        assert alias is not None
        assert alias.command == "open {1}"
        assert alias.command_variants == {"command_macos": "open {1}"}

    def test_existing_alias_gains_variant_keeps_base(self) -> None:
        runner.invoke(app, ["add", "open", "xdg-open {1}"])
        result = runner.invoke(app, ["add", "open", "open {1}", "--platform", "macos"])
        assert result.exit_code == 0, result.output
        alias = _loaded().load().get("open")
        assert alias is not None
        assert alias.command == "xdg-open {1}"
        assert alias.command_variants == {"command_macos": "open {1}"}

    def test_variant_upsert_requires_force(self) -> None:
        runner.invoke(app, ["add", "open", "xdg-open {1}"])
        runner.invoke(app, ["add", "open", "open {1}", "--platform", "macos"])
        result = runner.invoke(app, ["add", "open", "open2 {1}", "--platform", "macos"])
        assert result.exit_code == 1
        assert "already exists" in result.output
        alias = _loaded().load().get("open")
        assert alias is not None
        assert alias.command_variants == {"command_macos": "open {1}"}

        forced = runner.invoke(app, ["add", "open", "open2 {1}", "--platform", "macos", "--force"])
        assert forced.exit_code == 0, forced.output
        alias = _loaded().load().get("open")
        assert alias is not None
        assert alias.command_variants == {"command_macos": "open2 {1}"}
        assert alias.command == "xdg-open {1}"

    def test_readding_identical_variant_is_accepted(self) -> None:
        runner.invoke(app, ["add", "open", "xdg-open {1}"])
        first = runner.invoke(app, ["add", "open", "open {1}", "--platform", "macos"])
        second = runner.invoke(app, ["add", "open", "open {1}", "--platform", "macos"])
        assert first.exit_code == 0 and second.exit_code == 0

    def test_invalid_platform_rejected(self) -> None:
        result = runner.invoke(app, ["add", "open", "open {1}", "--platform", "bsd"])
        assert result.exit_code == 1
        assert "Invalid platform" in result.output

    def test_arity_mismatch_rejected(self) -> None:
        runner.invoke(app, ["add", "gco", "git checkout {1}"])
        result = runner.invoke(app, ["add", "gco", "git branch", "--platform", "macos"])
        assert result.exit_code == 1
        assert "arity" in result.output.lower()

    def test_variant_placeholder_validation(self) -> None:
        runner.invoke(app, ["add", "gco", "git checkout {1}"])
        result = runner.invoke(app, ["add", "gco", "echo {0}", "--platform", "macos"])
        assert result.exit_code == 1
        assert "1-based" in result.output

    def test_base_path_still_works(self) -> None:
        result = runner.invoke(app, ["add", "gs", "git", "status"])
        assert result.exit_code == 0
        alias = _loaded().load().get("gs")
        assert alias is not None
        assert alias.command == "git status"
        assert alias.command_variants == {}


# --------------------------------------------------------------------------- #
# display: show / list
# --------------------------------------------------------------------------- #


class TestShowVariants:
    def test_show_lists_variants_and_marks_active(self, monkeypatch: pytest.MonkeyPatch) -> None:
        runner.invoke(app, ["add", "open", "xdg-open {1}"])
        runner.invoke(app, ["add", "open", "open {1}", "--platform", "macos"])
        monkeypatch.setattr(sys, "platform", "darwin")
        monkeypatch.setenv("QWIK_SHELL", "bash")
        result = runner.invoke(app, ["show", "open"])
        assert result.exit_code == 0
        assert "command_macos" in result.output
        assert "active" in result.output
        assert "open {1}" in result.output

    def test_show_resolved_row_shown(self, monkeypatch: pytest.MonkeyPatch) -> None:
        runner.invoke(app, ["add", "gs", "git", "status"])
        monkeypatch.setenv("QWIK_SHELL", "bash")
        result = runner.invoke(app, ["show", "gs"])
        assert result.exit_code == 0
        assert "Resolved" in result.output
        assert "git status" in result.output

    def test_show_base_only_alias_has_no_variants(self) -> None:
        runner.invoke(app, ["add", "gs", "git", "status"])
        result = runner.invoke(app, ["show", "gs"])
        assert result.exit_code == 0
        assert "command_macos" not in result.output


class TestListPlatform:
    def test_list_platform_preview(self, monkeypatch: pytest.MonkeyPatch) -> None:
        runner.invoke(app, ["add", "open", "xdg-open {1}"])
        runner.invoke(app, ["add", "open", "start {1}", "--platform", "windows"])
        result = runner.invoke(app, ["list", "--platform", "windows"])
        assert result.exit_code == 0, result.output
        assert "start {1}" in result.output
        assert "resolved for platform: windows" in result.output.lower()

    def test_list_without_platform_shows_base(self) -> None:
        runner.invoke(app, ["add", "open", "xdg-open {1}"])
        runner.invoke(app, ["add", "open", "start {1}", "--platform", "windows"])
        result = runner.invoke(app, ["list"])
        assert result.exit_code == 0
        assert "xdg-open {1}" in result.output

    def test_list_invalid_platform_rejected(self) -> None:
        result = runner.invoke(app, ["list", "--platform", "bsd"])
        assert result.exit_code == 1
        assert "Invalid platform" in result.output


# --------------------------------------------------------------------------- #
# rendering: render_all resolves variants
# --------------------------------------------------------------------------- #


class TestRenderAllVariants:
    def test_resolves_variant_for_platform(self) -> None:
        alias = Alias.model_validate(
            {"command": "echo linuxbase", "command_macos": "echo macvariant"}
        )
        renderer = get_renderer("bash")
        snippet = renderer.render_all({"open": alias}, platform="macos", shell="bash")
        assert "macvariant" in snippet
        assert "linuxbase" not in snippet
        other = renderer.render_all({"open": alias}, platform="linux", shell="bash")
        assert "linuxbase" in other
        assert "macvariant" not in other

    def test_defaults_match_explicit_current_platform(self) -> None:
        alias = Alias.model_validate(
            {"command": "echo linuxbase", "command_macos": "echo macvariant"}
        )
        renderer = get_renderer("bash")
        assert renderer.render_all({"open": alias}) == renderer.render_all(
            {"open": alias}, platform=current_platform(), shell=renderer.shell_name
        )

    def test_base_only_alias_renders_unchanged(self) -> None:
        alias = Alias(command="git status")
        renderer = get_renderer("bash")
        assert "git status" in renderer.render_all({"gs": alias})

    def test_platform_shell_variant_beats_platform_variant(self) -> None:
        alias = Alias.model_validate(
            {
                "command": "echo base",
                "command_macos": "echo mac",
                "command_macos_zsh": "echo mac-zsh",
            }
        )
        renderer = get_renderer("zsh")
        # shell defaults to the renderer's own shell name (zsh)
        snippet = renderer.render_all({"open": alias}, platform="macos")
        assert "mac-zsh" in snippet


# --------------------------------------------------------------------------- #
# execution paths: run / pick resolve like init
# --------------------------------------------------------------------------- #


class TestRunResolvesVariant:
    def test_run_uses_platform_variant(self, monkeypatch: pytest.MonkeyPatch) -> None:
        runner.invoke(app, ["add", "open", "echo linuxbase"])
        runner.invoke(app, ["add", "open", "echo macvariant", "--platform", "macos"])
        # Patch the resolution seam, not sys.platform itself: mocking
        # sys.platform to a POSIX value on Windows makes FileLock branch to
        # fcntl and crash (No module named 'fcntl') in bump_usage.
        monkeypatch.setattr("qwik.commands.run.current_platform", lambda: "macos")
        monkeypatch.setenv("QWIK_SHELL", "bash")
        with patch("subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            result = runner.invoke(app, ["run", "open"])
        assert result.exit_code == 0
        assert mock_run.called
        invoked = str(mock_run.call_args)
        assert "macvariant" in invoked
        assert "linuxbase" not in invoked

    def test_run_falls_back_to_base(self, monkeypatch: pytest.MonkeyPatch) -> None:
        runner.invoke(app, ["add", "open", "echo linuxbase"])
        runner.invoke(app, ["add", "open", "echo winvariant", "--platform", "windows"])
        monkeypatch.setattr("qwik.commands.run.current_platform", lambda: "macos")
        monkeypatch.setenv("QWIK_SHELL", "bash")
        with patch("subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            result = runner.invoke(app, ["run", "open"])
        assert result.exit_code == 0
        invoked = str(mock_run.call_args)
        assert "linuxbase" in invoked
        assert "winvariant" not in invoked


class TestPickResolvesVariant:
    def test_pick_uses_platform_variant(self, monkeypatch: pytest.MonkeyPatch) -> None:
        runner.invoke(app, ["add", "open", "echo linuxbase"])
        runner.invoke(app, ["add", "open", "echo macvariant", "--platform", "macos"])
        # Same seam-not-sys.platform rationale as the run tests above.
        monkeypatch.setattr("qwik.commands.pick.current_platform", lambda: "macos")
        monkeypatch.setenv("QWIK_SHELL", "bash")
        with (
            patch("qwik.commands.pick.run_picker") as mock_picker,
            patch("subprocess.run") as mock_run,
        ):
            mock_picker.return_value = PickerResult(PickerAction.RUN, "open")
            mock_run.return_value.returncode = 0
            result = runner.invoke(app, ["pick"])
        assert result.exit_code == 0
        assert mock_run.called
        invoked = str(mock_run.call_args)
        assert "macvariant" in invoked
        assert "linuxbase" not in invoked


# --------------------------------------------------------------------------- #
# edit: variant editing and removal
# --------------------------------------------------------------------------- #


class TestEditVariants:
    def test_edit_adds_variant(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        runner.invoke(app, ["add", "open", "xdg-open {1}"])
        snippet = (
            'command = "xdg-open {1}"\n'
            'command_macos = "open {1}"\n'
            'tag = []\ngroup = ""\ndescription = ""\nenabled = true\n'
        )
        editor = _add_editor(tmp_path, snippet)
        monkeypatch.setenv("EDITOR", str(editor))
        result = runner.invoke(app, ["edit", "open"])
        assert result.exit_code == 0, result.output
        alias = _loaded().load().get("open")
        assert alias is not None
        assert alias.command_variants == {"command_macos": "open {1}"}

    def test_edit_removes_variant(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        runner.invoke(app, ["add", "open", "xdg-open {1}"])
        runner.invoke(app, ["add", "open", "open {1}", "--platform", "macos"])
        snippet = (
            'command = "xdg-open {1}"\ntag = []\ngroup = ""\ndescription = ""\nenabled = true\n'
        )
        editor = _add_editor(tmp_path, snippet)
        monkeypatch.setenv("EDITOR", str(editor))
        result = runner.invoke(app, ["edit", "open"])
        assert result.exit_code == 0, result.output
        alias = _loaded().load().get("open")
        assert alias is not None
        assert alias.command_variants == {}

    def test_edit_variant_arity_mismatch_rejected(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        runner.invoke(app, ["add", "gco", "git checkout {1}"])
        snippet = (
            'command = "git checkout {1}"\n'
            'command_macos = "git branch"\n'
            'tag = []\ngroup = ""\ndescription = ""\nenabled = true\n'
        )
        editor = _add_editor(tmp_path, snippet)
        monkeypatch.setenv("EDITOR", str(editor))
        result = runner.invoke(app, ["edit", "gco"])
        assert result.exit_code == 1
        assert "arity" in result.output.lower()

    def test_edit_variant_placeholder_invalid_rejected(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        runner.invoke(app, ["add", "gco", "git checkout {1}"])
        snippet = (
            'command = "git checkout {1}"\n'
            'command_macos = "echo {0}"\n'
            'tag = []\ngroup = ""\ndescription = ""\nenabled = true\n'
        )
        editor = _add_editor(tmp_path, snippet)
        monkeypatch.setenv("EDITOR", str(editor))
        result = runner.invoke(app, ["edit", "gco"])
        assert result.exit_code == 1

    def test_edit_rejects_nested_variants_table(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        runner.invoke(app, ["add", "gco", "git checkout {1}"])
        snippet = (
            'command = "git checkout {1}"\n[command_variants]\ncommand_macos = "git branch {1}"\n'
        )
        editor = _add_editor(tmp_path, snippet)
        monkeypatch.setenv("EDITOR", str(editor))
        result = runner.invoke(app, ["edit", "gco"])
        assert result.exit_code == 1
        assert "flat" in result.output.lower()

    def test_noop_edit_preserves_variants(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        runner.invoke(app, ["add", "open", "xdg-open {1}"])
        runner.invoke(app, ["add", "open", "open {1}", "--platform", "macos"])
        if sys.platform == "win32":
            editor = tmp_path / "noop.bat"
            editor.write_text("@echo off\r\n", encoding="utf-8")
        else:
            editor = tmp_path / "noop.sh"
            editor.write_text("#!/usr/bin/env bash\ntrue\n", encoding="utf-8")
            os.chmod(editor, 0o700)
        monkeypatch.setenv("EDITOR", str(editor))
        result = runner.invoke(app, ["edit", "open"])
        assert result.exit_code == 0, result.output
        alias = _loaded().load().get("open")
        assert alias is not None
        assert alias.command_variants == {"command_macos": "open {1}"}


# --------------------------------------------------------------------------- #
# round-trips: store serialization, export/import, sync
# --------------------------------------------------------------------------- #


class TestVariantRoundTrips:
    def test_store_serializes_flat_variant_keys(self) -> None:
        runner.invoke(app, ["add", "open", "xdg-open {1}"])
        runner.invoke(app, ["add", "open", "open {1}", "--platform", "macos"])
        on_disk = _loaded().path.read_text(encoding="utf-8")
        assert 'command_macos = "open {1}"' in on_disk
        assert "version = 2" in on_disk

    def test_toml_export_import_round_trip(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        runner.invoke(app, ["add", "open", "xdg-open {1}"])
        runner.invoke(app, ["add", "open", "open {1}", "--platform", "macos"])
        export_path = tmp_path / "aliases-export.toml"
        result = runner.invoke(app, ["export", str(export_path)])
        assert result.exit_code == 0, result.output
        raw = export_path.read_text(encoding="utf-8")
        assert 'command_macos = "open {1}"' in raw

        # Empty the live store, then import the export into it: the variant
        # must survive the full round trip.
        _loaded().path.unlink(missing_ok=True)
        result = runner.invoke(app, ["import", str(export_path), "--yes"])
        assert result.exit_code == 0, result.output
        alias = _loaded().load().get("open")
        assert alias is not None
        assert alias.command_variants == {"command_macos": "open {1}"}

    def test_json_export_has_variants(self, tmp_path: Path) -> None:
        runner.invoke(app, ["add", "open", "xdg-open {1}"])
        runner.invoke(app, ["add", "open", "open {1}", "--platform", "macos"])
        export_path = tmp_path / "aliases-export.json"
        result = runner.invoke(app, ["export", str(export_path)])
        assert result.exit_code == 0, result.output
        import json

        payload = json.loads(export_path.read_text(encoding="utf-8"))
        assert payload["aliases"]["open"]["command_variants"] == {"command_macos": "open {1}"}

    def test_import_flat_variant_keys(self, tmp_path: Path) -> None:
        incoming = tmp_path / "incoming.toml"
        incoming.write_text(
            "version = 2\n"
            "[aliases.open]\n"
            'command = "xdg-open {1}"\n'
            'command_macos = "open {1}"\n'
            'command_windows_pwsh = "start {1}"\n',
            encoding="utf-8",
        )
        result = runner.invoke(app, ["import", str(incoming), "--yes"])
        assert result.exit_code == 0, result.output
        alias = _loaded().load().get("open")
        assert alias is not None
        assert alias.command_variants == {
            "command_macos": "open {1}",
            "command_windows_pwsh": "start {1}",
        }

    def test_sync_export_contains_variant_keys(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake: FakeGit = _setup_env(tmp_path, monkeypatch)
        runner.invoke(app, ["add", "open", "xdg-open {1}"])
        runner.invoke(app, ["add", "open", "open {1}", "--platform", "macos"])
        _make_dirty(fake)
        result = runner.invoke(app, ["sync", "init", "--remote", "https://example.com/d.git"])
        assert result.exit_code == 0, result.output
        sync_toml = (tmp_path / "qwik-sync" / "aliases.toml").read_text(encoding="utf-8")
        assert 'command_macos = "open {1}"' in sync_toml


# --------------------------------------------------------------------------- #
# diff / merge consistency
# --------------------------------------------------------------------------- #


class TestVariantConsistency:
    def test_diff_counts_variant_change_as_changed(self) -> None:
        from qwik.core.diff import diff_stores

        a = AliasStore.model_validate(
            {"version": 2, "aliases": {"open": {"command": "xdg-open {1}"}}}
        )
        b = AliasStore.model_validate(
            {
                "version": 2,
                "aliases": {"open": {"command": "xdg-open {1}", "command_macos": "open {1}"}},
            }
        )
        diff = diff_stores(a, b)
        assert not diff.empty
        assert [e.name for e in diff.changed] == ["open"]

    def test_merge_into_updates_on_variant_change(self) -> None:
        from qwik.commands.importer import merge_into

        target = AliasStore.model_validate(
            {"version": 2, "aliases": {"open": {"command": "xdg-open {1}"}}}
        )
        incoming = AliasStore.model_validate(
            {
                "version": 2,
                "aliases": {"open": {"command": "xdg-open {1}", "command_macos": "open {1}"}},
            }
        )
        added, updated, unchanged = merge_into(incoming, target)
        assert (added, updated, unchanged) == (0, 1, 0)
