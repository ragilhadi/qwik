"""Native template rendering (``render_native`` + per-renderer opt-in).

Three layers of guarantees are pinned here:

1. **Structure.** The exact compiled syntax per shell, so a mapping
   regression is a readable diff, not a behaviour change discovered in
   production.

2. **Differential parity.** For every (command, argv) corpus entry, the
   natively rendered alias — defining a real function in a real shell with
   the real argument list — must hand the child program the same ``argv``
   that ``expand()`` + shell execution hands it (exactly what ``qwik run``
   does).  The corpus includes spaced, quoted, and metacharacter-bearing
   arguments plus empty/missing edge cases.

3. **Fallback safety.** Constructs whose native translation would change
   the alias's meaning (placeholders inside single quotes) or that the
   engine deliberately excludes (cmd, nu, xonsh) keep the ``qwik run``
   wrapper, byte-identical to what it emitted before native rendering.

Known, corpus-excluded divergence: a *missing* positional renders as a
dropped word on the list-semantics shells (fish/pwsh evaluate
``$argv[1]``/``$args[0]`` to nothing) but as a literal empty string under
``expand()`` (an in-place ``""`` word).  bash/zsh agree with ``expand()``
word-for-word, so missing positional cases run there; the corpus generator
skips them on fish/pwsh.  pwsh additionally has no local binary on most
dev/CI-linux images — its differential leg runs on the windows job.
"""

from __future__ import annotations

import shlex
import shutil
import subprocess
import sys
from typing import TYPE_CHECKING

import pytest

from qwik.core.models import Alias
from qwik.core.substitute import (
    expand,
    has_placeholders,
    native_template_capable,
    render_native,
)
from qwik.shells.base import get_renderer, supported_shells

if TYPE_CHECKING:
    from collections.abc import Iterator

# ---------------------------------------------------------------------------
# Structure pins
# ---------------------------------------------------------------------------

_STRUCTURE_CASES = [
    ("bash", "git checkout {1}", 'git checkout "${1-}" "${@:2}"'),
    ("zsh", "git checkout {1}", 'git checkout "${1-}" "${@:2}"'),
    (
        "fish",
        "git checkout {1}",
        "git checkout (string collect -- $argv[1]) (string collect -- $argv[2..-1])",
    ),
    ("pwsh", "git checkout {1}", None),  # surplus tail unexpressible; wrapper
    ("bash", "echo {1} {@}", 'echo "${1-}" "$@"'),  # {@} carries every arg: no tail
    ("fish", "echo {1} {@}", "echo (string collect -- $argv[1]) (string collect -- $argv)"),
    ("pwsh", "echo {1} {@}", "echo $args[0] @args"),  # expand duplicates too
    ("bash", "echo {2} {1}", 'echo "${2-}" "${1-}" "${@:3}"'),
    (
        "fish",
        "echo {2} {1}",
        "echo (string collect -- $argv[2]) (string collect -- $argv[1])"
        " (string collect -- $argv[3..-1])",
    ),
    ("pwsh", "echo {*}", None),  # no scalar join; wrapper
    ("bash", "echo {*}", 'echo "$*"'),  # {*} carries every arg: no tail
    # pwsh's native set is exactly the pure-{@} templates: @args splats all
    # arguments like expand()'s {@}; positional refs can't get a surplus tail.
    ("pwsh", "{@}", "@args"),
    ("pwsh", "echo {@}", "echo @args"),
    ("bash", "config {1:-main}", 'config "${1:-main}" "${@:2}"'),
    (
        "fish",
        "config {1:-main}",
        "config (if count $argv > 0; string collect -- $argv[1]; else;"
        ' string collect -- "main"; end) (string collect -- $argv[2..-1])',
    ),
    ("bash", "checkout {branch}", 'checkout "${1-}" "${@:2}"'),
    # Whole-word double quotes: the ref inherits the command's own quotes.
    ("bash", '"{1}"', '"${1-}" "${@:2}"'),
    # Composite double-quoted word: expand() quotes the value at runtime,
    # native splicing splits differently for spaced values — wrapper.
    ("bash", 'echo "p={1}"', None),
]


@pytest.mark.parametrize(("shell", "command", "expected"), _STRUCTURE_CASES)
def test_render_native_structure(shell: str, command: str, expected: str | None) -> None:
    assert render_native(command, shell) == expected


def test_render_native_rejects_placeholder_in_single_quotes() -> None:
    """A placeholder inside single quotes must keep the wrapper: the shell
    treats '<native ref>' as literal text while `qwik run` interpolates it —
    compiling would silently change the alias.
    """
    assert render_native("'branch is {1}'", "bash") is None
    assert render_native("echo 'keep {1} literal'", "zsh") is None
    # The single-quote detector and the composite-double-quote guard are
    # both conservative over-approximations (documented in native_safe).
    assert render_native("echo 'plain' {1}", "bash") == 'echo \'plain\' "${1-}" "${@:2}"'


