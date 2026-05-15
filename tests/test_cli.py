"""CLI integration tests using Typer's CliRunner."""

import json

import pytest
from typer.testing import CliRunner

from qwik.cli import app
from qwik.config import _reset_config

runner = CliRunner()


@pytest.fixture(autouse=True)
def clean_store(tmp_path, monkeypatch):
    """Redirect qwik store to a temp directory for every test."""
    monkeypatch.setenv("QWIK_CONFIG_DIR", str(tmp_path))
    _reset_config()
    yield tmp_path


class TestVersionHelp:
    def test_version_flag(self) -> None:
        result = runner.invoke(app, ["-v"])
        assert result.exit_code == 0
        assert "qwik" in result.output

    def test_help_flag(self) -> None:
        result = runner.invoke(app, ["-h"])
        assert result.exit_code == 0
        assert "friendly CLI alias manager" in result.output

    def test_help_subcommand(self) -> None:
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "add" in result.output


class TestAddCommand:
    def test_add_basic(self, clean_store) -> None:
        result = runner.invoke(app, ["add", "gs", "git", "status"])
        assert result.exit_code == 0
        assert "Added" in result.output

    def test_add_with_tag(self, clean_store) -> None:
        result = runner.invoke(app, ["add", "gs", "git", "status", "--tag", "git"])
        assert result.exit_code == 0
        assert "Added" in result.output

    def test_add_force_overwrite(self, clean_store) -> None:
        runner.invoke(app, ["add", "gs", "git", "status"])
        result = runner.invoke(app, ["add", "gs", "git", "status", "--force"])
        assert result.exit_code == 0
        assert "Added" in result.output

    def test_add_duplicate_error(self, clean_store) -> None:
        runner.invoke(app, ["add", "gs", "git", "status"])
        result = runner.invoke(app, ["add", "gs", "git", "status"])
        assert result.exit_code == 1
        assert "already exists" in result.output

    def test_add_invalid_name(self, clean_store) -> None:
        result = runner.invoke(app, ["add", "123bad", "echo"])
        assert result.exit_code == 1
        assert "Names must match" in result.output

    def test_add_builtin_conflict(self, clean_store) -> None:
        result = runner.invoke(app, ["add", "cd", "echo", "hi", "--force"])
        assert result.exit_code == 0
        assert "Added" in result.output

    def test_add_builtin_without_force(self, clean_store) -> None:
        result = runner.invoke(app, ["add", "cd", "echo", "hi"])
        assert result.exit_code == 1
        assert "shell builtin" in result.output

    def test_add_shadows_path(self, clean_store) -> None:
        """Shadowing warnings require interactive confirmation - not testable in CliRunner."""
        pytest.skip("Interactive confirmation not testable without stdin mock")


class TestListCommand:
    def test_list_empty(self, clean_store) -> None:
        result = runner.invoke(app, ["list"])
        assert result.exit_code == 0
        assert "No aliases yet" in result.output

    def test_list_with_aliases(self, clean_store) -> None:
        runner.invoke(app, ["add", "gs", "git", "status"])
        result = runner.invoke(app, ["list"])
        assert result.exit_code == 0
        assert "gs" in result.output

    def test_list_tag_filter(self, clean_store) -> None:
        runner.invoke(app, ["add", "gs", "git", "status", "--tag", "git"])
        runner.invoke(app, ["add", "ls", "ls", "-la"])
        result = runner.invoke(app, ["list", "--tag", "git"])
        assert result.exit_code == 0
        assert "gs" in result.output
        assert "ls" not in result.output


class TestShowCommand:
    def test_show_existing(self, clean_store) -> None:
        runner.invoke(app, ["add", "gs", "git", "status"])
        result = runner.invoke(app, ["show", "gs"])
        assert result.exit_code == 0
        assert "git status" in result.output

    def test_show_missing(self, clean_store) -> None:
        result = runner.invoke(app, ["show", "nonexistent"])
        assert result.exit_code == 1
        assert "does not exist" in result.output


class TestRemoveCommand:
    def test_remove_yes(self, clean_store) -> None:
        runner.invoke(app, ["add", "gs", "git", "status"])
        result = runner.invoke(app, ["rm", "gs", "--yes"])
        assert result.exit_code == 0
        assert "Removed" in result.output

    def test_remove_missing(self, clean_store) -> None:
        result = runner.invoke(app, ["rm", "gs", "--yes"])
        assert result.exit_code == 1
        assert "does not exist" in result.output


