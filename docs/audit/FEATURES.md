# qwik — feature roadmap

Nine proposals, grouped into four milestones. Same issue template as BUGS.md:
**Summary → Motivation → Proposed Design → Implementation Plan → Acceptance Criteria
→ Suggested Labels**.

These are written to be published *after* the bug issues, because several depend on
fixes landing first — noted per feature.

---

## Milestone plan

| Milestone | Theme | Features | Depends on |
|---|---|---|---|
| **v1.1 — Trust the tool** | Nothing qwik does should be unrecoverable or unexplainable | F1 `qwik undo`, F2 `doctor --fix` | B5, B7, B8 |
| **v1.2 — Actually cross-platform** | One alias store, seven shells, three OSes | F3 platform-conditional commands, F4 native template rendering | B9, B10, B12 |
| **v1.3 — Make aliases discoverable** | The hard part isn't storing aliases, it's remembering they exist | F5 `qwik suggest`, F6 `qwik stats`, F7 argument completions | B22 |
| **v1.4 — Teams & scale** | Aliases that travel with a project or an org | F8 project-scoped aliases, F9 overlay trust model v2 | B14, B15 |

**Sequencing rationale.** v1.1 is deliberately small and defensive: after B5–B8, users
have reason to doubt the store, and `undo` plus a non-interactive `doctor --fix` is the
cheapest way to rebuild that confidence. v1.2 closes out the cross-platform theme the
bug list opens. v1.3 is the growth milestone — `qwik suggest` is the feature most
likely to convert a curious installer into a daily user. v1.4 is the team story, and
depends on the overlay being trustworthy first.

---
---

# F1 · [Feature] `qwik undo` — first-class access to the backup directory

## Summary

Every destructive operation already writes a timestamped backup to
`<config_dir>/backups/`, keeping the last 20. There is no command to list them, diff
them, or restore one. Expose them as `qwik undo`, `qwik undo --list`, and
`qwik undo --to <stamp>`.

## Motivation

The safety net exists and is invisible. The only path to it today is `qwik doctor`,
which offers a restore **only when the store fails to parse** — so it covers the one
case where the user already knows something is wrong, and none of the cases where the
damage is silent:

- `qwik import --overwrite` replacing the store (B7)
- `qwik edit` dropping a field (B6)
- A lost concurrent write (B5)
- `qwik rm` on the wrong alias
- A `sync pull` that merged something unwanted

In all of those the store parses perfectly. `doctor` will not offer to help, and the
user has to know that `~/.config/qwik/backups/` exists and hand-copy a file.

Discoverability is the whole feature. The mechanism is already built, tested, and
rotating correctly; it just has no front door.

**Depends on:** B7 and B8 landing first, since both change what gets backed up and
when.

## Proposed Design

```bash
qwik undo                      # restore the most recent backup, with a diff + confirm
qwik undo --list               # table of available backups
qwik undo --to 20260815-141803 # restore a specific backup
qwik undo --diff               # show what the most recent restore would change
qwik undo --yes                # skip confirmation
```

`--list` output:

```
  When              Aliases   Size    Stamp
 ────────────────  ────────  ──────  ──────────────────────
  2 min ago             42    3.1 KB  20260815-141803-440913-0000
  1 hour ago            41    3.0 KB  20260815-134512-118820-0000
  yesterday             38    2.8 KB  20260814-090133-772104-0000
```

The confirmation always shows a diff, because "restore the last backup" is meaningless
without knowing what it undoes:

```
Restoring 20260815-141803 would:
  + add     deploy, k9s
  - remove  gco
  ~ change  gs   'git status' → 'git status --short'

Restore? [y/N]
```

Restoring takes its own backup first, so `undo` is itself undoable.

## Implementation Plan

- `qwik/commands/undo.py` — new command module
- `qwik/core/store.py` — extract backup enumeration from
  `doctor._latest_valid_backup` into `Store.list_backups() -> list[BackupInfo]` and
  `Store.restore(path)`; `doctor` then consumes the same API
- `qwik/core/diff.py` — a small `diff_stores(a, b) -> StoreDiff` returning
  added/removed/changed, reused by F9 and by the improved `import --overwrite`
  preview from B7
- `qwik/ui/tables.py` — `render_backup_table`
- Restore path must take the store lock (B5)

## Acceptance Criteria

