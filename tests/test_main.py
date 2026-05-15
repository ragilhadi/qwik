"""Test __main__.py entry point."""

from typer.testing import CliRunner

from qwik.cli import app

runner = CliRunner()


def test_main_entrypoint() -> None:
    """``python -m qwik`` should invoke the CLI app."""
    import qwik.__main__ as main_mod

    assert main_mod.app is app
