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

    # State
    selected_index = 0
    results: list[tuple[str, object, float]] = []
    selected_name: str | None = None
    cancelled = False

    def refresh(query: str) -> None:
        nonlocal results, selected_index
        results = search_aliases(store, query, limit=50)
        selected_index = 0
        result_window.content = FormattedTextControl(get_result_text)
        preview_window.content = FormattedTextControl(get_preview_text)

    def get_result_text() -> list:
        lines: list = []
        for idx, (name, alias, score) in enumerate(results):
            prefix = "▶ " if idx == selected_index else "  "
            style = "bold" if idx == selected_index else ""
            cmd = alias.command[:40]
            lines.append((f"{style}" if style else "", f"{prefix}{name:<12} {cmd}\n"))
        if not results:
            lines.append(("dim", "  (no matches)\n"))
        return lines

    def get_preview_text() -> list:
        if not results or selected_index >= len(results):
            return [("dim", "  (no selection)\n")]
        name, alias, _ = results[selected_index]
        lines = [
            ("bold", f"  Name: {name}\n"),
            ("", f"  Cmd:  {alias.command}\n"),
            ("", f"  Tag:  {', '.join(alias.tag) or '—'}\n"),
            ("", f"  Used: {alias.run_count} times\n"),
        ]
        return lines

    # Buffers
    input_buffer = Buffer(
        on_text_changed=lambda buf: refresh(buf.text),
        multiline=False,
    )

    # Windows
    result_window = Window(
        content=FormattedTextControl(get_result_text),
        height=Dimension(max=10),
        wrap_lines=False,
    )
    preview_window = Window(
        content=FormattedTextControl(get_preview_text),
        height=Dimension(min=4, max=8),
        wrap_lines=False,
    )

    @kb.add("up")
    def _up(event) -> None:  # type: ignore[no-untyped-def]
        nonlocal selected_index
        if results:
            selected_index = max(0, selected_index - 1)
            result_window.content = FormattedTextControl(get_result_text)
            preview_window.content = FormattedTextControl(get_preview_text)

    @kb.add("down")
    def _down(event) -> None:  # type: ignore[no-untyped-def]
        nonlocal selected_index
        if results:
            selected_index = min(len(results) - 1, selected_index + 1)
            result_window.content = FormattedTextControl(get_result_text)
            preview_window.content = FormattedTextControl(get_preview_text)

    @kb.add("enter")
    def _enter(event) -> None:  # type: ignore[no-untyped-def]
        nonlocal selected_name
        if results and selected_index < len(results):
            selected_name = results[selected_index][0]
            event.app.exit()

    @kb.add("c-c")
    @kb.add("escape")
    def _cancel(event) -> None:  # type: ignore[no-untyped-def]
        nonlocal cancelled
        cancelled = True
        event.app.exit()

    @kb.add("c-e")
    def _edit(event) -> None:  # type: ignore[no-untyped-def]
        nonlocal selected_name
        if results and selected_index < len(results):
            selected_name = f"__edit__:{results[selected_index][0]}"
            event.app.exit()

    @kb.add("c-d")
    def _delete(event) -> None:  # type: ignore[no-untyped-def]
        nonlocal selected_name
        if results and selected_index < len(results):
            selected_name = f"__delete__:{results[selected_index][0]}"
            event.app.exit()

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
    refresh("")
    app.run()

    if cancelled:
        return None
    return selected_name