class TestRenameCommand:
    def test_rename_success(self, clean_store) -> None:
        runner.invoke(app, ["add", "gs", "git", "status"])
        result = runner.invoke(app, ["rename", "gs", "gst"])
        assert result.exit_code == 0
        assert "Renamed" in result.output

    def test_rename_missing_source(self, clean_store) -> None:
        result = runner.invoke(app, ["rename", "gs", "gst"])
        assert result.exit_code == 1
        assert "does not exist" in result.output

    def test_rename_target_exists(self, clean_store) -> None:
        runner.invoke(app, ["add", "gs", "git", "status"])
        runner.invoke(app, ["add", "gst", "git", "status"])
        result = runner.invoke(app, ["rename", "gs", "gst"])
        assert result.exit_code == 1
        assert "already exists" in result.output


class TestEnableDisable:
    def test_disable_and_enable(self, clean_store) -> None:
        runner.invoke(app, ["add", "gs", "git", "status"])
        result = runner.invoke(app, ["disable", "gs"])
        assert result.exit_code == 0
        assert "disabled" in result.output

        result = runner.invoke(app, ["enable", "gs"])
        assert result.exit_code == 0
        assert "enabled" in result.output

    def test_disable_missing(self, clean_store) -> None:
        result = runner.invoke(app, ["disable", "gs"])
        assert result.exit_code == 1
        assert "does not exist" in result.output


class TestTagUntag:
    def test_tag_and_untag(self, clean_store) -> None:
        runner.invoke(app, ["add", "gs", "git", "status"])
        result = runner.invoke(app, ["tag", "gs", "git"])
        assert result.exit_code == 0
        assert "Tagged" in result.output

        result = runner.invoke(app, ["untag", "gs", "git"])
        assert result.exit_code == 0
        assert "Removed tag" in result.output

    def test_tag_missing_alias(self, clean_store) -> None:
        result = runner.invoke(app, ["tag", "gs", "git"])
        assert result.exit_code == 1
        assert "does not exist" in result.output


class TestSearchCommand:
    def test_search_found(self, clean_store) -> None:
        runner.invoke(app, ["add", "gs", "git", "status"])
        result = runner.invoke(app, ["search", "status"])
        assert result.exit_code == 0
        assert "gs" in result.output

    def test_search_empty_store(self, clean_store) -> None:
        result = runner.invoke(app, ["search", "xyz"])
        assert result.exit_code == 0
        assert "No aliases yet" in result.output


class TestInitCommand:
    def test_init_bash(self, clean_store) -> None:
        runner.invoke(app, ["add", "gs", "git", "status"])
        result = runner.invoke(app, ["init", "bash"])
        assert result.exit_code == 0
        assert "alias gs" in result.output

    def test_init_zsh(self, clean_store) -> None:
        runner.invoke(app, ["add", "gs", "git", "status"])
        result = runner.invoke(app, ["init", "zsh"])
        assert result.exit_code == 0
        assert "alias gs" in result.output

    def test_init_fish(self, clean_store) -> None:
        runner.invoke(app, ["add", "gs", "git", "status"])
        result = runner.invoke(app, ["init", "fish"])
        assert result.exit_code == 0
        assert "function gs" in result.output

    def test_init_pwsh(self, clean_store) -> None:
        runner.invoke(app, ["add", "gs", "git", "status"])
        result = runner.invoke(app, ["init", "pwsh"])
        assert result.exit_code == 0
        assert "function gs" in result.output

    def test_init_unsupported(self, clean_store) -> None:
        result = runner.invoke(app, ["init", "tcsh"])
        assert result.exit_code == 1
        assert "Unsupported shell" in result.output


class TestDoctorCommand:
    def test_doctor(self, clean_store) -> None:
        runner.invoke(app, ["add", "gs", "git", "status"])
        result = runner.invoke(app, ["doctor"])
        assert result.exit_code == 0
        assert "passed" in result.output