- `qwik undo --list` shows every retained backup with a relative time and alias count
- `qwik undo` diffs against the live store and requires confirmation
- `qwik undo --to <stamp>` accepts a full or unambiguous partial stamp
- Restoring backs up the current store first, so `undo` twice returns to the start
- A corrupt backup is skipped in `--list` with a note, not a crash
- `qwik doctor`'s restore path is reimplemented on the shared API
- README documents the backup lifecycle and `undo`

## Suggested Labels

`feature`, `store`, `dx`

---
---

# F2 · [Feature] `qwik doctor --fix` — non-interactive repair

## Summary

`qwik doctor` diagnoses well but can only *report*, except for one interactive restore
prompt. Add `--fix` to apply the obvious repairs, and `--json` for machine-readable
output, so doctor is usable from a dotfile bootstrap or CI.

## Motivation

Every recovery message qwik prints points at `qwik doctor`:

> Could not read alias store at …. Run `qwik doctor` to diagnose or restore from …
> Store version N is newer than supported. Upgrade qwik or restore from backup via
> 'qwik doctor'.

But `doctor`'s restore is a `[y/n]` prompt with no override. In any non-interactive
context it either hangs waiting on stdin or aborts on the `n` default. A dotfile
bootstrap script — the exact scenario in which a broken store is most likely and a
human least available — cannot use the recovery path the error message names.

The diagnosis half is equally locked up: doctor's findings only exist as styled text,
so nothing can act on them programmatically.

## Proposed Design

```bash
qwik doctor                # unchanged: report
qwik doctor --fix          # apply safe repairs, report what changed
qwik doctor --fix --yes    # no prompts at all
qwik doctor --json         # machine-readable findings, exit 0 always
```

Repairs `--fix` performs:

| Finding | Fix |
|---|---|
| Store unreadable / future version | Restore newest valid backup |
| Shell hook missing | Offer `qwik init <detected> --install` |
| Broken `compinit` block (B13) | Rewrite the completion block |
| Stale lock file | Remove if no live holder |
| Orphaned `.tmp-*` files from a crashed write | Remove |
| Overlay repo in a merge/conflict state (B15) | Reset to `origin/<branch>` |

Never fixed automatically: anything that could shadow a binary or change a command.
Those stay warnings.

`--json` shape:

```json
{"status": "error",
 "checks": [{"id": "store.readable", "status": "error",
             "message": "Store version 99 is newer than supported (max 1)",
             "fixable": true, "fix": "restore-backup"}],
 "summary": {"ok": 3, "warn": 1, "error": 1}}
```

## Implementation Plan

- `qwik/commands/doctor.py` — restructure the inline check sequence into a list of
  `Check` objects with `id`, `run()`, and optional `fix()`; the current printed report
  becomes one renderer over that list, `--json` another
- Reuse `Store.list_backups()` / `Store.restore()` from **F1**
- `qwik/core/locking.py` — add stale-lock detection
- Exit codes: `0` clean or all-fixed, `1` unfixed errors remain, `2` fix failed

## Acceptance Criteria

- `qwik doctor --fix --yes` recovers a store bricked by a future `version` with no
  input, exit 0
- `qwik doctor --json` emits valid JSON on stdout with no Rich markup, always exit 0
- `--fix` never modifies an alias command or name
- Each repair is individually tested against a synthetic broken state
- `doctor` remains non-destructive without `--fix`
- README documents `--fix`, `--json`, and the exit codes

## Suggested Labels

`feature`, `commands`, `dx`

---
---

# F3 · [Feature] Platform-conditional alias commands

## Summary

Let one alias carry per-platform command variants, so a single synced store works
across a Linux workstation, a macOS laptop, and a Windows desktop:

```toml
[aliases.open]
command = "xdg-open {1}"
command_macos = "open {1}"
command_windows = "start {1}"
```

## Motivation

`qwik sync` and `qwik overlay` are both built on the premise that one alias store
travels between machines. That premise breaks the moment a command is
platform-specific, which is often — `xdg-open`/`open`/`start`, `apt`/`brew`/`winget`,
`pbcopy`/`xclip`/`clip`, `ls --color`/`ls -G`.

Today the only workarounds are to keep divergent stores per machine (defeating sync)
or to name them differently (`openl`, `openm`, `openw`) and remember which host you
are on.

This is the natural companion to the cross-platform bug fixes: once B9–B12 make the
shells work correctly everywhere, the store becomes the remaining thing that is not
portable.

