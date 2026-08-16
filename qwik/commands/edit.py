"""``qwik edit`` — open alias in ``$EDITOR``."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import typer

from qwik.core.models import Alias
from qwik.core.store import get_store
from qwik.ui.prompts import print_error, print_success
from qwik.ui.theme import get_console

__all__ = ["edit_command"]


def _strip_inline_comment(line: str) -> str:
    """Remove a \"#\" comment that is not inside quotes."""
    comment_idx = -1
    in_quote: str | None = None
    for i, ch in enumerate(line):
        if ch in ('"', "'") and (i == 0 or line[i - 1] != "\\"):
            if in_quote == ch:
                in_quote = None
            elif in_quote is None:
                in_quote = ch
        elif ch == "#" and in_quote is None:
            comment_idx = i
            break
    if comment_idx >= 0:
        line = line[:comment_idx].rstrip()
    return line


def _parse_value(raw_val: str) -> object:
    """Parse a simple TOML-like value from an edited snippet."""
    low = raw_val.lower()
    if low == "true":
        return True
    if low == "false":
        return False
    if raw_val.startswith("[") and raw_val.endswith("]"):
        inner = raw_val[1:-1]
        return [v.strip().strip("'\"").strip() for v in inner.split(",") if v.strip()]
    return raw_val.strip("'\"").strip()


def edit_command(
    name: str = typer.Argument(..., help="Alias name to edit."),
) -> None:
    """Open the alias entry in ``$EDITOR`` as an editable TOML snippet."""
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

    snippet = (
        f'# Edit the fields below and save/quit to apply changes to "{name}"\n'
        f"command = {alias.command!r}\n"
        f"tag = {alias.tag!r}\n"
        f"description = {alias.description!r}\n"
        f"enabled = {alias.enabled!r}\n"
    )

    with tempfile.NamedTemporaryFile(
        mode="w+", suffix=".toml", delete=False, encoding="utf-8"
    ) as tmp:
        tmp.write(snippet)
        tmp_path = Path(tmp.name)

    try:
        subprocess.run([editor, str(tmp_path)], check=True)
        edited_text = tmp_path.read_text(encoding="utf-8")
        # Very simple parser: extract key = value lines
        new_fields: dict[str, object] = {}
        for line in edited_text.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            line = _strip_inline_comment(line)
            if " = " not in line:
                continue
            key, raw_val = line.split(" = ", 1)
            key = key.strip()
            new_fields[key] = _parse_value(raw_val)

        # $EDITOR already ran (a blocking, potentially long, external
        # process) above, outside any lock. Re-acquire the lock and reload
        # now, immediately before writing, so a concurrent mutation to this
        # or any other alias made while the editor was open isn't clobbered.
        with store.mutate() as fresh_data:
            fresh_alias = fresh_data.get(name)
            if fresh_alias is None:
                print_error(f'Alias "{name}" no longer exists.', console=console)
                raise typer.Exit(1)
            fresh_data.aliases[name] = Alias(
                command=str(new_fields.get("command", fresh_alias.command)),
                tag=list(new_fields.get("tag", fresh_alias.tag)) or [],  # type: ignore[call-overload]
                description=str(new_fields.get("description", fresh_alias.description)),
                enabled=bool(new_fields.get("enabled", fresh_alias.enabled)),
                created_at=fresh_alias.created_at,
                updated_at=datetime.now(timezone.utc),
                last_used=fresh_alias.last_used,
                run_count=fresh_alias.run_count,
            )
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
