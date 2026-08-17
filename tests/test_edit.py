"""Tests for qwik edit command."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

from qwik.cli import app

runner = CliRunner()


def _create_editor_script(path: Path, contents: str) -> Path:
    if sys.platform == "win32":
        writer = path / "editor.bat"
        # Batch can't easily write arbitrary multi-line text; delegate to Python.
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


def _no_op_editor_script(path: Path) -> Path:
    """An ``$EDITOR`` that opens the file and changes nothing.

    A bare ``.sh`` script isn't a Windows executable, so this needs the
    same ``.bat``-vs-``.sh`` split as :func:`_create_editor_script`.
    """
    if sys.platform == "win32":
        writer = path / "noop.bat"
        writer.write_text("@echo off\r\n", encoding="utf-8")
        return writer
    writer = path / "noop.sh"
    writer.write_text("#!/usr/bin/env bash\ntrue\n", encoding="utf-8")
    os.chmod(writer, 0o700)
    return writer


class TestEditCommand:
    @staticmethod
    def _setup(tmp_path, monkeypatch):
        from qwik.config import _reset_config

        monkeypatch.setenv("QWIK_CONFIG_DIR", str(tmp_path))
        _reset_config()
        runner.invoke(app, ["add", "gs", "git", "status"])

    def test_edit_alias_not_found(self, tmp_path, monkeypatch) -> None:
        self._setup(tmp_path, monkeypatch)
        result = runner.invoke(app, ["edit", "nonexistent"])
        assert result.exit_code == 1
        assert "does not exist" in result.output

    def test_edit_success(self, tmp_path, monkeypatch) -> None:
        self._setup(tmp_path, monkeypatch)
        snippet = 'command = "git log"\ntag = ["work"]\ndescription = "changed"\nenabled = false\n'
        editor = _create_editor_script(tmp_path, snippet)
        monkeypatch.setenv("EDITOR", str(editor))
        result = runner.invoke(app, ["edit", "gs"])
        assert result.exit_code == 0
        assert "Updated" in result.output

        # Verify persisted change
        from qwik.core.store import get_store

        data = get_store().load()
        assert data.get("gs").command == "git log"
        assert data.get("gs").tag == ["work"]
        assert data.get("gs").enabled is False

    def test_edit_boolean_lowercase(self, tmp_path, monkeypatch) -> None:
        self._setup(tmp_path, monkeypatch)
        snippet = 'command = "git log"\ntag = ["git"]\ndescription = ""\nenabled = false\n'
        editor = _create_editor_script(tmp_path, snippet)
        monkeypatch.setenv("EDITOR", str(editor))
        result = runner.invoke(app, ["edit", "gs"])
        assert result.exit_code == 0
        assert "Updated" in result.output

    def test_edit_inline_comments(self, tmp_path, monkeypatch) -> None:
        self._setup(tmp_path, monkeypatch)
        snippet = (
            'command = "git log" # my comment\ntag = ["git"]\n'
            'description = "desc"\nenabled = true\n'
        )
        editor = _create_editor_script(tmp_path, snippet)
        monkeypatch.setenv("EDITOR", str(editor))
        result = runner.invoke(app, ["edit", "gs"])
        assert result.exit_code == 0

    def test_edit_list_value(self, tmp_path, monkeypatch) -> None:
        self._setup(tmp_path, monkeypatch)
        snippet = 'command = "git log"\ntag = ["git", "work"]\ndescription = ""\nenabled = true\n'
        editor = _create_editor_script(tmp_path, snippet)
        monkeypatch.setenv("EDITOR", str(editor))
        result = runner.invoke(app, ["edit", "gs"])
        assert result.exit_code == 0

    def test_edit_empty_list(self, tmp_path, monkeypatch) -> None:
        self._setup(tmp_path, monkeypatch)
        snippet = 'command = "git log"\ntag = []\ndescription = ""\nenabled = true\n'
        editor = _create_editor_script(tmp_path, snippet)
        monkeypatch.setenv("EDITOR", str(editor))
        result = runner.invoke(app, ["edit", "gs"])
        assert result.exit_code == 0

    def test_edit_template_alias(self, tmp_path, monkeypatch) -> None:
        self._setup(tmp_path, monkeypatch)
        runner.invoke(app, ["add", "gco", "git checkout {1}"])
        snippet = 'command = "git branch {1}"\ntag = []\ndescription = ""\nenabled = true\n'
        editor = _create_editor_script(tmp_path, snippet)
        monkeypatch.setenv("EDITOR", str(editor))
        result = runner.invoke(app, ["edit", "gco"])
        assert result.exit_code == 0

    def test_edit_no_changes(self, tmp_path, monkeypatch) -> None:
        self._setup(tmp_path, monkeypatch)
        snippet = 'command = "git status"\ntag = []\ndescription = ""\nenabled = true\n'
        editor = _create_editor_script(tmp_path, snippet)
        monkeypatch.setenv("EDITOR", str(editor))
        result = runner.invoke(app, ["edit", "gs"])
        assert result.exit_code == 0

    def test_edit_no_op_preserves_group(self, tmp_path, monkeypatch) -> None:
        # Regression: `group` used to be silently dropped by every edit,
        # even a no-op one, because the snippet never included it and the
        # reconstruction never passed it through.
        self._setup(tmp_path, monkeypatch)
        runner.invoke(app, ["group", "gs", "git"])

        no_op_editor = _no_op_editor_script(tmp_path)
        monkeypatch.setenv("EDITOR", str(no_op_editor))

        result = runner.invoke(app, ["edit", "gs"])
        assert result.exit_code == 0

        from qwik.core.store import get_store

        data = get_store().load()
        assert data.get("gs").group == "git"

    def test_edit_can_change_group(self, tmp_path, monkeypatch) -> None:
        self._setup(tmp_path, monkeypatch)
        snippet = (
            'command = "git status"\ntag = []\ngroup = "vcs"\ndescription = ""\nenabled = true\n'
        )
        editor = _create_editor_script(tmp_path, snippet)
        monkeypatch.setenv("EDITOR", str(editor))
        result = runner.invoke(app, ["edit", "gs"])
        assert result.exit_code == 0

        from qwik.core.store import get_store

        assert get_store().load().get("gs").group == "vcs"

    def test_edit_can_clear_group(self, tmp_path, monkeypatch) -> None:
        self._setup(tmp_path, monkeypatch)
        runner.invoke(app, ["group", "gs", "git"])
        snippet = 'command = "git status"\ntag = []\ngroup = ""\ndescription = ""\nenabled = true\n'
        editor = _create_editor_script(tmp_path, snippet)
        monkeypatch.setenv("EDITOR", str(editor))
        result = runner.invoke(app, ["edit", "gs"])
        assert result.exit_code == 0

        from qwik.core.store import get_store

        assert get_store().load().get("gs").group is None

    def test_edit_round_trips_every_field_unchanged(self, tmp_path, monkeypatch) -> None:
        # A no-op edit (the editor script exits without touching the file)
        # must leave every field byte-identical apart from `updated_at`.
        # This is the regression the group-drop bug was an instance of —
        # it fails again if a future field is added to `Alias` without
        # this command being updated to carry it through.
        self._setup(tmp_path, monkeypatch)
        runner.invoke(
            app,
            [
                "add",
                "gco",
                "git checkout {1}",
                "--tag",
                "git,vcs",
                "--group",
                "git",
                "--description",
                "checkout a branch",
            ],
        )
        runner.invoke(app, ["run", "gco", "main"])  # bump run_count / last_used

        from qwik.core.store import get_store

        before = get_store().load().get("gco")
        assert before is not None
        assert before.run_count > 0
        assert before.last_used is not None

        no_op_editor = _no_op_editor_script(tmp_path)
        monkeypatch.setenv("EDITOR", str(no_op_editor))

        result = runner.invoke(app, ["edit", "gco"])
        assert result.exit_code == 0

        after = get_store().load().get("gco")
        assert after is not None
        assert after.command == before.command
        assert after.tag == before.tag
        assert after.group == before.group
        assert after.description == before.description
        assert after.enabled == before.enabled
        assert after.created_at == before.created_at
        assert after.last_used == before.last_used
        assert after.run_count == before.run_count
        assert after.updated_at >= before.updated_at

    def test_edit_malformed_snippet_reports_error(self, tmp_path, monkeypatch) -> None:
        # Invalid TOML must be a hard error, not silently keep the old
        # values (the old ad-hoc line parser silently ignored anything it
        # couldn't split on " = ").
        self._setup(tmp_path, monkeypatch)
        editor = _create_editor_script(tmp_path, 'command = "unterminated string\n')
        monkeypatch.setenv("EDITOR", str(editor))
        result = runner.invoke(app, ["edit", "gs"])
        assert result.exit_code == 1
        assert "parse" in result.output.lower()

        from qwik.core.store import get_store

        assert get_store().load().get("gs").command == "git status"

    def test_edit_invalid_group_reports_error(self, tmp_path, monkeypatch) -> None:
        self._setup(tmp_path, monkeypatch)
        snippet = (
            'command = "git status"\ntag = []\ngroup = "not a valid name!"\n'
            'description = ""\nenabled = true\n'
        )
        editor = _create_editor_script(tmp_path, snippet)
        monkeypatch.setenv("EDITOR", str(editor))
        result = runner.invoke(app, ["edit", "gs"])
        assert result.exit_code == 1

        from qwik.core.store import get_store

        assert get_store().load().get("gs").group is None

    def test_edit_editor_failed(self, tmp_path, monkeypatch) -> None:
        self._setup(tmp_path, monkeypatch)
        if sys.platform == "win32":
            fail_editor = tmp_path / "fail_editor.bat"
            fail_editor.write_text("@echo off\nexit /b 1\n", encoding="utf-8")
        else:
            fail_editor = tmp_path / "fail_editor.sh"
            fail_editor.write_text("#!/usr/bin/env bash\nexit 1\n")
            os.chmod(fail_editor, 0o700)
        monkeypatch.setenv("EDITOR", str(fail_editor))
        result = runner.invoke(app, ["edit", "gs"])
        assert result.exit_code == 1
        assert "Editor exited" in result.output


class TestEditorSelection:
    def test_editor_missing_filenotfound(self, tmp_path, monkeypatch):
        from qwik.config import _reset_config

        monkeypatch.setenv("QWIK_CONFIG_DIR", str(tmp_path))
        monkeypatch.setenv("EDITOR", "definitely-not-a-real-editor-xyz")
        monkeypatch.delenv("VISUAL", raising=False)
        _reset_config()
        runner.invoke(app, ["add", "gs", "git", "status"])
        result = runner.invoke(app, ["edit", "gs"])
        assert result.exit_code == 1
        assert "not found" in result.output.lower() or "Editor" in result.output

    def test_visual_takes_precedence_over_default(self, tmp_path, monkeypatch):
        if sys.platform == "win32":
            pytest.skip("POSIX-only editor script test")
        from qwik.config import _reset_config

        monkeypatch.setenv("QWIK_CONFIG_DIR", str(tmp_path))
        _reset_config()
        runner.invoke(app, ["add", "gs", "git", "status"])
        editor = _create_editor_script(
            tmp_path, 'command = "git log"\ntag = []\ndescription = ""\nenabled = true'
        )
        monkeypatch.setenv("EDITOR", "")
        monkeypatch.setenv("VISUAL", str(editor))
        result = runner.invoke(app, ["edit", "gs"])
        assert result.exit_code == 0