**Depends on:** B10, since selecting a variant needs reliable platform and shell
detection.

## Proposed Design

Resolution order for an alias, first match wins:

1. `command_<platform>_<shell>` — e.g. `command_windows_pwsh`
2. `command_<platform>` — `command_windows`, `command_macos`, `command_linux`
3. `command` — the fallback, required

Platform keys: `linux`, `macos`, `windows`. Shell keys: the registered renderer names.

CLI:

```bash
qwik add open "xdg-open {1}"
qwik add open "open {1}"   --platform macos     # adds a variant
qwik add open "start {1}"  --platform windows
qwik show open                                   # shows all variants, marks the active one
qwik list --platform windows                     # preview another platform's resolution
```

`qwik init` renders the variant for the current platform + shell. `qwik run` resolves
the same way, so both execution paths stay identical — the property the README already
promises.

Storage stays flat TOML keys rather than a nested table, so hand-editing remains easy
and old qwik versions reading a newer file degrade to the base `command` rather than
failing.

## Implementation Plan

- `qwik/core/models.py` — add optional `command_<platform>` fields; a
  `resolve_command(platform, shell) -> str` method holding the precedence rules; keep
  `extra="forbid"` by declaring variants explicitly
- `qwik/core/migrations.py` — bump `LATEST_VERSION` to 2 with a no-op forward migrator
- `qwik/core/platform.py` — `current_platform()` normalising `sys.platform`
- `qwik/shells/base.py` — `render_all` resolves before rendering
- `qwik/commands/run.py`, `add.py`, `show.py`, `edit.py`, `list.py` — variant-aware
- Validation: every variant is placeholder-checked at add time, and variants must
  agree on their placeholder arity

## Acceptance Criteria

- An alias with variants resolves to the right command on Linux, macOS, and Windows
- `qwik init` and `qwik run` resolve identically
- An alias with only a base `command` behaves exactly as today
- `qwik show` displays all variants and marks the active one
- `qwik list --platform <p>` previews another platform without changing anything
- Variants survive `export`/`import`/`sync` round-trips
- A v1 store loads and migrates cleanly to v2
- Placeholder arity mismatch between variants is rejected at add time
- README gains a Platform-Conditional Aliases section

## Suggested Labels

`feature`, `store`, `cross-platform`

---
---

# F4 · [Feature] Native template rendering — drop the `qwik run` round-trip

## Summary

Template-mode aliases currently render as wrappers that shell out to `qwik run`,
paying a full Python interpreter start (~300 ms today, see B22) on every invocation.
Render the substitution natively in each shell's own syntax instead, falling back to
the wrapper only for constructs a shell cannot express.

## Motivation

The README's per-shell table already promises native rendering:

| Shell | Template mode |
|---|---|
| bash / zsh | `gs() { git checkout "$1" ; }` |

What is actually emitted is:

```bash
gco() {
    qwik run "gco" "$@"
}
```

The performance gap is the point. A native `gco() { git checkout "$1"; }` costs
microseconds; the current wrapper costs a process spawn plus a pydantic import plus a
TOML parse — on every single use of the alias. For an alias used dozens of times a day
in an interactive shell, that is the difference between feeling native and feeling
sluggish.

It also removes the B3 flag-passthrough problem and the B4 stdout-pollution problem
from the hook path entirely, since neither `qwik run` nor its banner is involved.

**Depends on:** B22 (which reduces the cost of the fallback path that remains), and
B12 (escaping must be correct before more command text is spliced into shell source).

## Proposed Design

Map placeholders to native syntax per shell:

| Placeholder | bash / zsh | fish | pwsh | nu |
|---|---|---|---|---|
| `{1}` | `"$1"` | `$argv[1]` | `$args[0]` | `$arg0` |
| `{@}` | `"$@"` | `$argv` | `@args` | `...$args` |
| `{*}` | `"$*"` | `"$argv"` | `"$args"` | `($args \| str join ' ')` |
| `{1:-x}` | `"${1:-x}"` | `(count $argv > 0; and echo $argv[1]; or echo x)` | `$(if ($args.Count -gt 0) {$args[0]} else {'x'})` | positional default |
| `{name}` | resolved to its index, then as `{N}` | ″ | ″ | ″ |

Fall back to the `qwik run` wrapper when the shell cannot express the construct
(cmd/doskey for anything templated; fish defaults may be cleaner via the wrapper), and
emit a comment in the hook saying why, so the behaviour is inspectable.