def test_render_native_rejects_unsupported_shells() -> None:
    for shell in ("cmd", "nu", "xonsh", "unknown", ""):
        assert render_native("git checkout {1}", shell) is None


def test_render_native_rejects_zero_placeholder() -> None:
    with pytest.raises(ValueError):
        render_native("git checkout {0}", "bash")


def test_no_native_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    """QWIK_NO_NATIVE=1 forces every shell back onto the wrapper."""
    monkeypatch.setenv("QWIK_NO_NATIVE", "1")
    assert not native_template_capable("bash")
    assert render_native("git checkout {1}", "bash") is None
    out = get_renderer("bash").render_alias("gco", Alias(command="git checkout {1}"))
    assert out == 'gco() {\n    qwik run "gco" "$@"\n}'


def test_capability_flag_matches_engine_exclusions() -> None:
    """supports_native_templates means *attempts* native compilation; the
    engine may still refuse specific templates (surplus tail on pwsh,
    single quotes, composites) — the renderer then emits the wrapper."""
    for shell in supported_shells():
        renderer = get_renderer(shell)
        native = render_native("{@}", shell)
        if renderer.supports_native_templates:
            assert native is not None, shell
        else:
            assert native is None, shell


def test_wrapper_unchanged_for_excluded_shells() -> None:
    """cmd / nu / xonsh emit exactly what they did before native rendering."""
    assert (
        get_renderer("cmd").render_alias("g", Alias(command="x {1}"))
        == "REM omitted g: template mode unsupported in cmd"
    )
    assert (
        get_renderer("nu").render_alias("g", Alias(command="x {1}"))
        == 'def g [...args] {\n    qwik run "g" ...$args\n}'
    )
    assert (
        get_renderer("xonsh").render_alias("g", Alias(command="x {1}"))
        == 'aliases["g"] = ["qwik", "run", "g"]'
    )


# ---------------------------------------------------------------------------
# Differential parity: native execution vs expand() + shell, real shells.
# ---------------------------------------------------------------------------

_DIFFERENTIAL_SHELLS = [s for s in ("bash", "zsh", "fish", "pwsh") if shutil.which(s)]

_ARGECHO = "import json, sys\nsys.stdout.write(json.dumps(sys.argv[1:]) + chr(10))\n"


def _python_bin() -> str:
    """An interpreter path safe to splice into POSIX shell script text.

    Windows discovery (``shutil.which``) returns Windows paths
    (``C:\\…\\python.EXE``); backslashes vanish inside a bash script, so
    convert through ``cygpath`` (present on Git-Bash runners) and fall
    back to the bare ``python`` launcher, which Git-Bash resolves itself.
    """
    python3 = shutil.which("python3")
    if python3 is None:
        python3 = shutil.which("python")
    if python3 is None:
        return "python"
    if sys.platform == "win32":
        cygpath = shutil.which("cygpath")
        if cygpath is not None:
            converted = subprocess.run(
                [cygpath, python3], capture_output=True, text=True, check=False
            )
            if converted.returncode == 0 and converted.stdout.strip():
                return converted.stdout.strip()
        return "python"
    return python3


def _has(shell: str) -> bool:
    return shutil.which(shell) is not None


_CORPUS_COMMANDS = [
    "{1}",
    "{2} {1}",
    "{@}",
    "echo {1} {@}",
    "echo x {1:-def} y",
    "echo {name}",
    "echo {name:-fallback}",
    "echo {1} {2} {3}",
    "cp {1} {2}",
]


def _corpus(shell: str) -> Iterator[tuple[str, list[str]]]:
    """(command, argv) pairs that must behave identically under both legs.

    Missing positionals diverge on the list-semantics shells (a dropped
    word natively vs ``""`` under expand) and *raise* in expand() when a
    default is absent — the differential corpus only feeds expand()
    argument sets it accepts: every referenced positional must be present
    on shells where the missing case differs (fish/pwsh list semantics,
    or any shell when the command has no default for that position).
    """
    import re

    defaulted = re.compile(r"\{[\d\w]+:-")

    for command in _CORPUS_COMMANDS:
        # Track the highest index each placeholder consumes, exactly the way
        # the engine's name-map does: a named slot takes the next index
        # after the highest reference before it.
        required: set[int] = set()
        highest = 0
        has_default = bool(defaulted.search(command))
        # Walk the command in order; the engine maps names by first
        # appearance to (highest-so-far + 1).
        for tok in re.finditer(r"\{(\d+)(?::-([^}]*))?\}|\{(\w+)(?::-([^}]*))?\}", command):
            if tok.group(1) is not None:
                highest = max(highest, int(tok.group(1)))
                required.add(highest)
            elif tok.group(3) is not None:
                highest += 1
                required.add(highest)
                if tok.group(4) is not None:
                    has_default = True
        for args in (
            [],
            ["one"],
            ["my branch"],
            ["with space"],
            ["it's"],
            ['dq"quote'],
            ["dollar$sign"],
            ["three", "part", "line"],
            ["--flag", "-x"],
            ["a b", "c"],
            ["a", "", "", "d"],
            ["a;b|c&d"],
            ["x", "y", "z", "w"],
        ):
            # A positional beyond len(args) without a default is the case
            # expand() rejects (or renders differently on list shells);
            # the wrapper/None paths are pinned by the structure tests.
            if shell in ("fish", "pwsh") and len(args) < max(required, default=0):
                continue
            if not has_default and len(args) < max(required, default=1) and required:
                continue
            yield command, args


