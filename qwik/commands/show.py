"""``qwik show`` — detailed view of one alias."""

from __future__ import annotations

import typer

from qwik.core.platform import current_platform
from qwik.core.shell_detect import detect_shell
from qwik.core.store import get_store
from qwik.ui.prompts import print_error
from qwik.ui.tables import render_alias_detail
from qwik.ui.theme import get_console

__all__ = ["show_command"]


def show_command(
    name: str = typer.Argument(..., help="Alias name to inspect."),
) -> None:
    """Display detailed metadata for a single alias."""
    store = get_store()
    data = store.load()
    console = get_console()

    alias = data.get(name)
    if alias is None:
        # Overlay aliases are read-only layers the user store doesn't
        # own; show still displays them with provenance.
        if name in data.overlay_aliases:
            alias = data.overlay_aliases[name]
            from qwik.commands.overlay import (
                _load_overlay_config,
                _load_overlay_key,
                _load_overlay_pin,
            )
            from qwik.core.overlay_manifest import load_manifest
            from qwik.ui.tables import render_alias_detail as _rad

            config = store._config
            url, _branch, _ = _load_overlay_config(config.overlay_config_file)
            from qwik.core.git import git_available, rev_parse

            commit = None
            verification = "unverified"
            manifest = load_manifest(config.overlay_repo_dir)
            if git_available():
                try:
                    commit = rev_parse(config.overlay_repo_dir, "HEAD")
                except RuntimeError:
                    commit = None
            if manifest is not None:
                from qwik.commands.overlay import _describe_verification

                verification = _describe_verification(config.overlay_repo_dir)
            pinned = _load_overlay_pin(config.overlay_config_file)
            key = _load_overlay_key(config.overlay_config_file)
            source = f"overlay {url or '?'}"
            if commit:
                source += f" @ {commit[:12]}"
            table = _rad(name, alias, platform=current_platform(), shell=detect_shell())
            from rich.table import Table as _T

            extra = _T(title="Overlay provenance")
            extra.add_column("Field")
            extra.add_column("Value")

            extra.add_row("Source", source)
            extra.add_row("Signature", verification)
            if pinned:
                extra.add_row("Pinned", pinned)
            if key:
                extra.add_row("Pinned key", key[:48] + ("…" if len(key) > 48 else ""))
            if manifest is not None:
                extra.add_row("Maintainer", manifest.maintainer or "—")
            console.print(table)
            console.print(extra)
            raise typer.Exit(0)
        print_error(f'Alias "{name}" does not exist.', console=console)
        raise typer.Exit(1)

    table = render_alias_detail(name, alias, platform=current_platform(), shell=detect_shell())
    console.print(table)