A `--no-native` flag on `qwik init` forces the wrapper everywhere, as an escape hatch
if a rendering turns out to be wrong in the field.

## Implementation Plan

- `qwik/core/substitute.py` — add `render_native(command, shell) -> str | None`,
  returning `None` when the shell cannot express the template; the existing runtime
  `expand()` is untouched and remains the source of truth for `qwik run`
- Each renderer's `render_alias` tries `render_native` first, falls back to the wrapper
- `qwik/shells/base.py` — a `supports_native_templates` capability flag
- A differential test: for a corpus of (command, args) pairs, assert that the natively
  rendered alias and `qwik run` produce byte-identical output in each real shell — this
  is the test that makes the feature safe

## Acceptance Criteria

- bash, zsh, fish, pwsh, and nu render `{1}`, `{@}`, `{*}`, `{N:-default}`, and named
  placeholders natively
- Native and `qwik run` execution produce identical output for the differential corpus,
  including args with spaces, quotes, and shell metacharacters
- Shells that cannot express a construct fall back to the wrapper with an explanatory
  comment in the hook
- `qwik init --no-native` forces wrappers
- Benchmark showing the per-invocation cost drop
- README's per-shell table matches reality

## Suggested Labels

`feature`, `shells`, `performance`

---
---

# F5 · [Feature] `qwik suggest` — mine shell history for alias candidates

## Summary

Read the user's shell history, find frequently repeated commands that have no alias,
rank them by time saved, and offer to create aliases interactively.

## Motivation

The hardest part of an alias manager is not storing aliases — it is the blank page.
A new user installs qwik, runs `qwik add gs "git status"`, and then has to *notice*,
over the following weeks, which of their commands are worth aliasing. Most never do,
and the tool quietly goes unused.

`qwik suggest` inverts that: it tells the user what they already do, which is both
immediately useful and a strong first-run experience. It is the single highest-leverage
feature on this list for turning installs into daily users, and it is only possible
because qwik is a shell-integrated tool that already knows which shell you run.

It also compounds with `qwik stats` (F6): suggest finds candidates, stats confirms
whether the ones you created are earning their keep.

## Proposed Design

```bash
qwik suggest                    # interactive review of top candidates
qwik suggest --limit 20
qwik suggest --min-count 5      # only commands run at least 5 times
qwik suggest --since 30d
qwik suggest --dry-run          # print, create nothing
```

```
Analyzed 8,432 commands from ~/.zsh_history (last 90 days)

  #   Count  Command                              Suggested   Saves
 ───  ─────  ──────────────────────────────────  ──────────  ───────
   1    312  git status                          gs          ~52 min
   2    188  docker compose up -d                dcu         ~34 min
   3    140  kubectl get pods -n production      kgpp        ~48 min

Create alias for #1? [y/n/e(dit)/s(kip all)]
```

History sources: `~/.bash_history`, `~/.zsh_history` (including the
`: <ts>:<dur>;<cmd>` extended format), `~/.local/share/fish/fish_history` (YAML-ish),
`Microsoft.PowerShell_PSReadLine` history, and nushell's SQLite history.

Name generation: initials of the command words (`git status` → `gs`), extended on
collision (`gst`), always passed through the existing `ConflictChecker` so a suggestion
never proposes a builtin or an existing alias.

**Privacy is a first-class requirement.** History contains secrets. The command must:

- Never transmit anything anywhere
- Redact candidates matching common secret shapes (`--password`, `--token`, `AKIA…`,
  anything after `-p`) and exclude them from suggestions
- Skip commands with obvious one-shot arguments (long absolute paths, UUIDs, hashes)
  since they are not aliasable anyway
- Document exactly which files are read, and support `--history-file` to override

## Implementation Plan

- `qwik/core/history.py` — per-shell parsers behind one
  `read_history(shell, since) -> list[HistoryEntry]`; unavailable/unparseable sources
  degrade to empty with a warning, never an exception
- `qwik/core/suggest.py` — normalisation (strip variable trailing args), frequency
  count, scoring (`count × (len(cmd) - len(alias))`), name generation
- `qwik/core/redact.py` — secret-shaped-argument detection, unit tested against a
  corpus
- `qwik/commands/suggest.py` — interactive review loop reusing `ui/prompts.py`
- Entry-point-style registration for history parsers, mirroring the existing renderer
  plugin pattern, so new shells can be added without touching core

