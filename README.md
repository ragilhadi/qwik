# qwik — A Friendly CLI Alias Manager

[![Coverage](https://sonarcloud.io/api/project_badges/measure?project=ragilhadi_qwik&metric=coverage)](https://sonarcloud.io/summary/new_code?id=ragilhadi_qwik)
[![Bugs](https://sonarcloud.io/api/project_badges/measure?project=ragilhadi_qwik&metric=bugs)](https://sonarcloud.io/summary/new_code?id=ragilhadi_qwik)
[![Quality Gate Status](https://sonarcloud.io/api/project_badges/measure?project=ragilhadi_qwik&metric=alert_status)](https://sonarcloud.io/summary/new_code?id=ragilhadi_qwik)

Create, manage, and run shell aliases from a single interface. Works cross-platform with bash, zsh, fish, PowerShell, cmd, Nushell, and Xonsh.

**Two ways to run any alias:**
- **`gs`** — native shell command (after one-time hook install)
- **`qwik -r gs`** — works anywhere, no setup needed

---

## Table of Contents

- [Installation](#installation)
- [Quick Start](#quick-start)
- [Core Concepts](#core-concepts)
- [Commands](#commands)
- [Alias Templates & Arguments](#alias-templates--arguments)
- [Platform-Conditional Aliases](#platform-conditional-aliases)
- [Shell Integration](#shell-integration)
- [Conflict Detection](#conflict-detection)
- [Storage & Backups](#storage--backups)
- [Environment Variables](#environment-variables)
- [Development](#development)

---

## Installation

```bash
pipx install qwik
```

Or with `uv`:

```bash
uv tool install qwik
```

## Quick Start

```bash
qwik add gs "git status"
qwik init zsh --install
source ~/.zshrc

gs                      # native shell alias
qwik -r gs               # same thing, no hook needed
```

## Core Concepts

### Two ways to run

| Way | Example | When to use |
|---|---|---|
| **Native** | `gs` | Daily use after one-time shell hook setup |
| **Via qwik** | `qwik -r gs` | Scripts, CI, restricted shells, or pre-setup |

Both share the **same store and substitution engine** — behavior is identical.

### How it works

1. You **register** aliases with `qwik add`
2. You **install** a one-line shell hook with `qwik init --install`
3. Every new shell session **regenerates** shell-native aliases from the store
4. You type `gs` just like a normal alias — because it is one

---

## Commands

### `add` — Create alias

```bash
qwik add gs "git status"
qwik add gs "git status" --tag git --description "Repo status"
qwik add gs "git status" --group git
qwik add gs "git status" --force       # overwrite existing
qwik add open "open {1}" --platform macos   # platform-conditional variant
qwik add gco "git checkout {branch}" --complete-with 'branch=git branch --format="%(refname:short)"'
qwik add k "kubectl" --complete-from kubectl  # inherit kubectl's completion
qwik add                               # interactive mode
```

### `rm` — Delete alias

```bash
qwik rm gs
qwik rm gs --yes                       # skip confirmation
```

### `rename` — Rename alias

```bash
qwik rename gs gstat                   # preserves stats
```

### `edit` — Edit in $EDITOR

```bash
qwik edit gs
# Opens TOML snippet in your $EDITOR:
#   command = "git status"
#   tag = ["git"]
#   group = ""
#   description = ""
#   enabled = true
#   (platform variants appear as command_<platform> lines when set;
#    deleting a line removes that variant)
# Save and quit to apply changes.
```

### `enable` / `disable` — Toggle without deleting

```bash
qwik disable gs                        # hides from shell hook
qwik enable gs                         # re-enables
```

### `list` — Pretty table

```bash
qwik list                              # all aliases
qwik -l                                # shortcut
qwik list --tag git                    # filter by tag
qwik list --group git                   # filter by group
qwik list --search stat                # filter by query
qwik list --platform windows           # preview another platform's resolution
```

Output:

```
  Name   Command                     Group   Tag    Used   Last
 ─────  ──────────────────────────  ──────  ─────  ─────  ───────────
  gs     git status                  git     git     42     2 min ago
  gco    git checkout {1}            git     git     18     1 hour ago
  k      kubectl                     —       k8s     7     yesterday
```

### `show` — Detailed view

```bash
qwik show gs                           # full metadata
```

### `search` — Fuzzy search

```bash
qwik search "git"
qwik -s "git"                          # shortcut
qwik search "git" --group git          # restrict to a group
```

### `pick` — Interactive fuzzy picker

```bash
qwik                                   # bare invocation
qwik pick
```

- Type characters to filter matching aliases live
- `↑`/`↓` navigate
- `Enter` runs the selected alias
- `Ctrl+E` edits it
- `Ctrl+D` deletes it
- `Esc` cancels

### `run` — Execute alias

```bash
qwik run gs
qwik run gs --short                    # pass extra args
qwik -r gs --short                     # shortcut flag
```

### `tag` / `untag`

```bash
qwik tag gs git
qwik tag gs work
qwik untag gs work
```

### `group` / `ungroup`

```bash
qwik group gs git                      # assign primary group
qwik ungroup gs                        # remove the group
```

An alias has **at most one group** (the canonical primary namespace it
belongs to) but may carry **many tags** (free-form labels).  Use `--group`
on `add`, `list`, and `search` to filter by group.

### `export` / `import`

```bash
qwik export ~/aliases.toml             # share / backup
qwik import ~/aliases.toml             # merge
qwik import ~/aliases.toml --overwrite # replace the whole store — aliases
                                        # not in the file are deleted; the
                                        # preview lists them before you confirm
```

### `sync` — Dotfile sharing across machines

`qwik sync` keeps a separate git repo at `<config_dir>/qwik-sync/` so your aliases travel between machines. `push` exports the live store → commits → pushes; `pull` pulls the remote → import-merges into your live store (with the same trust-boundary preview as `qwik import`).

```bash
qwik sync init --remote <git-url>      # one-time setup; exports current store + first commit
qwik sync push [-m "msg"]              # export → commit (if dirty) → push
qwik sync pull [-y]                    # pull → preview → merge into live store
qwik sync status                       # branch, remote, dirty, ahead/behind, alias count
```

`sync init` writes `sync.toml` (remote + branch) and `aliases.toml` (your store) into the sync repo and makes the first commit. `sync push` overwrites `aliases.toml` with the current live store, commits only if the tree is dirty, then pushes to `origin <branch>`. `sync pull` runs `git pull`, then shows the same trust-boundary preview as `qwik import` — incoming commands run under `shell=True`, so review the preview before confirming.

> **Trust warning:** pulled stores are a code-execution vector. Always review the command preview before confirming a `sync pull`; only sync with repos you control.

### `overlay` — Team/shared read-only alias store

```bash
qwik overlay add --url https://github.com/team/qwik-aliases --branch main
qwik overlay list           # show overlay aliases
qwik overlay update         # fetch and show added/changed/removed before applying
qwik overlay copy --name gs # copy an overlay alias to your user store
qwik overlay remove         # remove the overlay
```

`overlay add` and `overlay update` show the same trust-boundary preview as
`qwik import`/`qwik sync pull` — the incoming (or changed) commands, and a
confirmation prompt — before anything is applied; pass `--yes` to skip the
prompt. `update` reports "already up to date" and doesn't prompt when
nothing changed. The overlay repo is managed with `git clone` on `add` and
`git fetch` + `git reset --hard` on `update`, so it always exactly mirrors
the remote branch and can't enter a merge-conflict state.

> **Trust warning:** overlay aliases are a code-execution vector — anyone
> with push access to the overlay repo can add or change a command that
> runs under `shell=True` the next time you use it. Always review the
> preview before confirming an `overlay add`/`update`; only point the
> overlay at a repo you control.

Overlay aliases appear in `qwik list`, `qwik search`, `qwik init`, and the
picker — marked `(overlay)` in `list`/`search` — but cannot be edited or
removed (they're read-only). A user alias with the same name shadows the
overlay one. Running an overlay alias copies it to your user store for
usage tracking.

#### Signed overlays & pinning (trust v2)

The overlay is a supply chain; signing and pinning give it a trust model.
Maintainers opt in by adding two files to the overlay repo:

- `qwik-overlay.toml` — manifest with `name`, `maintainer`, and a
  `signing_key` (a public SSH key line)
- `aliases.toml.sig` — an SSH signature over `aliases.toml`
  (`ssh-keygen -Y sign -f <key> -n qwik-overlay aliases.toml`)

Users pin what they trust:

```bash
qwik overlay add --url … --key 'ssh-ed25519 AAAA… maintainer@host'
qwik overlay add --url … --pin 3f2a1b9            # exact commit
qwik overlay verify                                # re-check the signature now
qwik overlay update                                # verify → diff → confirm
qwik overlay update --to 9c4e2d1                  # explicitly move a pinned overlay
```

With a key pinned, every `update` verifies `aliases.toml`'s signature at
the *incoming* ref; a signature that does not verify is a **hard stop** —
nothing is applied.  A pinned overlay (`--pin`) never moves on `update`
without an explicit `--to <commit>`, the same guarantee a lockfile gives;
after `--to` the pin follows the applied commit.  Diff display shows a
before → after for each *changed* command — the highest-risk change and
the easiest to miss in a name list.

Unsigned overlays keep working: signing is opt-in.  Every surface marks
the state — `overlay list` prints the signature ladder (`VERIFIED` /
manifest-without-key / no-manifest "unverified"), `qwik show <name>` on
an overlay alias reports the source repo, commit, and verification
status, and `qwik doctor`'s `overlay` checks cover the repo state.
Missing `ssh-keygen` (OpenSSH ≥ 8.2) degrades to unverified warnings,
never a crash.  `qwik show <name>`'s provenance table and
`qwik overlay verify` are the quick health checks.

### `doctor` — Health check

```bash
qwik doctor                # shell, hook, store, conflicts, sync repo
qwik doctor --fix          # apply safe repairs, report what changed
qwik doctor --fix --yes    # no prompts at all
qwik doctor --json         # machine-readable findings, exit 0 always
```

`--fix` performs the obvious repairs non-interactively — the recovery
path every error message names, usable from a dotfile bootstrap:

| Finding | Fix |
|---|---|
| Store unreadable / future version | Restore newest valid backup |
| Shell hook missing | Install `qwik init <shell> --install` (prompted unless `--yes`) |
| Stale lock file | Remove if no live holder |
| Orphaned `aliases.toml.tmp-*` files | Remove (older than 5 minutes) |
| Overlay repo in a merge/conflict state | Reset to `origin/<branch>` |

**Never** fixed automatically: anything that could shadow a binary or
change an alias command (e.g. aliases shadowing PATH binaries) — those
stay warnings.

Exit codes: `0` clean or all-fixed, `1` unfixed errors remain, `2` a fix
attempt failed.

`--json` emits `{"status": ..., "checks": [{"id", "status", "message",
"fixable", "fix", "detail"}...], "summary": {"ok", "warn", "error"}}`
with no Rich markup, and always exits 0.

### `undo` — Restore a backup

Every destructive operation (add, rm, import, edit, sync pull, …) writes
a timestamped backup to `<config_dir>/backups/` before mutating the
store, keeping the last 20. `qwik undo` is the front door to that safety
net — including for silent damage the store still parses fine after
(`import --overwrite`, a lost concurrent write, an unwanted merge).

```bash
qwik undo                      # restore the most recent backup, with a diff + confirm
qwik undo --list               # table of available backups
qwik undo --to 20260815        # restore a specific backup (full or unambiguous partial stamp)
qwik undo --diff               # show what restoring the newest backup would change
qwik undo --yes                # skip confirmation
```

`--list` output:

```
  When              Aliases   Size    Stamp
 ────────────────  ────────  ──────  ──────────────────────
  2 min ago              42  3.1 KB  20260815-141803-440913-0000
  1 hour ago             41  3.0 KB  20260815-134512-118820-0000
```

The confirmation always shows a diff, because "restore the last backup"
is meaningless without knowing what it undoes:

```
Restoring 20260815-141803 would:
  + add     deploy, k9s
  - remove  gco
  ~ change  gs   'git status' → 'git status --short'
```

Restoring takes its own backup first, so `undo` is itself undoable (run
it twice to return to where you started). A corrupt backup is skipped in
`--list` with a note, not a crash.

### `suggest` — Alias candidates from shell history

Mines your shell history for frequently repeated commands that have no
alias, ranks them by estimated keystrokes saved, and offers to create
them interactively.

```bash
qwik suggest                    # interactive review of top candidates
qwik suggest --limit 20
qwik suggest --min-count 5      # only commands run at least 5 times
qwik suggest --since 30d
qwik suggest --dry-run          # print, create nothing
qwik suggest --json             # machine-readable candidates, no prompts
```

```
Analyzed 8,432 commands from ~/.zsh_history (all time)

  #   Count  Command                              Suggested   Saves
 ───  ─────  ──────────────────────────────────  ──────────  ───────
   1    312  git status                          gs          ~52 min
   2    188  docker compose up -d                dcu-d       ~34 min

Create alias for #1 (gs → 'git status')? [y/n/e(dit)/s(kip all)]
```

Name generation takes the initials of the command words (`git status` →
`gs`), extended on collision, and every suggestion passes the same
conflict checks as `qwik add` — a suggestion is never a builtin, a PATH
binary, or an existing alias. Commands that already have an exact alias
are excluded, and ranking is by estimated keystrokes saved
(`count × characters saved`), not raw frequency.

**Privacy.** History often contains secrets, so `qwik suggest`:

- Never transmits anything anywhere — the only I/O is reading your local
  history file and (on your confirmation) writing to your local store.
- Excludes commands matching common secret shapes from suggestions and
  output entirely: `--password`/`--token`/`-p <value>` flags,
  `AKIA…` key ids, `user:pass@host` URLs, `Authorization: Bearer …`
  headers, GitHub/GitLab/Slack/OpenAI-style tokens, JWTs, private-key
  files, and secret-named env assignments (`export FOO_TOKEN=…`).
- Skips one-shot commands (long absolute paths, UUIDs, hashes, pipes)
  since they are not aliasable anyway.
- **Files read:** bash `~/.bash_history` (or `$HISTFILE`), zsh
  `~/.zsh_history` (plain + extended `: <ts>:<dur>;<cmd>` formats), fish
  `~/.local/share/fish/fish_history`, PowerShell's PSReadLine
  `ConsoleHost_history.txt`, and nushell's SQLite history
  (`~/.local/share/nushell/history.sqlite3`, opened read-only). Override
  with `--history-file <path>` to read exactly one file.
- A missing or unreadable history file produces a clear message, never a
  traceback.

New shells can register history parsers via the `qwik.history_readers`
entry-point group (same pattern as `qwik.shell_renderers`).

### `init` — Shell hook

```bash
qwik init zsh                          # print hook to stdout
qwik init zsh --install                # append to ~/.zshrc with backup
```

Supported shells: `bash`, `zsh`, `fish`, `pwsh`.

Every `qwik` invocation defers importing `prompt_toolkit` (used only by
the interactive `pick` screen) and caches shell-renderer discovery
instead of re-scanning installed-package metadata on each call — so a
`qwik` call your shell hook makes on every prompt, like `qwik init`,
isn't paying for either.

### `completion` — Shell completions

Generate or install shell completion scripts for `qwik` itself (so `qwik <Tab>` offers command/alias suggestions).

```bash
qwik completion bash            # print completion script to stdout
qwik completion zsh --install   # install into ~/.zshrc + ~/.zfunc/_qwik
```

| Shell | `--install` action |
|---|---|
| bash | writes `~/.bash_completions/qwik.sh` + appends `source` line to `~/.bashrc` |
| zsh | writes `~/.zfunc/_qwik` + appends `fpath`/`compinit` to `~/.zshrc` |
| fish | writes `<fish config>/completions/qwik.fish` (auto-loaded, no rc edit) |
| pwsh / powershell | appends the script to `$PROFILE` |

Installs are idempotent (a `# qwik completion (<shell>)` marker is checked before appending) and back up the rc file with a timestamp before modifying it.

> Typer's built-in `qwik --install-completion <shell>` / `qwik --show-completion <shell>` also works; `qwik completion` provides the same scripts with qwik's own backup + idempotency behavior.

### Plugin System

qwik supports third-party shell renderers and CLI commands via Python entry points:

- **Shell renderers:** Register a class implementing `ShellRenderer` under the `qwik.shell_renderers` entry-point group in your `pyproject.toml`.
- **CLI commands:** Register a Typer-compatible callable under the `qwik.commands` entry-point group.

```toml
# In your plugin's pyproject.toml
[project.entry-points."qwik.shell_renderers"]
myshell = "my_package.shell:MyShellRenderer"
```

### Version & Help

```bash
qwik --version
qwik -v
qwik --help
qwik -h
qwik --no-color           # disable colored output for this invocation
```

---

## Alias Templates & Arguments

Aliases can pass arguments through unchanged or interpolate them into the command.

### Append mode (default — no placeholders)

Extra args are appended after quoting.

```bash
qwik add gs "git status"
gs --short              # → git status --short
```

### Template mode (placeholders)

Use `{…}` markers to substitute arguments into the command.

In the generated shell hook, template aliases are compiled to native shell
argument references (bash/zsh/fish) so calling them costs microseconds —
no `qwik run` interpreter spawn. Templates that don't compile safely fall
back to the `qwik run` wrapper automatically; see
[Per-shell rendering](#per-shell-rendering). `qwik run` remains the
runtime engine either way.

| Placeholder | Meaning |
|---|---|
| `{1}`, `{2}`, `{3}`… | Nth positional argument (1-based) |
| `{name}` | Named slot — mapped to a positional index by order of first appearance (see below) |
| `{@}` | All arguments joined with spaces |
| `{*}` | All arguments as a single quoted string |
| `{1:-default}` | Nth positional, falling back to `default` if missing |
| `{name:-default}` | Named slot, falling back to `default` if the arg is missing |

### Project-scoped aliases (`.qwik.toml`)

A repository can ship its own commands.  Drop a `.qwik.toml` in the repo
root; qwik discovers it from the current directory upward and layers its
aliases over the user store for shells running inside that tree —
precedence: **project → user → overlay**.

```toml
# .qwik.toml — committed to the repo
version = 1

[aliases.dev]
command = "docker compose -f docker-compose.dev.yml up"
description = "Start the dev stack"

[aliases.t]
command = "pytest -q {@}"
```

```bash
qwik project init      # scaffold a .qwik.toml
qwik project trust     # opt in to this directory's file (interactive)
qwik project untrust   # remove the trust record
qwik project status    # discovery + trust state
qwik project list      # merged view with (project) marks
```

**Trust is mandatory and explicit.**  A `.qwik.toml` arrives by
`git clone` — from whoever wrote the repo — so it is untrusted code by
definition.  A newly-seen file is *inert*: `qwik list` tells you it
exists and how to trust it, `qwik run`/`pick`/the hook load nothing from
it.  `qwik project trust` shows the file and records trust per absolute
path plus a SHA-256 content hash; when the file changes afterwards it
reverts to inert (doctor reports `stale`) until you re-trust it.  Cloning
a repository can never define commands in your shell by itself.

The `init` hook emits a directory-change refresh (bash: `cd` wrapper,
zsh: `chpwd` hook, fish: `--on-variable PWD`) so the project layer turns
on/off as you move in and out of the tree.  That refresh re-runs
`qwik init <shell>`, i.e. one process spawn per `cd` — the price of
per-directory scoping, documented so it's a choice, not a surprise.
Per-alias execution stays native (microseconds); only the layer
composition pays.

Project aliases are read-only: `qwik run` executes them and `edit`/
`remove`/`rename` refuse them — copy the file's contents into your own
store if you want to own them.  Doctor reports the discovered layer and
its trust state (`project.trust` check).

### Argument completion (`--complete-with` / `--complete-from`)

A native shell alias inherits the wrapped command's completion; a function
wrapper doesn't — that's why `gco <Tab>` offers filenames instead of
branches. qwik lets an alias declare per-argument completion, emitted into
the hook as native completion definitions:

```bash
qwik add gco "git checkout {branch}" \
  --complete-with 'branch=git branch --format="%(refname:short)"'
# gco <Tab>  →  main, feat/x, …   (bash/zsh/fish/pwsh)

qwik add k "kubectl" --complete-from kubectl
# k <Tab> delegates to kubectl's own completion (bash/zsh)
```

- `--complete-with KEY="COMMAND"` maps an argument to a command whose
  output supplies the candidates; `KEY` is a positional index (`1`,
  `2`, …) or a named placeholder (`branch`). Repeatable.
- `--complete-from PROGRAM` delegates every argument to that program's
  installed completion (restoring what a raw `alias` would inherit).
- Emitting is per shell: bash (`complete -F` + `compgen`), zsh
  (`compdef` + `_describe`), fish (`complete -c`), PowerShell
  (`Register-ArgumentCompleter`); `cmd`/`nu`/`xonsh` render nothing for
  completions.
- The completion *command runs in your shell at `<Tab>` time — never
  qwik. Stored in the alias entry (`[aliases.<name>.complete]`), so it
  survives export/import/sync; edit it with `qwik edit <name>`.

---

**Single positional:**

```bash
qwik add gco "git checkout {1}"
gco main                # → git checkout main
```

> **Note:** `{1}`, `{@}`, and `{N:-default}` interpolations are quoted at runtime, so args containing shell metacharacters are passed safely. `{*}` is shell-quoted as a single string. For example, `qwik run gco '; rm -rf /'` expands to `git checkout '; rm -rf /'` on a POSIX shell — the `;` is quoted and treated as a literal argument, not a command separator.
>
> The quoting rule depends on which shell will actually run the expanded command — chosen by `qwik run`'s shell detection, not by the host platform (a user can be running POSIX bash under Git Bash or WSL on a Windows host). `shlex.quote`'s POSIX single-quote syntax is used for bash/zsh/fish; cmd.exe gets caret-escaped metacharacters wrapped in doubled double quotes; PowerShell gets single-quoted strings with embedded `'` doubled, invoked via `pwsh`/`powershell` explicitly rather than through `cmd.exe`'s default `shell=True` interpreter. The guarantee above holds on all three; it does not extend to `nu` or `xonsh`, which currently fall back to POSIX quoting.

**Multiple positionals:**

```bash
qwik add gcm 'git commit -m "{1}: {2}"'
gcm feat "add login"
# → git commit -m "feat: add login"
```

**Named placeholders (readable):**

```bash
qwik add gco "git checkout {branch}"
gco main                # → git checkout main

qwik add gcm 'git commit -m "{type}: {scope}"'
gcm feat login          # → git commit -m "feat: login"
```

Named placeholders are mapped to positional arguments by **order of first appearance**: the first distinct name is `{1}`, the second is `{2}`, and so on. Repeating a name reuses its index (`echo {a} {a}` with arg `x` → `echo x x`). Named and numeric placeholders share the same index space — `echo {1} {name}` with args `a b` → `echo a b` (`{1}`=a, `{name}`=b at index 2).

> **Note:** Named placeholder names must start with a letter or underscore and contain only letters, digits, underscores, and hyphens (`^[A-Za-z_][A-Za-z0-9_-]*$`). A `{…}` that doesn't match this pattern and isn't a numeric/`@`/`*` placeholder is left as a literal — so `{123bad}` and `{some text}` in a command are passed through untouched.

**Default value:**

```bash
qwik add gpo "git push origin {1:-main}"
gpo                     # → git push origin main
gpo feature/x           # → git push origin feature/x
```

**All args joined:**

```bash
qwik add gc-chore 'git commit -m "chore: {@}"'
gc-chore init version
# → git commit -m "chore: init version"
```

**All args as one quoted string:**

```bash
qwik add note 'echo "Note: {*}"'
note hello world
# → echo "Note: 'hello world'"
```

**Mixed — template + appended extras:**

```bash
qwik add k "kubectl {1}"
k get pods -n kube-system
# → kubectl get pods -n kube-system
#     {1}=get, "pods -n kube-system" appended after template
```

---

### Placeholder defaults

`{N:-default}` is especially useful for aliases with a sensible fallback:

```bash
qwik add co "git checkout {1:-main}"
co feature              # → git checkout feature
co                      # → git checkout main (default)
```

### Validation

- `{0}` is rejected at add-time and at run-time — positional placeholders are 1-based
- Named placeholders (`{name}`) are 1-based by order of appearance, so there is no `{0name}` form; `{0name}` is a literal
- Invalid brace content (e.g. `{123bad}`, `{some text}`) is left untouched as a literal, not an error
- Missing required args produce a clear error at runtime instead of silently expanding to empty strings

---

## Platform-Conditional Aliases

One synced store, many machines. An alias can carry per-platform command
variants, so `qwik sync` travels between a Linux workstation, a macOS
laptop, and a Windows desktop without diverging:

```toml
[aliases.open]
command = "xdg-open {1}"
command_macos = "open {1}"
command_windows = "start {1}"
```

### Resolution order

First match wins, per alias:

1. `command_<platform>_<shell>` — most specific (e.g. `command_windows_pwsh`)
2. `command_<platform>` — platform fallback (`command_linux`, `command_macos`, `command_windows`)
3. `command` — the base, always present

`qwik init` (shell hook) and `qwik run` / the picker resolve the same way,
so both execution paths always pick the identical command for your
platform and shell.

### CLI

```bash
qwik add open "xdg-open {1}"                # base command
qwik add open "open {1}"  --platform macos  # adds a variant
qwik add open "start {1}" --platform windows

qwik show open            # shows all variants, marks the active one
qwik list --platform windows   # preview another platform's resolution
```

Rules:

- On an existing alias, `--platform` upserts **only the variant** — the base
  and all other fields stay untouched; overwriting an existing variant
  requires `--force`
- On a new alias, the command becomes both the base and the variant
- Every variant is placeholder-validated at add time, and all variants must
  accept the **same arguments** as the base (e.g. base `xdg-open {1}` and
  variant `open {1} {2}` is rejected)
- `qwik edit` shows variants as flat `command_<platform>` keys — delete a
  line to remove that variant
- Variants survive `export` / `import` / `sync` round-trips

Per-shell variants (`command_windows_pwsh`, `command_linux_bash`, …) are
also supported in the store — add them with `qwik edit`. Older qwik
versions reading a v2 store refuse it cleanly via the store version gate
(see [Store versioning](#store-versioning)).

---

## Shell Integration

Make aliases available as **real shell commands**.

### One-time setup

**bash:**

```bash
qwik init bash --install
source ~/.bashrc
```

**zsh:**

```bash
qwik init zsh --install
source ~/.zshrc
```

**fish:**

```bash
qwik init fish --install
source ~/.config/fish/config.fish
```

**PowerShell:**

```powershell
qwik init pwsh --install
```

The `--install` flag:
- Creates a timestamped backup of your rc file
- Appends the hook (idempotent — safe to run multiple times)

### Manual setup

If you prefer to edit your rc file directly, `qwik init <shell>` prints the hook:

```bash
eval "$(qwik init zsh)"
```

### Per-shell rendering

The hook generates native aliases/functions for each shell. Template-mode
aliases (containing `{…}` placeholders) are **compiled to native shell
argument syntax** where the shell can express them — no `qwik run` process
spawn per invocation:

| Shell | Append mode | Template mode |
|---|---|---|
| bash / zsh | `alias gs='git status'` | `gco() { git checkout "${1-}" "${@:2}" ; }` |
| fish | `alias gs 'git status'` | `function gco ; git checkout (string collect -- $argv[1]) … ; end` |
| PowerShell | `function gs { & ([ScriptBlock]::Create('git status')) @args }` | `function gs { qwik run "gs" @args }` |
| nu | `def gs [...args] { qwik run "gs" ...$args }` | `def gs [...args] { qwik run "gs" ...$args }` |
| cmd | `doskey gs=git status $*` | (best-effort, no template) |

Native compilation applies whenever the whole translation is
semantics-preserving; templates the shell can't express natively (a
placeholder inside single quotes, a composite double-quoted word like
`"p={1}"`, `{*}`'s single-string join on fish/pwsh, surplus args on pwsh)
keep the `qwik run` wrapper, whose behaviour is unchanged. Pass
`qwik init <shell> --no-native` (or set `QWIK_NO_NATIVE=1`) to force the
wrapper everywhere.

PowerShell's append mode wraps the command as a string literal compiled into a script block at call time rather than splicing it into the function body as source, and cmd's `doskey` macros are `$`/metacharacter-escaped — both so a command containing `}`, `&`, `$`, or another shell's syntax can't break out of the generated definition. Nu has no equivalent to a compiled-string script block, so both modes delegate to `qwik run`. Supported characters in a command are documented per shell in [`docs/shell-quoting.md`](docs/shell-quoting.md).

### Variable expansion

On cmd and pwsh, `%VAR%` and `$VAR` in alias commands are expanded by the
shell at run time, not treated as literal text. `qwik add` warns when it
detects these patterns. On bash/zsh/fish, `$VAR` expansion is the expected
behavior and no warning is shown. When the active shell is cmd and a template
alias (`{1}`, `{name}`) is created, `qwik add` also warns that cmd/doskey
cannot expand parameters and the alias will be omitted from cmd hooks.

---

## Conflict Detection

Every `add` and `rename` validates the new name:

| # | Check | Result |
|---|---|---|
| 1 | Already an alias? | Refuse unless `--force` |
| 2 | Shell builtin? (`cd`, `echo`, `alias`, …) | Refuse unless `--force` |
| 3 | Binary on `$PATH`? | Warn but allow |
| 4 | Valid syntax? | Refuse if it contains spaces, slashes, `$`, backticks, semicolons |

Example UX:

```bash
qwik add ls "ls --color=auto"
⚠ Warning: "ls" shadows /usr/bin/ls.
  Continue? [y/N]

qwik add cd "echo nope"
✗ "cd" is a shell builtin. Shadowing it can break your shell.

qwik add "my alias" "echo hi"
✗ Invalid name "my alias": contains whitespace.
```

---

## Storage & Backups

- **Linux/macOS:** `$XDG_CONFIG_HOME/qwik/aliases.toml` (usually `~/.config/qwik/aliases.toml`)
- **Windows:** `%APPDATA%\qwik\aliases.toml`
- **Backups:** every destructive operation writes to `qwik/backups/aliases-<timestamp>.toml` (last 20 kept)
- **Atomic writes:** temp file + rename to prevent corruption; crashed writes leave `aliases.toml.tmp-*` debris that `qwik doctor --fix` removes
- **Format:** human-readable TOML, safe to edit by hand

**Backup lifecycle:** a mutating command copies the current store into
`backups/`, rotates older backups past 20, and writes the new store
atomically. `qwik undo` lists (`--list`), diffs (`--diff`), and restores
(`--to <stamp>`) those backups, taking its own backup before restoring —
so the whole cycle is undoable. `qwik doctor --fix` uses the same
mechanism to recover from an unreadable store non-interactively.

Example store file:

```toml
version = 1

[aliases.gs]
command = "git status"
tag = ["git"]
group = "git"
description = "Quick git status"
enabled = true
created_at = "2026-05-10T10:00:00Z"
updated_at = "2026-05-10T10:00:00Z"
last_used = "2026-05-10T11:30:00Z"
run_count = 42
```

### Store versioning

qwik writes a `version = N` field to the top of `aliases.toml` describing the schema of the file. On load, if the file's version is older than the current schema, qwik auto-migrates it forward (one migrator per version step) and backs up the pre-migration file before writing the new shape. Migration is forward-only — downgrade is not supported; restore from a backup (see `qwik undo` or `qwik doctor --fix`) instead.

- **v1** — the original schema: one `command` per alias.
- **v2** — adds optional platform-conditional variants: flat `command_<platform>` / `command_<platform>_<shell>` keys next to `command` (see [Platform-Conditional Aliases](#platform-conditional-aliases)). Fresh stores are written as v2; existing stores migrate on the next write. An alias without variants behaves exactly as it did under v1.

If the file's version is newer than the version qwik understands, qwik refuses to load it and points at `qwik doctor` — typically you need to upgrade qwik to a newer release.

---

## Environment Variables

| Variable | Purpose |
|---|---|
| `EDITOR` | Editor for `qwik edit` (default: `vi`) |
| `QWIK_CONFIG_DIR` | Override default config directory |
| `XDG_CONFIG_HOME` | Base config dir (used by fish rc resolution) |
| `QWIK_DEBUG=1` | Enable debug logs to stderr |
| `NO_COLOR` | Disable colored output (also `--no-color`) |
| `QWIK_SHELL` | Force shell detection (`bash`, `zsh`, `fish`, `pwsh`, `cmd`, `nu`, `xonsh`) instead of auto-detecting from the environment/parent process |

---

## Development

```bash
# Install with dev dependencies
pip install -e ".[dev]"

# Run the test suite
pytest

# With coverage report
pytest --cov=qwik --cov-report=term-missing
```

---

## License

MIT
