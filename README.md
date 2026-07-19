# qwik — A Friendly CLI Alias Manager

[![Coverage](https://sonarcloud.io/api/project_badges/measure?project=ragilhadi_qwik&metric=coverage)](https://sonarcloud.io/summary/new_code?id=ragilhadi_qwik)
[![Bugs](https://sonarcloud.io/api/project_badges/measure?project=ragilhadi_qwik&metric=bugs)](https://sonarcloud.io/summary/new_code?id=ragilhadi_qwik)
[![Quality Gate Status](https://sonarcloud.io/api/project_badges/measure?project=ragilhadi_qwik&metric=alert_status)](https://sonarcloud.io/summary/new_code?id=ragilhadi_qwik)

Create, manage, and run shell aliases from a single interface. Works cross-platform with bash, zsh, fish, PowerShell, and cmd.

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
- [Shell Integration](#shell-integration)
- [Conflict Detection](#conflict-detection)
- [Storage & Backups](#storage--backups)
- [Environment Variables](#environment-variables)
- [Development](#development)

---

## Installation

Not yet published to PyPI; install from source.

```bash
pipx install git+https://github.com/ragilhadi/qwik.git
```

Or with `uv`:

```bash
uv tool install git+https://github.com/ragilhadi/qwik.git
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
qwik add gs "git status" --force       # overwrite existing
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
#   description = ""
#   enabled = true
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
qwik list --search stat                # filter by query
```

Output:

```
  Name   Command                     Tag    Used   Last
 ─────  ──────────────────────────  ─────  ─────  ───────────
  gs     git status                  git     42     2 min ago
  gco    git checkout {1}            git     18     1 hour ago
  k      kubectl                     k8s      7     yesterday
```

### `show` — Detailed view

```bash
qwik show gs                           # full metadata
```

### `search` — Fuzzy search

```bash
qwik search "git"
qwik -s "git"                          # shortcut
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

### `export` / `import`

```bash
qwik export ~/aliases.toml             # share / backup
qwik import ~/aliases.toml             # merge
qwik import ~/aliases.toml --overwrite
```

### `doctor` — Health check

```bash
qwik doctor                            # shell, hook, store, conflicts
```

### `init` — Shell hook

```bash
qwik init zsh                          # print hook to stdout
qwik init zsh --install                # append to ~/.zshrc with backup
```

Supported shells: `bash`, `zsh`, `fish`, `pwsh`.

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

| Placeholder | Meaning |
|---|---|
| `{1}`, `{2}`, `{3}`… | Nth positional argument (1-based) |
| `{name}` | Named slot — mapped to a positional index by order of first appearance (see below) |
| `{@}` | All arguments joined with spaces |
| `{*}` | All arguments as a single quoted string |
| `{1:-default}` | Nth positional, falling back to `default` if missing |
| `{name:-default}` | Named slot, falling back to `default` if the arg is missing |

---

**Single positional:**

```bash
qwik add gco "git checkout {1}"
gco main                # → git checkout main
```

> **Note:** `{1}`, `{@}`, and `{N:-default}` interpolations are `shlex.quote`d at runtime, so args containing shell metacharacters are passed safely. `{*}` is shell-quoted as a single string. For example, `qwik run gco '; rm -rf /'` expands to `git checkout '; rm -rf /'` — the `;` is quoted and treated as a literal argument, not a command separator.

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

The hook generates native aliases/functions for each shell:

| Shell | Append mode | Template mode |
|---|---|---|
| bash / zsh | `alias gs='git status'` | `gs() { git checkout "$1" ; }` |
| fish | `alias gs 'git status'` | `function gs ; … ; end` |
| PowerShell | `function gs { echo hi @args }` | `function gs { echo "{1}" $args[0] }` |
| cmd | `doskey gs=git status $*` | (best-effort, no template) |

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
- **Atomic writes:** temp file + rename to prevent corruption
- **Format:** human-readable TOML, safe to edit by hand

Example store file:

```toml
version = 1

[aliases.gs]
command = "git status"
tag = ["git"]
description = "Quick git status"
enabled = true
created_at = "2026-05-10T10:00:00Z"
updated_at = "2026-05-10T10:00:00Z"
last_used = "2026-05-10T11:30:00Z"
run_count = 42
```

### Store versioning

qwik writes a `version = N` field to the top of `aliases.toml` describing the schema of the file. On load, if the file's version is older than the current schema, qwik auto-migrates it forward (one migrator per version step) and backs up the pre-migration file before writing the new shape. Migration is forward-only — downgrade is not supported; restore from a backup (see `qwik doctor`) instead.

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
