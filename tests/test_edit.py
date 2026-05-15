"""Tests for qwik edit command."""

from __future__ import annotations

import os
from pathlib import Path

from typer.testing import CliRunner

from qwik.cli import app

runner = CliRunner()


def _create_editor_script(path: Path, contents: str) -> Path:
    writer = path / "editor.sh"
    writer.write_text(
        f"#!/usr/bin/env bash\ncat > \"$1\" <<'EDOFSNIPPET'\n{contents}\nEDOFSNIPPET\n",
        encoding="utf-8",
    )
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
        snippet = (
            'command = "git log"\n'
            'tag = ["work"]\n'
            'description = "changed"\n'
            "enabled = false\n"
        )
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
        snippet = (
            'command = "git log"\ntag = ["git"]\ndescription = ""\nenabled = false\n'
        )
        editor = _create_editor_script(tmp_path, snippet)
        monkeypatch.setenv("EDITOR", str(editor))
        result = runner.invoke(app, ["edit", "gs"])
        assert result.exit_code == 0
        assert "Updated" in result.output

    def test_edit_inline_comments(self, tmp_path, monkeypatch) -> None:
        self._setup(tmp_path, monkeypatch)
        snippet = 'command = "git log" # my comment\ntag = ["git"]\ndescription = "desc"\nenabled = true\n'
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
        snippet = (
            'command = "git branch {1}"\ntag = []\ndescription = ""\nenabled = true\n'
        )
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

    def test_edit_editor_failed(self, tmp_path, monkeypatch) -> None:
        self._setup(tmp_path, monkeypatch)
        fail_editor = tmp_path / "fail_editor.sh"
        fail_editor.write_text("#!/usr/bin/env bash\nexit 1\n")
        os.chmod(fail_editor, 0o700)
        monkeypatch.setenv("EDITOR", str(fail_editor))
        result = runner.invoke(app, ["edit", "gs"])
        assert result.exit_code == 1
        assert "Editor exited" in result.output
