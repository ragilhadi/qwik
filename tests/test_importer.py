"""Tests for the import command."""

from __future__ import annotations

from unittest.mock import patch

from typer.testing import CliRunner

from qwik.cli import app

runner = CliRunner()


class TestImportPaths:
    def test_import_merge_conflict_display(self, tmp_path, monkeypatch) -> None:
        from qwik.config import _reset_config

        monkeypatch.setenv("QWIK_CONFIG_DIR", str(tmp_path))
        _reset_config()
        runner.invoke(app, ["add", "gs", "git", "status"])
        out = tmp_path / "export.json"
        runner.invoke(app, ["export", str(out)])
        with patch("qwik.commands.importer.prompt_confirm", return_value=False):
            result = runner.invoke(app, ["import", str(out)])
            assert result.exit_code == 0
            assert "Conflicts" in result.output

    def test_import_conflict_display(self, tmp_path, monkeypatch) -> None:
        from qwik.config import _reset_config

        monkeypatch.setenv("QWIK_CONFIG_DIR", str(tmp_path))
        _reset_config()
        runner.invoke(app, ["add", "gs", "git", "status"])
        out = tmp_path / "export.json"
        runner.invoke(app, ["export", str(out)])
        with patch("qwik.commands.importer.prompt_confirm", return_value=True):
            result = runner.invoke(app, ["import", str(out)])
            assert result.exit_code == 0
            assert "Conflicts" in result.output


class TestImportSafety:
    def test_import_malformed_toml_friendly_error(self, tmp_path, monkeypatch):
        from qwik.config import _reset_config

        monkeypatch.setenv("QWIK_CONFIG_DIR", str(tmp_path))
        _reset_config()
        bad = tmp_path / "bad.toml"
        bad.write_text("not = valid = toml", encoding="utf-8")
        result = runner.invoke(app, ["import", str(bad), "--yes"])
        assert result.exit_code == 1
        assert "could not parse" in result.output.lower() or "toml" in result.output.lower()

    def test_import_shows_command_preview(self, tmp_path, monkeypatch):
        from qwik.config import _reset_config

        monkeypatch.setenv("QWIK_CONFIG_DIR", str(tmp_path))
        _reset_config()
        runner.invoke(app, ["add", "danger", "rm -rf /tmp"])
        src = tmp_path / "src.toml"
        runner.invoke(app, ["export", str(src)])
        # Wipe store so import shows everything as new and the command preview surfaces
        (tmp_path / "aliases.toml").unlink()
        _reset_config()
        result = runner.invoke(app, ["import", str(src)], input="n\n")
        assert "rm -rf /tmp" in result.output
        assert result.exit_code == 0  # declined → exit 0


class TestImportOverwritePreview:
    def test_import_overwrite_shows_preview_and_confirms(self, tmp_path, monkeypatch) -> None:
        from qwik.config import _reset_config

        monkeypatch.setenv("QWIK_CONFIG_DIR", str(tmp_path))
        _reset_config()
        runner.invoke(app, ["add", "keep", "echo keep"])
        hostile = tmp_path / "hostile.toml"
        # Build an incoming file with a hostile command
        import tomlkit

        doc = tomlkit.document()
        doc.add("version", 1)
        aliases = tomlkit.table()
        t = tomlkit.table()
        t.add("command", "rm -rf /tmp")
        aliases.add("danger", t)
        doc.add("aliases", aliases)
        hostile.write_text(tomlkit.dumps(doc), encoding="utf-8")

        with patch("qwik.commands.importer.prompt_confirm", return_value=False) as declined:
            result = runner.invoke(app, ["import", str(hostile), "--overwrite"])
            assert declined.called
            assert result.exit_code == 0
            assert "trust" in result.output.lower() or "shell=True" in result.output.lower()
            assert "rm -rf /tmp" in result.output
            live = tomlkit.parse((tmp_path / "aliases.toml").read_text(encoding="utf-8"))
            assert "danger" not in live["aliases"].unwrap()  # type: ignore[attr-defined]
            assert "keep" in live["aliases"].unwrap()  # type: ignore[attr-defined]

        with patch("qwik.commands.importer.prompt_confirm", return_value=True) as confirmed:
            result = runner.invoke(app, ["import", str(hostile), "--overwrite"])
            assert confirmed.called
            assert result.exit_code == 0, result.output
            live = tomlkit.parse((tmp_path / "aliases.toml").read_text(encoding="utf-8"))
            assert "danger" in live["aliases"].unwrap()  # type: ignore[attr-defined]
            assert "keep" not in live["aliases"].unwrap()  # type: ignore[attr-defined]

    def test_import_overwrite_yes_shows_warning(self, tmp_path, monkeypatch) -> None:
        from qwik.config import _reset_config

        monkeypatch.setenv("QWIK_CONFIG_DIR", str(tmp_path))
        _reset_config()
        runner.invoke(app, ["add", "keep", "echo keep"])
        import tomlkit

        hostile = tmp_path / "h.toml"
        doc = tomlkit.document()
        doc.add("version", 1)
        aliases = tomlkit.table()
        t = tomlkit.table()
        t.add("command", "rm -rf /tmp")
        aliases.add("danger", t)
        doc.add("aliases", aliases)
        hostile.write_text(tomlkit.dumps(doc), encoding="utf-8")
        result = runner.invoke(app, ["import", str(hostile), "--overwrite", "--yes"])
        assert result.exit_code == 0, result.output
        assert "trust" in result.output.lower() or "shell=True" in result.output.lower()
        live = tomlkit.parse((tmp_path / "aliases.toml").read_text(encoding="utf-8"))
        assert "danger" in live["aliases"].unwrap()  # type: ignore[attr-defined]
