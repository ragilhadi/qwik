# Shell quoting and escaping reference

Two independent layers touch a command's text:

- **Runtime argument quoting** (`qwik run`, `qwik/core/substitute.py`):
  values interpolated into a template placeholder (`{1}`, `{@}`, `{*}`,
  `{N:-default}`) at call time.
- **Hook rendering** (`qwik init <shell>`, `qwik/shells/*.py`): the stored
  alias *command* itself, embedded into a native alias/function
  definition once, ahead of time.

Both are shell-aware: the escaping rule is chosen by the shell that will
actually interpret the text, not by the host platform, since (for
example) a user can be running POSIX bash under Git Bash or WSL on a
Windows host.

## Runtime argument quoting (`qwik run`)

| Shell | Strategy | Notes |
|---|---|---|
| bash / zsh / fish | `shlex.quote` (POSIX single-quote) | Handles every byte; `'` becomes `'"'"'`. |
| cmd | Doubled double-quotes, cmd metacharacters (`& \| < > ^ ( ) %` and `!`) caret-escaped | Runs through cmd.exe, which `subprocess.run(..., shell=True)` invokes by default on Windows. |
| pwsh | Single-quoted PowerShell string, embedded `'` doubled | `$` is never expanded inside a PowerShell single-quoted string, so no extra escaping is needed for it. Invoked via an explicit `pwsh`/`powershell` process rather than `shell=True`, since the latter would run a PowerShell-quoted string through cmd.exe instead. |

`nu` and `xonsh` currently fall back to POSIX quoting for runtime
arguments (`qwik run` invokes them the same way as bash/zsh/fish).

Every character in `qwik run gco '; rm -rf /'` — including `;`, `&`, `|`,
`<`, `>`, `^`, `%`, `` ` ``, and `$` — is passed to the target program as
one literal argument, never interpreted as a shell operator, on bash,
zsh, fish, cmd, and pwsh.

## Hook rendering (`qwik init <shell>`)

The stored command is embedded once into a generated alias/function
definition. Because it can arrive from `qwik import`, `qwik sync pull`,
or `qwik overlay` — content the user reading the hook did not necessarily
author — this embedding must not let the command's own text be
interpreted as shell syntax.

| Shell | Mechanism |
|---|---|
| bash / zsh | `alias name='<command>'`, POSIX single-quote escaped. |
| fish | `alias name '<command>'`, fish single-quote escaped. |
| pwsh | `& ([ScriptBlock]::Create('<command>')) @args` — the command is a single-quoted string literal (embedded `'` doubled) compiled into a script block at call time, so it can never be spliced into the function body as raw source. A `}` in the command cannot close the function early. |
| cmd | `doskey name=<command> $*` — every literal `$` is doubled (so it can't be misread as doskey's own `$1`-`$9`/`$*` substitution syntax) and every cmd metacharacter is caret-escaped (so it can't act as a separator/redirect/pipe once cmd.exe parses the macro's expanded text). A command containing a newline has no representation in a single-line `doskey` macro and is skipped with a `REM omitted` comment. |
| nu | `def name [...args] { qwik run "name" ...$args }` for both append and template mode. Nushell's `^command` syntax runs exactly one external program with argument-list semantics; it has no equivalent to pwsh's `ScriptBlock.Create` for safely compiling an arbitrary command *string*, so hook rendering delegates to `qwik run` instead of splicing the command into source. |
| xonsh | `aliases["name"] = ["qwik", "run", "name"]` (template mode) or `aliases["name"] = "<command>"` (append mode, Python-string escaped) — both are plain Python literal expressions, never executed as a call. |

## Not currently covered

Neither layer applies POSIX-specific shell-operator semantics (pipes,
`&&`, redirects) inside a command string rendered for cmd or nu — cmd's
doskey macros and nu's `qwik run` delegation both treat the stored
command as one opaque unit for cmd, and as an argument to a subprocess
call for nu, rather than re-parsing it as a multi-command shell script.
