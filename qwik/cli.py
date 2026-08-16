"""Main Typer CLI application wiring all subcommands together."""

from __future__ import annotations

import logging
import os

import typer

from qwik import __version__
from qwik.commands.add import add_command
from qwik.commands.completion import completion_command
from qwik.commands.doctor import doctor_command
from qwik.commands.edit import edit_command
from qwik.commands.enable_disable import disable_command, enable_command
from qwik.commands.exporter import export_command
from qwik.commands.importer import import_command
from qwik.commands.group import group_command, ungroup_command
from qwik.commands.init_shell import init_shell_command
from qwik.commands.overlay import overlay_command
from qwik.commands.list import list_command
from qwik.commands.pick import pick_command
from qwik.commands.remove import remove_command
from qwik.commands.rename import rename_command
from qwik.commands.run import run_command
from qwik.commands.search import search_command
from qwik.commands.show import show_command
from qwik.commands.sync import sync_command
from qwik.commands.tag import tag_command, untag_command
from qwik.ui.theme import get_console

__all__ = ["app", "main_entrypoint"]


def _version_callback(value: bool) -> None:
    """Print version and exit."""
    if value:
        get_console().print(f"qwik {__version__}")
        raise typer.Exit()


app = typer.Typer(
    name="qwik",
    help="A friendly CLI alias manager.",
    no_args_is_help=False,
    add_completion=True,
    context_settings={"ignore_unknown_options": True, "allow_extra_args": True},
)

# Register subcommands
app.command("add")(add_command)
app.command("list")(list_command)
app.command("ls")(list_command)
app.command("show")(show_command)
app.command("edit")(edit_command)
app.command("rename")(rename_command)
app.command("rm")(remove_command)
app.command("enable")(enable_command)
app.command("disable")(disable_command)
app.command(
    "run",
    context_settings={"ignore_unknown_options": True},
)(run_command)
app.command("search")(search_command)
app.command("pick")(pick_command)
app.command("tag")(tag_command)
app.command("untag")(untag_command)
app.command("group")(group_command)
app.command("ungroup")(ungroup_command)
app.command("export")(export_command)
app.command("import")(import_command)
app.command("init")(init_shell_command)
app.command("doctor")(doctor_command)
app.command("completion")(completion_command)
app.command("sync")(sync_command)
app.command("overlay")(overlay_command)


def _discover_plugin_commands() -> None:
    """Register CLI commands from the ``qwik.commands`` entry-point group."""
    import importlib.metadata
    import sys

    for ep in importlib.metadata.entry_points(group="qwik.commands"):
        try:
            cmd = ep.load()
            app.command(ep.name)(cmd)
        except Exception as exc:
            print(f"Warning: failed to load plugin command {ep.name!r}: {exc}", file=sys.stderr)


_discover_plugin_commands()


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    run_alias: str | None = typer.Option(
        None,
        "--run",
        "-r",
        help="Run an alias (qwik -r <name> [args...]).",
    ),
    list_flag: bool = typer.Option(False, "--list", "-l", help="Quick list."),
    search_query: str | None = typer.Option(
        None,
        "--search",
        "-s",
        help="Quick search.",
    ),
    version: bool = typer.Option(
        False,
        "--version",
        "-v",
        help="Show version and exit.",
        callback=_version_callback,
        is_eager=True,
    ),
    help_flag: bool = typer.Option(
        False,
        "--help",
        "-h",
        help="Show this message and exit.",
        is_eager=True,
    ),
    no_color: bool = typer.Option(
        False,
        "--no-color",
        help="Disable colored output.",
    ),
) -> None:
    """Top-level callback implementing shortcut flags and bare invocation.

    When invoked with no subcommand and no flags, the fuzzy picker opens.
    """
    if os.environ.get("QWIK_DEBUG"):
        logging.basicConfig(
            level=logging.DEBUG,
            format="%(levelname)s %(name)s: %(message)s",
        )
    # Child contexts (every subcommand) inherit ctx.obj from this, the
    # top-level group context, unless they set their own — so get_console()
    # can read it back via the current Click context instead of a mutable
    # module global.
    ctx.obj = {"no_color": no_color}
    # If a subcommand is already being handled, do nothing.
    if ctx.invoked_subcommand is not None:
        return

    if help_flag:
        get_console().print(ctx.get_help())
        raise typer.Exit()

    if list_flag:
        list_command()
        raise typer.Exit()

    if search_query is not None:
        search_command(search_query)
        raise typer.Exit()

    if run_alias is not None:
        # Reached only when Click's own group parsing didn't need to treat
        # any leftover token as a subcommand name (e.g. `-r name` with no
        # extra args). The general case — extra args/flags after the alias
        # name — is intercepted earlier, in `main_entrypoint()`, because
        # Click's Group dispatch always claims the first leftover
        # positional token as a subcommand candidate and would misparse it.
        run_command(run_alias, list(ctx.args))
        raise typer.Exit()

    # Bare invocation → fuzzy picker
    pick_command()


def main_entrypoint() -> None:
    """Console-script entry point.

    Intercepts a leading ``-r``/``--run`` shortcut directly from
    ``sys.argv`` before Click parses anything. Click's ``Group`` dispatch
    always claims the first leftover positional token as a subcommand
    name, so ``qwik -r gs --short`` would otherwise have ``--short``
    misparsed as an unknown subcommand before the callback above ever
    runs. The documented shortcut form always places ``-r``/``--run``
    immediately after ``qwik``, so only that position is intercepted;
    any other placement is left to Click's normal subcommand parsing.
    """
    import sys

    argv = sys.argv[1:]
    if argv and argv[0] in ("-r", "--run"):
        remainder = argv[1:]
        if not remainder:
            get_console().print("[qwik.error]Usage: qwik -r <name> [args...][/qwik.error]")
            raise SystemExit(1)
        name, args = remainder[0], remainder[1:]
        if args and args[0] == "--":
            # Match Click's convention: a leading `--` marks end-of-options
            # and is itself dropped, not passed through as a literal arg.
            args = args[1:]
        try:
            run_command(name, args)
        except typer.Exit as exc:
            raise SystemExit(exc.exit_code) from None
        return

    app()