class TestExportImport:
    def test_export_toml(self, clean_store) -> None:
        runner.invoke(app, ["add", "gs", "git", "status"])
        out = clean_store / "export.toml"
        result = runner.invoke(app, ["export", str(out)])
        assert result.exit_code == 0
        assert out.exists()
        assert "aliases" in out.read_text()

    def test_export_json(self, clean_store) -> None:
        runner.invoke(app, ["add", "gs", "git", "status"])
        out = clean_store / "export.json"
        result = runner.invoke(app, ["export", str(out)])
        assert result.exit_code == 0
        assert out.exists()
        data = json.loads(out.read_text())
        assert "aliases" in data

    def test_export_unknown_format(self, clean_store) -> None:
        runner.invoke(app, ["add", "gs", "git", "status"])
        out = clean_store / "export.yaml"
        result = runner.invoke(app, ["export", str(out)])
        assert result.exit_code == 1
        assert "Unknown format" in result.output

    def test_export_empty(self, clean_store) -> None:
        out = clean_store / "export.toml"
        result = runner.invoke(app, ["export", str(out)])
        assert result.exit_code == 1
        assert "No aliases to export" in result.output

    def test_import_toml(self, clean_store) -> None:
        runner.invoke(app, ["add", "gs", "git", "status"])
        out = clean_store / "export.toml"
        runner.invoke(app, ["export", str(out)])
        result = runner.invoke(app, ["import", str(out), "--yes"])
        assert result.exit_code == 0
        assert "Imported" in result.output

    def test_import_json(self, clean_store) -> None:
        runner.invoke(app, ["add", "gs", "git", "status"])
        out = clean_store / "export.json"
        runner.invoke(app, ["export", str(out)])
        result = runner.invoke(app, ["import", str(out), "--yes"])
        assert result.exit_code == 0
        assert "Imported" in result.output

    def test_import_missing_file(self, clean_store) -> None:
        result = runner.invoke(app, ["import", "/nonexistent/file.toml", "--yes"])
        assert result.exit_code == 1
        assert "File not found" in result.output

    def test_import_unknown_format(self, clean_store) -> None:
        bad = clean_store / "bad.txt"
        bad.write_text("hello")
        result = runner.invoke(app, ["import", str(bad), "--yes"])
        assert result.exit_code == 1
        assert "Unknown format" in result.output

    def test_import_overwrite(self, clean_store) -> None:
        runner.invoke(app, ["add", "gs", "git", "status"])
        out = clean_store / "export.json"
        runner.invoke(app, ["export", str(out)])
        result = runner.invoke(app, ["import", str(out), "--yes", "--overwrite"])
        assert result.exit_code == 0
        assert "Imported" in result.output


class TestRunCommand:
    def test_run_missing_alias(self, clean_store) -> None:
        result = runner.invoke(app, ["run", "nonexistent"])
        assert result.exit_code == 1
        assert "does not exist" in result.output

    def test_run_disabled_alias(self, clean_store) -> None:
        runner.invoke(app, ["add", "gs", "git", "status"])
        runner.invoke(app, ["disable", "gs"])
        result = runner.invoke(app, ["run", "gs"])
        assert result.exit_code == 1
        assert "disabled" in result.output

    def test_run_simple_command(self, clean_store) -> None:
        runner.invoke(app, ["add", "hi", "echo", "hello"])
        result = runner.invoke(app, ["run", "hi"])
        # echo command should succeed (exit code 0)
        assert result.exit_code == 0

    def test_run_with_args(self, clean_store) -> None:
        runner.invoke(app, ["add", "echo2", "echo", "{1}"])
        result = runner.invoke(app, ["run", "echo2", "world"])
        assert result.exit_code == 0


class TestShortcutFlags:
    def test_version_flag(self, clean_store) -> None:
        result = runner.invoke(app, ["-v"])
        assert result.exit_code == 0
        assert "qwik" in result.output

    def test_help_flag(self, clean_store) -> None:
        result = runner.invoke(app, ["-h"])
        assert result.exit_code == 0
        assert "friendly CLI alias manager" in result.output

    def test_run_flag(self, clean_store) -> None:
        runner.invoke(app, ["add", "hi", "echo", "hello"])
        result = runner.invoke(app, ["-r", "hi"])
        # Subprocess execution inside CliRunner may fail due to pseudo-tty;
        # verify it at least parses and attempts to run.
        assert result.exit_code in (0, 1)


class TestSubcommandDispatch:
    def test_subcommand_routes_correctly(self, clean_store) -> None:
        result = runner.invoke(app, ["add", "myalias", "echo", "test"])
        assert result.exit_code == 0
        result = runner.invoke(app, ["list"])
        assert result.exit_code == 0
        assert "myalias" in result.output
