"""Main Typer CLI application wiring all subcommands together."""

from __future__ import annotations

import typer
from rich.console import Console

from qwik import __version__
from qwik.commands.add import add_command
from qwik.commands.doctor import doctor_command
from qwik.commands.edit import edit_command
from qwik.commands.enable_disable import disable_command, enable_command
from qwik.commands.exporter import export_command
from qwik.commands.importer import import_command
from qwik.commands.init_shell import init_shell_command
from qwik.commands.list import list_command
from qwik.commands.pick import pick_command
from qwik.commands.remove import remove_command
from qwik.commands.rename import rename_command
from qwik.commands.run import run_command
from qwik.commands.search import search_command
from qwik.commands.show import show_command
from qwik.commands.tag import tag_command, untag_command

__all__ = ["app"]


def _version_callback(value: bool) -> None:
    """Print version and exit."""
    if value:
        Console().print(f"qwik {__version__}")
        raise typer.Exit()


app = typer.Typer(
    name="qwik",
    help="A friendly CLI alias manager.",
    no_args_is_help=False,
    add_completion=True,
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
app.command("run")(run_command)
app.command("search")(search_command)
app.command("pick")(pick_command)
app.command("tag")(tag_command)
app.command("untag")(untag_command)
app.command("export")(export_command)
app.command("import")(import_command)
app.command("init")(init_shell_command)
app.command("doctor")(doctor_command)


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
) -> None:
    """Top-level callback implementing shortcut flags and bare invocation.

    When invoked with no subcommand and no flags, the fuzzy picker opens.
    """
    # If a subcommand is already being handled, do nothing.
    if ctx.invoked_subcommand is not None:
        return

    if help_flag:
        Console().print(ctx.get_help())
        raise typer.Exit()

    if list_flag:
        list_command()
        raise typer.Exit()

    if search_query is not None:
        search_command(search_query)
        raise typer.Exit()

    if run_alias is not None:
        # Need to capture remaining args after -r ... tricky in Typer callback.
        # We use sys.argv but only look at the FIRST occurrence (index 0/1 are
        # the Python/qwik executable), so alias names containing "-r" are safe
        # unless they appear before the flag.
        import sys

        # Find first occurrence in argv (after the program name)
        idx = None
        for i, arg in enumerate(sys.argv[1:], start=1):
            if arg == "-r" or arg == "--run":
                idx = i
                break
        if idx is None:
            Console().print(
                "[qwik.error]Could not locate -r in arguments.[/qwik.error]"
            )
            raise typer.Exit(1)
        remainder = sys.argv[idx + 1 :]
        if not remainder:
            Console().print("[qwik.error]Usage: qwik -r <name> [args...][/qwik.error]")
            raise typer.Exit(1)
        name = remainder[0]
        args = remainder[1:]
        run_command(name, args)
        raise typer.Exit()

    # Bare invocation → fuzzy picker
    pick_command()