## Acceptance Criteria

- Parsers for bash, zsh (both formats), fish, pwsh, and nu, each with fixture-based
  tests
- Suggestions exclude commands that already have an alias and names that fail the
  conflict check
- Ranking is by estimated keystrokes saved, not raw frequency
- Secret-shaped commands are redacted and never suggested; covered by explicit tests
- `--dry-run` creates nothing
- No network access in any code path
- A missing or unreadable history file produces a clear message, not a traceback
- README documents the files read and the redaction rules

## Suggested Labels

`feature`, `commands`, `dx`

---
---

# F6 · [Feature] `qwik stats` — usage dashboard

## Summary

`run_count` and `last_used` are tracked on every alias and surfaced only as two
columns in `qwik list`. Add `qwik stats` to turn that data into something actionable:
what you actually use, what you never use, and what you should probably delete.

## Motivation

The data is already collected and paid for — `bump_usage` takes a lock and does a
read-modify-write on every single alias invocation. That is a meaningful cost for two
table columns.

Alias sets rot. People accumulate dozens over years, forget most of them, and never
prune. Surfacing "these 14 aliases have never been run" and "these 5 are 60% of your
usage" makes the store maintainable and gives the run-count tracking a reason to exist.

It also closes the loop on **F5**: suggest proposes, stats verifies.

## Proposed Design

```bash
qwik stats                  # overview
qwik stats --top 20
qwik stats --unused         # never run, or not run since --since
qwik stats --since 90d
qwik stats --json
```

```
  42 aliases · 3,847 runs · 18 used this week

  Most used
   1.  gs      312 runs   ~52 min saved   last: 2 min ago
   2.  dcu     188 runs   ~34 min saved   last: 1 hour ago

  Never used (14)
   deploy-staging, k9s, tf-plan, …
     → qwik stats --unused --prune  to remove them

  Time saved (estimated)  ~4 h 12 min
  Busiest group           git (1,204 runs across 8 aliases)
```

`--prune` runs the removals through the normal confirm-and-backup path.

The "time saved" estimate is deliberately rough (characters saved × runs ÷ typing
speed) and should be labelled as an estimate in the output.

## Implementation Plan

- `qwik/core/stats.py` — aggregation over the store; no new persisted state
- `qwik/commands/stats.py` + `qwik/ui/tables.py::render_stats`
- `--prune` reuses `remove_command`'s confirm/backup path (and F1's diff preview)
- Depends on **B5**, since `run_count` is only trustworthy once writes stop racing

## Acceptance Criteria

- `qwik stats` summarises total aliases, total runs, and recency
- `--top N`, `--unused`, `--since`, and `--json` all work
- `--prune` confirms before removing and writes a backup
- Overlay aliases are counted and marked distinctly from user aliases
- An empty store prints a friendly empty state, not a crash
- `--json` is valid JSON with no markup

## Suggested Labels

`feature`, `commands`, `dx`

---
---

# F7 · [Feature] Argument-aware completions for aliases

## Summary

`qwik completion` makes `qwik <Tab>` complete qwik's own commands. It does nothing for
the aliases themselves — after `gco <Tab>`, the shell offers filenames, not branches.
Let an alias declare how its arguments complete, and emit that into the generated hook.

## Motivation

A native shell alias inherits the completion of the command it wraps. A qwik
*function* wrapper does not — the shell sees an opaque function and falls back to
filename completion. So installing the hook actively *loses* completion that the raw
command had.

For template aliases this is the difference between `gco <Tab>` offering your branches
and offering the contents of your working directory. It is one of the most common
reasons people abandon function-based alias tools.

**Depends on:** F4, since native rendering determines what the shell can see.

## Proposed Design

```bash
qwik add gco "git checkout {1}" --complete-with "git branch --format='%(refname:short)'"
qwik add k   "kubectl {1}"      --complete-from git    # inherit another command's completion
```

Stored as an optional per-alias field:

```toml
[aliases.gco]
command = "git checkout {branch}"
complete = { branch = "git branch --format='%(refname:short)'" }
```

Rendered per shell — `complete -F` for bash, `compdef` for zsh, `complete -c` for
fish, `Register-ArgumentCompleter` for pwsh, and `extern`/custom completers for nu.

