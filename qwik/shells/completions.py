"""Completion-definition compilation for generated shell hooks.

An alias may declare a ``complete`` mapping from a placeholder reference
to a shell command whose output supplies that argument's candidates::

    [aliases.gco]
    command = "git checkout {branch}"
    complete = { branch = "git branch --format='%(refname:short)'" }

Renderers whose shell supports programmable completion
(:attr:`ShellRenderer.supports_completions`) emit a native definition
that, when the user hits ``<Tab>`` on the corresponding argument
position, runs the completion *command* (never qwik) and offers its
output lines as candidates.

Key resolution: a positional key (``"1"``, ``"2"``) selects that argument
slot directly; a named key (``"branch"``) resolves through the same
first-appearance index map the substitution engine uses
(:func:`qwik.core.substitute._named_placeholder_index_map`).  Keys that
don't reference a resolvable argument position emit no definition.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from qwik.core.substitute import _named_placeholder_index_map

if TYPE_CHECKING:
    from qwik.core.models import Alias

__all__ = [
    "bash_completion",
    "fish_completion",
    "pwsh_completion",
    "resolve_completion_positions",
    "zsh_completion",
]


def resolve_completion_positions(alias: Alias) -> list[tuple[int, str]]:
    """Return ``(position, completion_command)`` pairs for an alias.

    Positions are 1-based argument slots.  The same position may resolve
    for several keys (``{"1": "c1", "branch": "c2"}`` when ``branch`` is
    the first placeholder): both commands appear at that slot, joined with
    newline-separated output at completion time.  Positional keys beyond
    the alias's arity and ``@``/``*`` keys produce no definition.  The
    reserved ``"inherit"`` key is handled by the delegation emitters.
    """
    from qwik.core.substitute import placeholder_arity

    name_map = _named_placeholder_index_map(alias.command)
    arity = placeholder_arity(alias.command) or 0
    by_position: dict[int, list[str]] = {}
    for key, completion in alias.complete.items():
        if key == "inherit":
            continue
        idx: int | None
        if key.isdigit():
            idx = int(key)
        elif key in name_map:
            idx = name_map[key]
        else:
            idx = None  # unknown name / @ / *: no argument position to attach to
        if idx is None or idx < 1 or idx > arity:
            continue
        by_position.setdefault(idx, []).append(completion)
    return sorted((pos, " ; ".join(cmds)) for pos, cmds in by_position.items())


def _guarded(command: str) -> str:
    """Return *command* wrapped so its output splits into candidate lines."""
    return "$(" + command + ")"


def bash_completion(name: str, alias: Alias) -> str:
    """Return a bash ``complete -F`` definition for *name*.

    The registered function runs each completion command at completion
    time and feeds the lines through ``compgen -W``.  A ``complete``
    mapping containing the reserved key ``"inherit": "<program>"`` instead
    delegates to that program's own completion loader.
    """
    inherit = alias.complete.get("inherit")
    if inherit is not None and not alias.complete.keys() - {"inherit"}:
        escaped = name.replace("$", "\\$")
        # Delegate: load the wrapped program's completion (if installed)
        # and complete against its loader.  -o bashdefault/-o default keep
        # filename completion when the program's loader yields nothing —
        # restoring the completion a native `alias` would inherit.
        return (
            f"__qwik_delegate_{name}() {{\n"
            f"    command -v {inherit} >/dev/null 2>&1 && __load_completion_{name}\n"
            f"}}\n"
            f"__load_completion_{name}() {{\n"
            f"    local src\n"
            f'    src="$(dirname "$(command -v {inherit})")/{inherit}_completion"\n'
            '    [[ -f $src ]] && source "$src" 2>/dev/null || true\n'
            "    if declare -F _" + inherit + " >/dev/null 2>&1; then\n"
            "        complete -F _" + inherit + " -- " + escaped + "\n"
            "    fi\n"
            "}\n"
            f"complete -F __qwik_delegate_{name} -o bashdefault -o default -- {escaped}"
        )
    positions = resolve_completion_positions(alias)
    if not positions:
        return ""
    f = f"_qwik_complete_{name}"
    lines = [
        f"{f}() {{",
        "    local cur candidates words",
        '    cur="${COMP_WORDS[COMP_CWORD]}"',
    ]
    for pos, command in positions:
        lines.append(f"    if (( COMP_CWORD == {pos} )); then")
        lines.append(f"        candidates={_guarded(command)}")
        lines.append('        COMPREPLY=( $(compgen -W "$candidates" -- "$cur") )')
        lines.append("    fi")
    lines.append("    return 0")
    lines.append("}")
    escaped = name.replace("$", "\\$")
    lines.append(f"complete -F {f} -- {escaped}")
    return "\n".join(lines)


def zsh_completion(name: str, alias: Alias) -> str:
    """Return a zsh ``compdef`` definition for *name*.

    With the reserved ``"inherit": "<program>"`` key, registers the
    wrapped program's own completion function for the alias instead.
    """
    inherit = alias.complete.get("inherit")
    if inherit is not None and not alias.complete.keys() - {"inherit"}:
        escaped = name.replace(":", "\\:")
        return f"if (( $+functions[_{inherit}] )); then\n    compdef _{inherit} {escaped}\nfi"
    positions = resolve_completion_positions(alias)
    if not positions:
        return ""
    f = f"_qwik_complete_{name}"
    lines = [
        f"{f}() {{",
        "    local -a candidates",
    ]
    for pos, command in positions:
        lines.append(f"    if (( CURRENT == {pos + 1} )); then")  # zsh words: word 1 is the command
        lines.append(f'        candidates=(${{(f)"$({_guarded(command)})"}})')
        lines.append("        _describe 'values' candidates")
        lines.append("    fi")
    lines.append("}")
    escaped = name.replace(":", "\\:")
    lines.append(f"compdef {f} {escaped}")
    return "\n".join(lines)


def fish_completion(name: str, alias: Alias) -> str:
    """Return a fish ``complete`` definition for *name*.

    fish conditions on ``(count (commandline -opc))`` — the number of
    words before the cursor — matching the 1-based argument position.
    """
    positions = resolve_completion_positions(alias)
    if not positions:
        return ""
    escaped = name.replace("'", "'\\''")
    lines = []
    for pos, command in positions:
        cond = f"(count (commandline -opc) == {pos + 1})"  # word 1 is the command
        cand = command.replace("'", "'\\''")
        lines.append(f"complete -c {escaped} -f -n \"'{cond}'\" -a \"'{cand}'\"")
    return "\n".join(lines)


def pwsh_completion(name: str, alias: Alias) -> str:
    """Return a pwsh ``Register-ArgumentCompleter`` definition for *name*."""
    positions = resolve_completion_positions(alias)
    if not positions:
        return ""
    lines = [
        "Register-ArgumentCompleter -CommandName '" + name.replace("'", "''") + "' -ScriptBlock {",
        "    param($wordToComplete, $commandAst, $cursorPosition)",
        "    $args = @($commandAst.CommandElements | Select-Object -Skip 1)",
    ]
    for pos, command in positions:
        lines.append(f"    if ($args.Count -eq {pos - 1}) {{")
        lines.append("        $candidates = @(" + command + " 2>$null)")
        lines.append(
            "        $candidates | ForEach-Object {"
            " [System.Management.Automation.CompletionResult]::new($_) }"
        )
        lines.append("    }")
    lines.append("}")
    return "\n".join(lines)
