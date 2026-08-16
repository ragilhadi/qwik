"""``qwik edit`` — open alias in ``$EDITOR``."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import tomlkit
import typer
from pydantic import ValidationError
from tomlkit.exceptions import ParseError as TOMLDecodeError

from qwik.core.models import Alias
from qwik.core.store import get_store
from qwik.ui.prompts import print_error, print_success
from qwik.ui.theme import get_console

__all__ = ["edit_command", "edit_alias"]

# Fields the user may edit through the snippet. Everything else on `Alias`
# (created_at, updated_at, last_used, run_count) is preserved structurally
# from the freshly loaded alias rather than round-tripped through the
# editor, since a future field added to the model must stay safe by
# default without this command needing to know about it.
_EDITABLE_FIELDS = ("command", "tag", "group", "description", "enabled")


def edit_command(
    name: str = typer.Argument(..., help="Alias name to edit."),
) -> None:
    """Open the alias entry in ``$EDITOR`` as an editable TOML snippet."""
    edit_alias(name)


def edit_alias(name: str) -> None:
    """Open *name*'s entry in ``$EDITOR``; the logic behind ``edit_command``.

    A plain function taking real values rather than ``typer.Argument``
    defaults, so callers other than Click — the picker's Ctrl+E binding —
    can invoke it directly instead of going through a CLI-testing shim.

    Args:
        name: Alias identifier to edit.
    """
    store = get_store()
    data = store.load()
    console = get_console()

    if name in data.overlay_aliases and name not in data.aliases:
        print_error(
            f"'{name}' is an overlay alias (read-only). "
            f"Copy it first: qwik overlay copy --name {name}",
            console=console,
        )
        raise typer.Exit(1)

    alias = data.get(name)
    if alias is None:
        print_error(f'Alias "{name}" does not exist.', console=console)
        raise typer.Exit(1)

    default_editor = "notepad" if sys.platform == "win32" else "vi"
    editor = (
        os.environ.get("EDITOR")
        or os.environ.get("VISUAL")
        or default_editor
    )

    doc = tomlkit.document()
    doc.add(tomlkit.comment(f'Edit the fields below and save/quit to apply changes to "{name}"'))
    doc.add("command", alias.command)
    doc.add("tag", list(alias.tag))
    doc.add("group", alias.group or "")
    doc.add("description", alias.description)
    doc.add("enabled", alias.enabled)
    snippet = tomlkit.dumps(doc)

    with tempfile.NamedTemporaryFile(
        mode="w+", suffix=".toml", delete=False, encoding="utf-8"
    ) as tmp:
        tmp.write(snippet)
        tmp_path = Path(tmp.name)

    try:
        subprocess.run([editor, str(tmp_path)], check=True)
        edited_text = tmp_path.read_text(encoding="utf-8")
        try:
            parsed = tomlkit.parse(edited_text).unwrap()
        except TOMLDecodeError as exc:
            print_error(f"Could not parse edited snippet: {exc}", console=console)
            raise typer.Exit(1)

        update: dict[str, object] = {
            key: parsed[key] for key in _EDITABLE_FIELDS if key in parsed
        }
        if "group" in update and not str(update["group"]).strip():
            update["group"] = None
        update["updated_at"] = datetime.now(timezone.utc)

        # $EDITOR already ran (a blocking, potentially long, external
        # process) above, outside any lock. Re-acquire the lock and reload
        # now, immediately before writing, so a concurrent mutation to this
        # or any other alias made while the editor was open isn't clobbered.
        with store.mutate() as fresh_data:
            fresh_alias = fresh_data.get(name)
            if fresh_alias is None:
                print_error(f'Alias "{name}" no longer exists.', console=console)
                raise typer.Exit(1)
            merged = fresh_alias.model_dump()
            merged.update(update)
            try:
                fresh_data.aliases[name] = Alias.model_validate(merged)
            except ValidationError as exc:
                print_error(f"Invalid edit: {exc}", console=console)
                raise typer.Exit(1)
        print_success(f'Updated "{name}".', console=console)
    except subprocess.CalledProcessError as exc:
        print_error(f"Editor exited with code {exc.returncode}.", console=console)
        raise typer.Exit(1)
    except FileNotFoundError:
        print_error(
            f"Editor {editor!r} not found.",
            suggestion="Set $EDITOR or $VISUAL to an installed editor.",
            console=console,
        )
        raise typer.Exit(1)
    except OSError as exc:
        print_error(f"Could not launch editor {editor!r}: {exc}", console=console)
        raise typer.Exit(1)
    finally:
        tmp_path.unlink(missing_ok=True)