An `--inherit` mode is the higher-leverage default: for an append-mode alias whose
command is a bare program (`alias k = "kubectl"`), the hook can simply delegate to
that program's existing completion, which requires no configuration from the user at
all and fixes the majority of the regression.

## Implementation Plan

- `qwik/core/models.py` — optional `complete: dict[str, str] | None`; store version
  bump shared with **F3**
- `qwik/shells/base.py` — a `render_completion(name, alias) -> str` hook, default `""`
- Per-renderer implementations; shells without support emit nothing
- `qwik/commands/add.py` / `edit.py` — `--complete-with`, `--complete-from`
- Completion commands are executed by the *shell*, never by qwik, so no new execution
  surface is introduced in qwik itself — but the string is still user-authored shell
  code and needs the same escaping treatment as B12

## Acceptance Criteria

- Append-mode aliases wrapping a single binary inherit that binary's completion in
  bash, zsh, and fish
- A `--complete-with` command supplies candidates for the declared placeholder
- Shells without completion support render the alias unchanged, with no errors
- Completion definitions survive export/import/sync
- Integration tests asserting completion output in a real bash and zsh
- Escaping of the completion command is covered by B12's adversarial matrix

## Suggested Labels

`feature`, `shells`, `dx`

---
---

# F8 · [Feature] Project-scoped aliases (`.qwik.toml`)

## Summary

Discover a `.qwik.toml` in the current directory or any ancestor, and layer its
aliases over the user store for shells running inside that tree — so a repo can ship
its own commands.

## Motivation

Every non-trivial project accumulates commands that only make sense inside it:
`make dev`, `docker compose -f docker-compose.dev.yml up`, a long `pytest -k` line, a
deploy script with six flags. These are exactly the commands worth aliasing and exactly
the ones that do not belong in a global, machine-wide store.

This is the pattern `direnv`, `mise`, and `just` have each proven demand for, and qwik
is unusually well placed to serve it: the overlay work already established a read-only
layered store, and `all_aliases()` already merges layers with a precedence rule. This
is a third layer on machinery that exists.

For teams it is also the natural answer to the onboarding question — a new contributor
clones the repo and immediately has the project's commands, with no setup step and
nothing to install.

**Depends on:** B14 (layer visibility in `list`/`search` must be fixed first) and B15
(the trust model for non-user-authored aliases).

## Proposed Design

`.qwik.toml`, committed to the repo:

```toml
version = 1

[aliases.dev]
command = "docker compose -f docker-compose.dev.yml up"
description = "Start the dev stack"

[aliases.t]
command = "pytest -q {@}"
```

Precedence, highest first: **project → user → overlay**.

```bash
qwik list                     # project aliases marked [project]
qwik project init             # scaffold a .qwik.toml
qwik project trust            # opt in to this directory's aliases
qwik project untrust
```

**Trust is mandatory and explicit.** A `.qwik.toml` arrives by `git clone` from
whoever wrote the repo, so it is untrusted code by definition. Auto-loading it would
mean cloning a repo is enough to define commands in a contributor's shell — an
unacceptable default. Instead:

- A newly-seen `.qwik.toml` is *inert* until `qwik project trust` is run in that
  directory
- Trust is recorded per absolute path plus a content hash in the user config
- If the file changes after trusting, it reverts to inert and the user is prompted to
  review a diff
- `qwik doctor` lists trusted project directories

Shell integration needs the hook to re-evaluate on directory change (`chpwd` in zsh,
`PROMPT_COMMAND` in bash, `--on-variable PWD` in fish). That is the main implementation
risk and should be prototyped before committing to the design.

## Implementation Plan

- `qwik/core/project.py` — upward discovery from cwd (stopping at `$HOME` or a
  filesystem boundary), parse, hash
- `qwik/core/trust.py` — trust store at `<config_dir>/trusted.toml`, path + SHA-256
- `qwik/core/models.py` — `AliasStore.project_aliases`, and `all_aliases()` precedence
- `qwik/commands/project.py` — `init`, `trust`, `untrust`, `list`
- Renderers — a directory-change hook per shell; document the added startup cost, which
  makes **B22** a hard prerequisite rather than a nice-to-have
- `qwik run`, `pick`, `list`, `search`, `show` — project-layer aware

## Acceptance Criteria

- `.qwik.toml` is discovered from cwd upward and layered above the user store
- An untrusted `.qwik.toml` is never loaded and never executed; `qwik list` says it
  exists and how to trust it
