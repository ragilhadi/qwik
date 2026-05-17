"""Interactive fuzzy picker using ``prompt_toolkit`` + ``rapidfuzz``."""

from __future__ import annotations

from typing import TYPE_CHECKING

from prompt_toolkit import Application
from prompt_toolkit.buffer import Buffer
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import (
    HSplit,
    Layout,
    Window,
)
from prompt_toolkit.layout.controls import BufferControl, FormattedTextControl
from prompt_toolkit.layout.dimension import Dimension
from prompt_toolkit.styles import Style as PTStyle

from qwik.core.search import search_aliases
from qwik.ui.theme import get_console

if TYPE_CHECKING:
    from qwik.core.models import AliasStore

__all__ = ["run_picker"]


def _get_result_lines(results, selected_index):
    lines = []
    for idx, (name, alias, _score) in enumerate(results):
        prefix = "▶ " if idx == selected_index else "  "
        style = "bold" if idx == selected_index else ""
        cmd = alias.command[:40]
        lines.append((f"{style}" if style else "", f"{prefix}{name:<12} {cmd}\n"))
    if not results:
        lines.append(("dim", "  (no matches)\n"))
    return lines


def _get_preview_lines(results, selected_index):
    if not results or selected_index >= len(results):
        return [("dim", "  (no selection)\n")]
    name, alias, _ = results[selected_index]
    return [
        ("bold", f"  Name: {name}\n"),
        ("", f"  Cmd:  {alias.command}\n"),
        ("", f"  Tag:  {', '.join(alias.tag) or '—'}\n"),
        ("", f"  Used: {alias.run_count} times\n"),
    ]


class _PickerState:
    def __init__(self) -> None:
        self.selected_index: int = 0
        self.results: list[tuple[str, object, float]] = []
        self.selected_name: str | None = None


def _bind_keys(
    kb: KeyBindings,
    state: _PickerState,
    result_window: Window,
    preview_window: Window,
) -> None:
    @kb.add("up")
    def _up(event) -> None:  # type: ignore[no-untyped-def]
        if state.results:
            state.selected_index = max(0, state.selected_index - 1)
            result_window.content = FormattedTextControl(
                lambda: _get_result_lines(state.results, state.selected_index)
            )
            preview_window.content = FormattedTextControl(
                lambda: _get_preview_lines(state.results, state.selected_index)
            )

    @kb.add("down")
    def _down(event) -> None:  # type: ignore[no-untyped-def]
        if state.results:
            state.selected_index = min(len(state.results) - 1, state.selected_index + 1)
            result_window.content = FormattedTextControl(
                lambda: _get_result_lines(state.results, state.selected_index)
            )
            preview_window.content = FormattedTextControl(
                lambda: _get_preview_lines(state.results, state.selected_index)
            )

    @kb.add("enter")
    def _enter(event) -> None:  # type: ignore[no-untyped-def]
        if state.results and state.selected_index < len(state.results):
            state.selected_name = state.results[state.selected_index][0]
            event.app.exit()

    @kb.add("c-c")
    @kb.add("escape")
    def _cancel(event) -> None:  # type: ignore[no-untyped-def]
        event.app.exit()

    @kb.add("c-e")
    def _edit(event) -> None:  # type: ignore[no-untyped-def]
        if state.results and state.selected_index < len(state.results):
            state.selected_name = f"__edit__:{state.results[state.selected_index][0]}"
            event.app.exit()

    @kb.add("c-d")
    def _delete(event) -> None:  # type: ignore[no-untyped-def]
        if state.results and state.selected_index < len(state.results):
            state.selected_name = f"__delete__:{state.results[state.selected_index][0]}"
            event.app.exit()


def run_picker(store: "AliasStore") -> str | None:
    """Run the interactive fuzzy picker and return the selected alias name.

    Args:
        store: The alias database.

    Returns:
        The chosen alias name, or ``None`` if the user cancelled.
    """
    if not store.aliases:
        get_console().print(
            "[qwik.error]No aliases found. Run `qwik add` first.[/qwik.error]"
        )
        return None

    kb = KeyBindings()
    state = _PickerState()

    result_window = Window(
        content=FormattedTextControl(
            lambda: _get_result_lines(state.results, state.selected_index)
        ),
        height=Dimension(max=10),
        wrap_lines=False,
    )
    preview_window = Window(
        content=FormattedTextControl(
            lambda: _get_preview_lines(state.results, state.selected_index)
        ),
        height=Dimension(min=4, max=8),
        wrap_lines=False,
    )

    _bind_keys(kb, state, result_window, preview_window)

    input_buffer = Buffer(
        on_text_changed=lambda buf: _refresh(
            store, state, result_window, preview_window, buf.text
        ),
        multiline=False,
    )

    layout = Layout(
        HSplit(
            [
                Window(
                    height=1,
                    content=FormattedTextControl(
                        [("bold", "qwik pick — type to filter")]
                    ),
                ),
                Window(height=1, char="─"),
                Window(height=1, content=BufferControl(buffer=input_buffer)),
                Window(height=1, char="─"),
                result_window,
                Window(height=1, char="─"),
                Window(height=1, content=FormattedTextControl([("dim", "Preview:")])),
                preview_window,
                Window(
                    height=1,
                    content=FormattedTextControl(
                        [
                            (
                                "dim",
                                "↑↓ navigate  Enter run  Ctrl-E edit  Ctrl-D delete  Esc cancel",
                            )
                        ]
                    ),
                ),
            ]
        )
    )

    style = PTStyle.from_dict(
        {
            "": "#ffffff",
            "bold": "bold #ffffff",
            "dim": "#666666",
        }
    )

    app = Application(layout=layout, key_bindings=kb, style=style, full_screen=False)
    _refresh(store, state, result_window, preview_window, "")
    app.run()

    return state.selected_name


def _refresh(store, state, result_window, preview_window, query):
    state.results = search_aliases(store, query, limit=50)
    state.selected_index = 0
    result_window.content = FormattedTextControl(
        lambda: _get_result_lines(state.results, state.selected_index)
    )
    preview_window.content = FormattedTextControl(
        lambda: _get_preview_lines(state.results, state.selected_index)
    )
