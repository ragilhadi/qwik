import pytest
from prompt_toolkit.input import create_pipe_input
from prompt_toolkit.output import DummyOutput

from qwik.core.models import Alias, AliasStore
from qwik.ui.picker import run_picker, _build_style


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
    assert result in ("gco", "gp", "gs")


def test_picker_filters_and_selects(store_with_aliases):
    with create_pipe_input() as inp:
        inp.send_text("gco\r")
        result = run_picker(store_with_aliases, input_=inp, output=DummyOutput())
    assert result == "gco"


def test_picker_escape_cancels(store_with_aliases):
    with create_pipe_input() as inp:
        inp.send_text("\x1b")
        result = run_picker(store_with_aliases, input_=inp, output=DummyOutput())
    assert result is None


def test_picker_ctrl_e_edits(store_with_aliases):
    with create_pipe_input() as inp:
        inp.send_text("\x05")
        result = run_picker(store_with_aliases, input_=inp, output=DummyOutput())
    assert result is not None and result.startswith("__edit__:")


def test_picker_ctrl_d_deletes(store_with_aliases):
    with create_pipe_input() as inp:
        inp.send_text("\x04")
        result = run_picker(store_with_aliases, input_=inp, output=DummyOutput())
    assert result is not None and result.startswith("__delete__:")


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