- Trust is per-path and invalidated when the file's hash changes
- Aliases are marked by layer in `list`, `search`, `show`, and the picker
- Shell hooks refresh on directory change in bash, zsh, and fish
- The per-`cd` cost is measured and documented
- A project alias shadowing a user alias resolves to the project one, and `show`
  reports both
- `qwik doctor` lists trusted directories
- Security tests: cloning a repo with a `.qwik.toml` defines nothing until trusted

## Suggested Labels

`feature`, `store`, `security`, `dx`

---
---

# F9 · [Feature] Overlay trust model v2 — signed manifests and diff-on-update

## Summary

Give the overlay a real trust model: a signed manifest, a reviewable diff on every
update, pinning to a specific commit, and per-alias provenance in the UI.

## Motivation

**B15** fixes the immediate gap (no preview before applying a remote update). This
feature is the durable answer to the same question: *why should a user trust an alias
that arrived over the network?*

An overlay is a shell-command distribution channel. The commands it carries run with
the user's full privileges, are installed into shell startup files, and refresh on
demand from a repo the user does not control. That is a supply chain, and it currently
has none of the properties one expects — no signing, no pinning, no provenance, no
review.

For qwik's team story to be credible at any scale beyond a handful of trusting
colleagues, this has to exist. It is the difference between "a shared repo of aliases"
and "something I would deploy to an engineering org".

**Depends on:** B15 landing first (its diff-and-confirm is the foundation this builds
on), and F1's `diff_stores` helper.

## Proposed Design

**Manifest.** The overlay repo carries a `qwik-overlay.toml` alongside `aliases.toml`:

```toml
name = "acme-platform"
maintainer = "platform@acme.example"
min_qwik_version = "1.2.0"
signing_key = "ssh-ed25519 AAAA…"
```

**Signing.** `aliases.toml` is signed with `ssh-keygen -Y sign` — SSH signing rather
than GPG because every developer already has an SSH key and git already supports it.
Verification uses `ssh-keygen -Y verify` against an allowed-signers file the user
controls.

```bash
qwik overlay add --url … --key ssh-ed25519 AAAA…   # pin the expected key
qwik overlay verify                                 # check the signature now
qwik overlay update                                 # verify, diff, confirm
```

**Pinning.**

```bash
qwik overlay add --url … --pin 3f2a1b9      # exact commit
qwik overlay update --to 9c4e2d1            # explicit move
```

Pinned overlays never move without an explicit command — the same guarantee a lockfile
gives.

**Diff on update.** Every update shows added / removed / changed commands and requires
confirmation, with `--yes` for automation. Changed commands show a before/after, since
a modified command is the highest-risk change and the easiest to miss.

**Provenance in the UI.** `qwik show <name>` reports which overlay an alias came from,
at which commit, and whether the signature verified. `qwik doctor` reports overlay
verification status.

**Degradation.** Unsigned overlays keep working — signing is opt-in — but `list`,
`show`, and `doctor` mark them `unverified`, and `qwik overlay add` warns once.

## Implementation Plan

- `qwik/core/overlay_manifest.py` — parse and validate `qwik-overlay.toml`
- `qwik/core/signing.py` — wrap `ssh-keygen -Y sign|verify`; absent `ssh-keygen`
  degrades to unverified with a warning, never a hard failure
- `qwik/commands/overlay.py` — `verify`, `--key`, `--pin`, `--to`; update becomes
  fetch → verify → diff → confirm → reset
- `qwik/core/diff.py` — shared with **F1**
- `qwik/core/models.py` — provenance fields on overlay-sourced aliases (source URL,
  commit, verified flag), in-memory only, never written to the user store
- `qwik/commands/show.py`, `doctor.py` — surface provenance

## Acceptance Criteria

- A signed overlay verifies against the pinned key; a tampered `aliases.toml` fails
  verification and is not applied
- A pinned overlay does not move on `update` without `--to`
- Every update shows added/removed/changed with before/after for changes, and requires
  confirmation
- `qwik show` reports source overlay, commit, and verification status
- `qwik doctor` reports overlay verification status
- Unsigned overlays keep working and are marked `unverified` everywhere they appear
- Missing `ssh-keygen` degrades gracefully
- Tests: valid signature, wrong key, tampered file, unsigned overlay, pinned update
  attempt, `ssh-keygen` absent
- README documents how to publish and sign an overlay

## Suggested Labels

`feature`, `overlay`, `security`
