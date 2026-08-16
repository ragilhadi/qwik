"""Interactive fuzzy picker using ``prompt_toolkit`` + ``rapidfuzz``."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from typing import TYPE_CHECKING

from qwik.core.search import search_aliases
from qwik.ui.theme import get_console

if TYPE_CHECKING:
    # prompt_toolkit costs ~80ms to import. Every qwik invocation loads
    # this module (qwik/commands/pick.py imports it at module scope so
    # the CLI can register the `pick` command), but only an actual picker
    # session needs prompt_toolkit itself — so the real imports live
    # inside the functions that use them, and only these type-only names
    # are needed up here (erased at runtime by `from __future__ import
    # annotations`).
    from prompt_toolkit.formatted_text import StyleAndTextTuples
    from prompt_toolkit.input import Input
    from prompt_toolkit.key_binding import KeyBindings
    from prompt_toolkit.layout import Window
    from prompt_toolkit.output import Output
    from prompt_toolkit.styles import Style as PTStyle

    from qwik.core.models import Alias, AliasStore

__all__ = ["PickerAction", "PickerResult", "run_picker"]


class PickerAction(Enum):
    """What the user asked the picker to do with the selected alias."""

    RUN = "run"
    EDIT = "edit"
    DELETE = "delete"


@dataclass(frozen=True)
class PickerResult:
    """The alias name and action chosen when the picker exits.

    Replaces the previous ``"__edit__:name"`` / ``"__delete__:name"``
    string-prefix protocol, which relied on ``:`` being forbidden in
    alias names to disambiguate an action from a literal alias — fragile
    to rely on, and impossible to express in the type system.
    """

    action: PickerAction
    name: str


def _build_style() -> PTStyle:
    from prompt_toolkit.styles import Style as PTStyle

    from qwik.ui.theme import _no_color_active

    if _no_color_active():
        return PTStyle.from_dict({"": "", "bold": "bold", "dim": ""})
    return PTStyle.from_dict({"": "#ffffff", "bold": "bold #ffffff", "dim": "#666666"})


def _get_result_lines(
    results: list[tuple[str, Alias, float]], selected_index: int
) -> StyleAndTextTuples:
    lines: StyleAndTextTuples = []
    for idx, (name, alias, _score) in enumerate(results):
        prefix = "▶ " if idx == selected_index else "  "
        style = "bold" if idx == selected_index else ""
        cmd = alias.command[:40]
        lines.append((f"{style}" if style else "", f"{prefix}{name:<12} {cmd}\n"))
    if not results:
        lines.append(("dim", "  (no matches)\n"))
    return lines


def _get_preview_lines(
    results: list[tuple[str, Alias, float]], selected_index: int
) -> StyleAndTextTuples:
    if not results or selected_index >= len(results):
        return [("dim", "  (no selection)\n")]
    name, alias, _ = results[selected_index]
    lines: StyleAndTextTuples = [
        ("bold", f"  Name: {name}\n"),
        ("", f"  Cmd:  {alias.command}\n"),
        ("", f"  Group: {alias.group or '—'}\n"),
        ("", f"  Tag:  {', '.join(alias.tag) or '—'}\n"),
        ("", f"  Used: {alias.run_count} times (last: {alias.format_last_used()})\n"),
        ("", f"  Created: {alias.created_at.strftime('%Y-%m-%d')}\n"),
        ("", f"  Enabled: {'yes' if alias.enabled else 'no'}\n"),
    ]
    if alias.description:
        lines.append(("", f"  Desc:  {alias.description}\n"))
    return lines


class _PickerState:
    def __init__(self) -> None:
        self.selected_index: int = 0
        self.results: list[tuple[str, Alias, float]] = []
        self.selected_result: PickerResult | None = None
        self.history_mode: bool = False


def _bind_keys(
    kb: KeyBindings,
    store: AliasStore,
    state: _PickerState,
    result_window: Window,
    preview_window: Window,
) -> None:
    from prompt_toolkit.layout.controls import FormattedTextControl

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
            name = state.results[state.selected_index][0]
            state.selected_result = PickerResult(PickerAction.RUN, name)
            event.app.exit()

    @kb.add("c-c")
    @kb.add("escape")
    def _cancel(event) -> None:  # type: ignore[no-untyped-def]
        event.app.exit()

    @kb.add("c-e")
    def _edit(event) -> None:  # type: ignore[no-untyped-def]
        if state.results and state.selected_index < len(state.results):
            name = state.results[state.selected_index][0]
            state.selected_result = PickerResult(PickerAction.EDIT, name)
            event.app.exit()

    @kb.add("c-d")
    def _delete(event) -> None:  # type: ignore[no-untyped-def]
        if state.results and state.selected_index < len(state.results):
            name = state.results[state.selected_index][0]
            state.selected_result = PickerResult(PickerAction.DELETE, name)
            event.app.exit()

    @kb.add("c-r")
    def _toggle_history(event) -> None:  # type: ignore[no-untyped-def]
        state.history_mode = not state.history_mode
        _refresh(store, state, result_window, preview_window, "")


def run_picker(
    store: AliasStore,
    *,
    input_: Input | None = None,
    output: Output | None = None,
) -> PickerResult | None:
    """Run the interactive fuzzy picker and return the chosen action.

    Args:
        store: The alias database.

    Returns:
        A :class:`PickerResult` naming the alias and the action the user
        chose (run/edit/delete), or ``None`` if the user cancelled.
    """
    if not store.all_aliases():
        get_console().print("[qwik.error]No aliases found. Run `qwik add` first.[/qwik.error]")
        return None

    # Deferred until an interactive session is actually needed (see the
    # module-level comment above) rather than paid by every qwik invocation.
    from prompt_toolkit import Application
    from prompt_toolkit.buffer import Buffer
    from prompt_toolkit.key_binding import KeyBindings
    from prompt_toolkit.layout import HSplit, Layout, Window
    from prompt_toolkit.layout.controls import BufferControl, FormattedTextControl
    from prompt_toolkit.layout.dimension import Dimension

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

    _bind_keys(kb, store, state, result_window, preview_window)

    input_buffer = Buffer(
        on_text_changed=lambda buf: _refresh(store, state, result_window, preview_window, buf.text),
        multiline=False,
    )

    layout = Layout(
        HSplit(
            [
                Window(
                    height=1,
                    content=FormattedTextControl([("bold", "qwik pick — type to filter")]),
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
                                "↑↓ navigate  Enter run  Ctrl-E edit  Ctrl-D delete  "
                                "Ctrl-R history  Esc cancel",
                            )
                        ]
                    ),
                ),
            ]
        )
    )

    style = _build_style()

    app: Application[None] = Application(
        layout=layout,
        key_bindings=kb,
        style=style,
        full_screen=False,
        input=input_,
        output=output,
    )
    _refresh(store, state, result_window, preview_window, "")
    app.run()

    return state.selected_result


def _refresh(
    store: AliasStore,
    state: _PickerState,
    result_window: Window,
    preview_window: Window,
    query: str,
) -> None:
    from prompt_toolkit.layout.controls import FormattedTextControl

    current_name = None
    if state.results and state.selected_index < len(state.results):
        current_name = state.results[state.selected_index][0]

    state.results = search_aliases(store, query, limit=50)

    if state.history_mode:
        state.results.sort(
            key=lambda t: t[1].last_used or datetime.min.replace(tzinfo=UTC),
            reverse=True,
        )

    if current_name is not None:
        for i, (n, _, _) in enumerate(state.results):
            if n == current_name:
                state.selected_index = i
                break
        else:
            state.selected_index = 0
    else:
        state.selected_index = 0

    result_window.content = FormattedTextControl(
        lambda: _get_result_lines(state.results, state.selected_index)
    )
    preview_window.content = FormattedTextControl(
        lambda: _get_preview_lines(state.results, state.selected_index)
    )