def _probe_body(native: str, python_bin: str, argecho: str) -> str:
    """Rewrite the probe word of a rendered template into the real probe.

    Corpus commands are prefixed with the literal word ``PROBE``; the
    differential runner swaps it for ``<python> <argecho.py>`` so both legs
    print the argv their child process sees.
    """
    return native.replace("PROBE", f"{python_bin} {argecho}")


@pytest.mark.integration
@pytest.mark.parametrize("shell", _DIFFERENTIAL_SHELLS)
def test_native_parity_with_expand(shell: str, tmp_path_factory: pytest.TempPathFactory) -> None:
    if not _has(shell):
        pytest.skip(f"{shell} not installed")
    bindir = tmp_path_factory.mktemp("bin")
    argecho = bindir / "argecho.py"
    argecho.write_text(_ARGECHO, encoding="utf-8")
    python_bin = _python_bin()

    for command, args in _corpus(shell):
        probe_command = f"PROBE {command}"
        native_body = render_native(probe_command, shell)
        if native_body is None:
            # Engine refused this construct for this shell — the wrapper
            # path applies (byte-identical to pre-native rendering) and
            # parity is trivially preserved there.
            continue
        expected_expand = expand(probe_command, args, shell=shell)

        native_argv = _run_native_leg(shell, native_body, args, python_bin, str(argecho))
        expand_argv = _run_expand_leg(shell, expected_expand, args, python_bin, str(argecho))
        assert native_argv == expand_argv, (shell, command, args)


def _run_native_leg(
    shell: str,
    native_body: str,
    args: list[str],
    python_bin: str,
    argecho: str,
) -> str:
    """Define the function from the rendered body; call it with *args*."""
    body = _probe_body(native_body, python_bin, argecho)
    if shell in ("bash", "zsh"):
        script = f"nat() {{\n    {body}\n}}\n"
        script += ("nat " + " ".join(shlex.quote(a) for a in args) + "\n") if args else "nat\n"
    elif shell == "fish":
        script = f"function nat\n    {body}\nend\n"
        script += ("nat " + " ".join(_fish_quote(a) for a in args) + "\n") if args else "nat\n"
    elif shell == "pwsh":
        script = f"function nat {{\n    {body}\n}}\n"
        script += ("nat " + " ".join(_pwsh_quote(a) for a in args) + "\n") if args else "nat\n"
    else:
        raise AssertionError(shell)
    binary = shutil.which(shell)
    assert binary is not None
    result = subprocess.run(
        [binary, "-c", script],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, f"native leg failed: {result.stderr}"
    return result.stdout


def _run_expand_leg(
    shell: str,
    expanded: str,
    args: list[str],
    python_bin: str,
    argecho: str,
) -> str:
    """Execute expand()'s output the way `qwik run` does; return stdout.

    expand() already interpolated quoting for *shell*; the probe program is
    substituted as two plain words (no quoting needed: no spaces in either).
    """
    expanded = expanded.replace("PROBE", f"{python_bin} {argecho}")
    if shell == "pwsh":
        from qwik.core.shell_exec import build_invocation

        cmd, use_shell = build_invocation(expanded, shell)
        result = subprocess.run(cmd, shell=use_shell, capture_output=True, text=True, check=False)
    else:
        result = subprocess.run(
            expanded,
            shell=True,
            capture_output=True,
            text=True,
            check=False,
            executable="/bin/bash" if shell == "bash" else None,
        )
    assert result.returncode == 0, f"expand leg failed: {result.stderr}"
    return result.stdout


def _fish_quote(value: str) -> str:
    """Quote *value* as one fish argument (double-quoted literal; fish
    expands ``$var`` inside those, so ``$`` is escaped too)."""
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"').replace("$", "\\$") + '"'


def _pwsh_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


# ---------------------------------------------------------------------------
# Renderer integration: hooks actually contain the native bodies.
# ---------------------------------------------------------------------------


def test_render_all_contains_native_template_bodies() -> None:
    from qwik.core.models import AliasStore

    store = AliasStore()
    store.add("gco", Alias(command="git checkout {1}"))
    out = get_renderer("bash").render_all(store.aliases)
    assert out == 'gco() {\n    git checkout "${1-}" "${@:2}"\n}'


def test_has_placeholders_untouched() -> None:
    """The mode discriminator shared with the wrapper path still works."""
    assert has_placeholders("git checkout {1}")
    assert not has_placeholders("git checkout")
