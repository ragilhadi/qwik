import pytest
from prompt_toolkit.input import create_pipe_input
from prompt_toolkit.output import DummyOutput

from qwik.core.models import Alias, AliasStore
from qwik.ui.picker import PickerAction, PickerResult, run_picker, _build_style


@pytest.fixture
def store_with_aliases():
    s = AliasStore()
    s.add("gs", Alias(command="git status"))
    s.add("gco", Alias(command="git checkout {1}"))
    s.add("gp", Alias(command="git push"))
    return s


def test_picker_selects_first(store_with_aliases):
    with create_pipe_input() as inp:
        inp.send_text("\r")
        result = run_picker(store_with_aliases, input_=inp, output=DummyOutput())
    assert result is not None
    assert result.action is PickerAction.RUN
    assert result.name in ("gco", "gp", "gs")


def test_picker_filters_and_selects(store_with_aliases):
    with create_pipe_input() as inp:
        inp.send_text("gco\r")
        result = run_picker(store_with_aliases, input_=inp, output=DummyOutput())
    assert result == PickerResult(PickerAction.RUN, "gco")


def test_picker_escape_cancels(store_with_aliases):
    with create_pipe_input() as inp:
        inp.send_text("\x1b")
        result = run_picker(store_with_aliases, input_=inp, output=DummyOutput())
    assert result is None


def test_picker_ctrl_e_edits(store_with_aliases):
    with create_pipe_input() as inp:
        inp.send_text("\x05")
        result = run_picker(store_with_aliases, input_=inp, output=DummyOutput())
    assert result is not None
    assert result.action is PickerAction.EDIT


def test_picker_ctrl_d_deletes(store_with_aliases):
    with create_pipe_input() as inp:
        inp.send_text("\x04")
        result = run_picker(store_with_aliases, input_=inp, output=DummyOutput())
    assert result is not None
    assert result.action is PickerAction.DELETE


def test_picker_style_respects_no_color(monkeypatch):
    monkeypatch.setenv("NO_COLOR", "1")
    style = _build_style()
    rules = dict(style.style_rules)
    assert rules.get("") == ""
    assert rules.get("dim") == ""


def test_picker_result_lines_snapshot(store_with_aliases, snapshot):
    from qwik.ui.picker import _get_result_lines
    from qwik.core.search import search_aliases
    results = search_aliases(store_with_aliases, "", limit=50)
    lines = _get_result_lines(results, 0)
    assert lines == snapshot


def test_picker_ctrl_r_toggles_history(store_with_aliases):
    from qwik.core.models import Alias
    import datetime as dt

    store_with_aliases.aliases["gs"].last_used = dt.datetime.now(dt.timezone.utc)
    with create_pipe_input() as inp:
        inp.send_text("\x12\r")
        result = run_picker(store_with_aliases, input_=inp, output=DummyOutput())
    assert result is not None


def test_preview_shows_all_fields(store_with_aliases):
    from qwik.core.models import Alias
    from qwik.ui.picker import _get_preview_lines

    store_with_aliases.add("full", Alias(
        command="git status",
        tag=["vcs"],
        group="git",
        description="Show working tree status",
    ))
    results = [("full", store_with_aliases.aliases["full"], 1.0)]
    lines = _get_preview_lines(results, 0)
    text = "".join(s for _, s in lines)
    assert "Name:" in text
    assert "Cmd:" in text
    assert "Group:" in text
    assert "Tag:" in text
    assert "Used:" in text
    assert "Desc:" in text


def test_picker_preserves_selection(store_with_aliases):
    with create_pipe_input() as inp:
        inp.send_text("\x1b[B\r")
        result = run_picker(store_with_aliases, input_=inp, output=DummyOutput())
    assert result is not None


class TestPickCommandEditDelete:
    """`pick_command`'s handling of the picker's Ctrl+E/Ctrl+D result.

    Regression: this used to re-enter the CLI via
    typer.testing.CliRunner, a test harness that replaces stdin with an
    empty stream — so Ctrl+D's confirmation prompt hit EOF and Click
    aborted, leaving the alias in place despite the picker reporting
    success. `run_picker` (driven through prompt_toolkit's pipe input
    above) is monkeypatched here to isolate pick_command's own wiring:
    does it call the real edit_alias/remove_alias and does the store
    actually change.
    """

    @staticmethod
    def _setup(tmp_path, monkeypatch):
        from qwik.config import _reset_config

        monkeypatch.setenv("QWIK_CONFIG_DIR", str(tmp_path))
        _reset_config()
        from typer.testing import CliRunner

        from qwik.cli import app

        CliRunner().invoke(app, ["add", "doomed", "echo", "doomed"])

    def test_ctrl_d_deletes_with_real_confirmation(self, tmp_path, monkeypatch):
        self._setup(tmp_path, monkeypatch)
        import qwik.commands.pick as pick_mod
        from qwik.ui.picker import PickerAction, PickerResult

        monkeypatch.setattr(
            pick_mod, "run_picker",
            lambda data: PickerResult(PickerAction.DELETE, "doomed"),
        )
        monkeypatch.setattr(
            "qwik.commands.remove.prompt_confirm", lambda *a, **k: True
        )

        import typer

        with pytest.raises(typer.Exit) as exc:
            pick_mod.pick_command()
        assert exc.value.exit_code == 0

        from qwik.core.store import get_store

        assert get_store().load().get("doomed") is None

    def test_ctrl_d_declined_keeps_alias(self, tmp_path, monkeypatch):
        self._setup(tmp_path, monkeypatch)
        import qwik.commands.pick as pick_mod
        from qwik.ui.picker import PickerAction, PickerResult

        monkeypatch.setattr(
            pick_mod, "run_picker",
            lambda data: PickerResult(PickerAction.DELETE, "doomed"),
        )
        monkeypatch.setattr(
            "qwik.commands.remove.prompt_confirm", lambda *a, **k: False
        )

        import typer

        with pytest.raises(typer.Exit):
            pick_mod.pick_command()

        from qwik.core.store import get_store

        assert get_store().load().get("doomed") is not None

    def test_ctrl_e_edits_with_real_editor(self, tmp_path, monkeypatch):
        self._setup(tmp_path, monkeypatch)
        import os
        import sys

        editor = tmp_path / "editor.sh"
        editor.write_text(
            "#!/usr/bin/env bash\n"
            'cat > "$1" <<\'EOF\'\n'
            'command = "echo edited"\ntag = []\ngroup = ""\n'
            'description = ""\nenabled = true\nEOF\n',
            encoding="utf-8",
        )
        os.chmod(editor, 0o700)
        monkeypatch.setenv("EDITOR", str(editor))

        import qwik.commands.pick as pick_mod
        from qwik.ui.picker import PickerAction, PickerResult

        monkeypatch.setattr(
            pick_mod, "run_picker",
            lambda data: PickerResult(PickerAction.EDIT, "doomed"),
        )

        import typer

        with pytest.raises(typer.Exit) as exc:
            pick_mod.pick_command()
        assert exc.value.exit_code == 0

        from qwik.core.store import get_store

        assert get_store().load().get("doomed").command == "echo edited"
