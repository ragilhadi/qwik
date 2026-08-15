# qwik — bug & chore issue drafts

Ready to publish as GitHub issues. Each draft follows the template used in
`ragilhadi/mimic`: **Summary → Motivation → Repro Steps → Root Cause →
Acceptance Criteria → Suggested Labels**.

All repro steps were executed against `qwik 1.0.0` at commit `6cbe7de`.

---
---

# B1 · [Bug] fish append-mode aliases render as `'git status' $argv` — every non-template alias fails with "Unknown command"

## Summary

`FishRenderer.render_alias` wraps the **entire command string** in single quotes
before emitting it into the generated function body. fish treats a quoted string in
command position as a single command *name*, so `alias gs = "git status"` becomes a
lookup for an executable literally named `git status`.

Every append-mode alias — which is the default mode and the one the README leads
with — is dead on fish. Template-mode aliases happen to work, because they take a
different branch that delegates to `qwik run`.

## Motivation

fish is one of the four shells named in the README's opening line and one of the
four with a documented `--install` path. A fish user who follows the Quick Start
verbatim gets a hook that fails on the very first alias they created:

```
qwik add gs "git status"
qwik init fish --install
source ~/.config/fish/config.fish
gs      # fish: Unknown command: 'git status'
```

The README's own per-shell table promises `alias gs 'git status'` for fish, which is
correct fish and is *not* what the renderer emits. So the documentation describes
working behaviour that the code does not implement.

This also silently degrades the picker and `qwik init` output for fish users without
any warning or `doctor` check — nothing in the tool reports that the hook it just
installed cannot work.

## Repro Steps

```
export QWIK_CONFIG_DIR=$(mktemp -d)
qwik add gs "git status"
qwik init fish > /tmp/hook.fish
cat /tmp/hook.fish
```

Emitted hook:

```
function gs
    'git status' $argv
end
```

Sourcing and calling it in real fish (fish 3.7):

```
fish -c "source /tmp/hook.fish; gs"
```

**Expected:** the output of `git status`.
**Actual:**

```
fish: Unknown command: 'git status'
/tmp/hook.fish (line 5):
    'git status' $argv
    ^~~~~~~~~~~^
in function 'gs'
```

Exit code `127`.

## Root Cause

`qwik/shells/fish.py:44-45`:

```python
escaped = alias.command.replace("\\", "\\\\").replace("'", "\\'")
return f"function {name}\n    '{escaped}' $argv\nend"
```

The escaping itself is right; the placement of the quotes is not. The quotes belong
around *arguments*, never around the whole command line — a quoted string in command
position is a program name in fish, exactly as it is in POSIX shells.

Compare the bash renderer (`qwik/shells/bash.py:44-45`), which gets this right by
using `alias name='...'`, where the quotes are consumed by the `alias` builtin rather
than by the command parser.

Two viable fixes:

1. **Match the README** — emit `alias {name} '{escaped}'`. fish's `alias` builtin
   parses the string as a command line, so quoting the whole thing is correct there.
2. **Keep the function form** — emit the command body *unquoted* inside the function:
   `function {name}\n    {command} $argv\nend`. This needs no escaping of `'`, but
   does need the same command-body escaping discussed in **B12**.

Option 1 is the smaller change and matches the documented contract.

## Acceptance Criteria

- `qwik init fish` emits a definition that runs the command, for both simple
  (`git status`) and quote-containing (`echo "it's fine"`) commands
- Extra arguments still forward: `gs --short` → `git status --short`
- An integration test that **sources the generated fish hook and invokes the
  append-mode alias**, asserting on its stdout — not on `qwik run` (see **B20**)
- The `tests/__snapshots__/test_shell_snapshots.ambr` fish snapshot is regenerated
  and reviewed, since it currently pins the broken output
- README's per-shell rendering table matches what the renderer actually emits

## Suggested Labels

`bug`, `shells`, `correctness`

---
---

# B2 · [Bug] xonsh hook is a SyntaxError — one template alias disables every xonsh alias

## Summary

`XonshRenderer.render_alias` emits `qwik run("name", *args)` for template-mode
aliases. That is neither valid Python nor valid xonsh subprocess syntax, so xonsh
raises `SyntaxError` while evaluating the hook. Because the hook is evaluated as a
single unit via `execx($(qwik init xonsh))`, the error aborts the whole snippet —
including the append-mode aliases defined *after* it, which are themselves fine.

A single templated alias therefore takes down every qwik alias in the shell.

## Motivation

xonsh shipped in v1.0.0 as part of "M5 ecosystem & growth" and is registered as a
first-class renderer entry point. There is no integration test for it (see **B20**),
so the renderer has never been executed by a real xonsh interpreter.

The failure mode is maximally confusing: the user creates one alias with a `{1}`
placeholder and *all* their other aliases stop existing, with a traceback pointing at
a line they never wrote.

Separately, even if the syntax error were fixed, `def gs(*args): ...` does not
register a xonsh alias. xonsh resolves shell commands through the `aliases` mapping;
a bare Python function is not callable as `gs foo` from the prompt. The append-mode
branch gets this right (`aliases["gs"] = "git status"`); the template branch does not.

## Repro Steps

```
export QWIK_CONFIG_DIR=$(mktemp -d)
qwik add gs  "git status"
qwik add gco "git checkout {1}"
qwik init xonsh > /tmp/hook.xsh
cat /tmp/hook.xsh
```

Emitted hook:

```
def gco(*args):
    qwik run("gco", *args)
aliases["gs"] = "git status"
```

Evaluating it the way the install hook line does:

```
xonsh -c "execx(open('/tmp/hook.xsh').read()); gs"
```

**Expected:** `gs` runs `git status`; `gco main` runs `git checkout main`.
**Actual:**

```
xonsh: For full traceback set: $XONSH_SHOW_TRACEBACK = True
  File "<stdin>", line 2
    qwik run("gco", *args)
         ^
SyntaxError: code: run
```

`gs` is never defined — the append-mode alias on line 3 is collateral damage.

## Root Cause

`qwik/shells/xonsh.py:42-43`:

```python
if has_placeholders(alias.command):
    return f'def {name}(*args):\n    qwik run("{name}", *args)'
```

`qwik run(...)` parses as two juxtaposed Python expressions → `SyntaxError`. xonsh's
subprocess-mode fallback does not rescue it, because the line is ambiguous rather
than cleanly non-Python.

The correct xonsh form registers a callable alias and invokes the subprocess
explicitly, e.g.:

```python
return (
    f"def _qwik_{name}(args):\n"
    f'    return ![qwik run "{name}" @(args)]\n'
    f'aliases["{name}"] = _qwik_{name}'
)
```

(Exact spelling to be settled during implementation — the point is that it must
(a) parse, and (b) land in the `aliases` mapping.)

A defensive second fix is worth doing regardless: `render_all` should not let one bad
alias take out the whole hook. Emitting each definition so that a failure is isolated
(or validating the rendered snippet before printing) would have contained this.

## Acceptance Criteria

- `qwik init xonsh` output parses cleanly under `xonsh -c "execx(...)"`
- Template aliases are callable as shell commands (`gco main` → `git checkout main`),
  not merely defined as Python functions
- Append-mode aliases still work when a template alias is present in the same hook
- An integration test that pipes the generated hook through a real `xonsh` and
  asserts on the alias's output, skipped when xonsh is unavailable
- Same treatment audited for the `nu` renderer, which was added in the same milestone
  and also lacks an integration test

## Suggested Labels

`bug`, `shells`, `correctness`

---
---

# B3 · [Bug] `qwik run <alias> --flag` fails with "No such option" — flags can never be passed to an alias

## Summary

Neither `qwik run` nor the `-r` shortcut accepts an argument that starts with `-`.
Click parses the alias's arguments as options belonging to `qwik` itself and aborts
with `No such option`. The README documents both forms as working.

This also breaks the generated bash/zsh/fish/nu hooks for template aliases, because
those hooks are wrappers that call `qwik run "<name>" "$@"` — so any templated alias
invoked with a flag fails.

## Motivation

The README's "Two ways to run any alias" section is the project's central promise,
and `qwik -r gs` is presented as the form that "works anywhere, no setup needed". The
`run` section documents the failing invocation literally:

```
qwik run gs --short                    # pass extra args
qwik -r gs --short                     # shortcut flag
```

Both are copy-pasteable from the README and both fail. Passing flags to a command is
not an edge case — `git checkout -b`, `docker run -it`, `kubectl get -n` are the
motivating examples in the project's own alias-template documentation.

The blast radius is larger than the CLI, because template-mode aliases in every
POSIX shell route through `qwik run`. `qwik add gco "git checkout {1}"` then
`gco -b feature/x` fails even for a user who installed the hook and never types
`qwik` directly.

## Repro Steps

```
export QWIK_CONFIG_DIR=$(mktemp -d)
qwik add gs "git status"

qwik run gs --short
qwik -r gs --short
```

**Expected:** `git status --short` runs in both cases.
**Actual:**

```
$ qwik run gs --short
Usage: qwik run [OPTIONS] {name} [args]...
╭─ Error ─────────────────────────────────╮
│ No such option: --short                 │
╰─────────────────────────────────────────╯
exit 2

$ qwik -r gs --short
Usage: qwik [OPTIONS] COMMAND [ARGS]...
╭─ Error ──────────────────────────────────────────────────╮
│ No such option: --short (Possible options: --list)       │
╰──────────────────────────────────────────────────────────╯
exit 2
```

Through a hook, same failure:

```
qwik add gco "git checkout {1}"
eval "$(qwik init bash)"
gco -b feature/x       # → No such option: -b
```

## Root Cause

Two independent gaps.

**1. `qwik run` (`qwik/commands/run.py:23-26`).** The command is registered with
`app.command("run")(run_command)` in `qwik/cli.py:59` and never sets
`context_settings`. Click's default is to parse every `-`-prefixed token as an
option. The variadic `args: list[str]` argument cannot absorb them.

Fix: register with `ignore_unknown_options` and `allow_interspersed_args=False`:

```python
app.command("run", context_settings={
    "ignore_unknown_options": True,
    "allow_interspersed_args": False,
})(run_command)
```

**2. The `-r` shortcut (`qwik/cli.py:155-179`).** The top-level callback already
sidesteps Click by rescanning `sys.argv` for `-r`, but the callback itself never
gets that far — Click errors out during option parsing of the *group*, before
`main()` runs. The group needs the same `context_settings`, applied at
`typer.Typer(...)` construction (`qwik/cli.py:42-47`).

The existing `sys.argv` rescan is also fragile in its own right and should be
revisited: `-r` is located by scanning for the first literal `-r`/`--run` token, so
an alias *argument* equal to `-r` earlier in the line would mislocate the split. With
`ignore_unknown_options` on the group, a cleaner formulation is available.

## Acceptance Criteria

- `qwik run gs --short` and `qwik -r gs --short` both execute `git status --short`
- `--` is honoured as an explicit end-of-options marker: `qwik run gs -- --short`
- A single-dash arg (`-n`), a double-dash arg (`--short`), and a bare `-` all pass
  through untouched
- `qwik run --help` still shows `run`'s own help rather than being swallowed as an
  alias argument
- Template aliases invoked through a generated bash hook accept flags:
  `gco -b feature/x`
- Regression tests for each of the above, including one that goes through a real
  sourced bash hook
- The `sys.argv` rescan in the callback is either removed in favour of Click-native
  parsing or covered by a test for the `-r`-as-an-argument case

## Suggested Labels

`bug`, `cli`, `correctness`, `documentation`

---
---

# B4 · [Bug] `qwik run` writes its "Running …" banner to stdout, corrupting every piped alias

## Summary

Before executing an alias, `run_command` prints `✓ Running "gs" → 'git status'` to
**stdout**. That line is interleaved with the aliased command's own stdout, so any
alias used in a pipeline, captured in `$(...)`, or redirected to a file produces
corrupted output.

Because template-mode aliases in bash, zsh, fish, and nu are wrappers around
`qwik run`, this contaminates aliases that the user never invokes through `qwik`
directly.

## Motivation

Aliases exist to be composed. `gs | grep modified`, `files=$(myalias)`, and
`myalias > out.txt` are the normal way anyone uses a shell alias, and all three are
silently wrong today. Nothing about the banner is machine-readable, so downstream
tools see a stray decorated line with ANSI escapes when attached to a TTY.

The project already knows the distinction matters — `qwik/__init__.py` goes to some
trouble to force UTF-8 on stdout specifically so Rich's `✓` and `→` glyphs survive
being piped. The glyphs survive; they just should not be on that stream.

This compounds **B3**: the same wrapper path that cannot accept flags also injects a
line into its own output.

## Repro Steps

```
export QWIK_CONFIG_DIR=$(mktemp -d)
qwik add gs "git status"

qwik run gs 2>/dev/null | cat
```

stderr is discarded, so anything shown came from stdout.

**Expected:** only `git status` output.
**Actual:**

```
✓ Running "gs" → 'git status'
On branch master
nothing to commit, working tree clean
```

Same through a hook, for a templated alias:

```
qwik add count "wc -l {1}"
eval "$(qwik init bash)"
count README.md | awk '{print $1}'    # first line of output is the banner
```

## Root Cause

`qwik/commands/run.py:51`:

```python
print_success(f'Running "{name}" → {expanded!r}', console=console)
```

`print_success` (`qwik/ui/prompts.py:93-101`) resolves to `get_console()`, which is a
`rich.console.Console` writing to `sys.stdout` by default.

`qwik/commands/pick.py:68` has the identical line and the identical problem.

The fix has two parts:

1. Route the banner to **stderr** — `Console(stderr=True)` — so it stays visible to a
   human at a terminal without entering the data stream.
2. Consider suppressing it entirely when stdout is not a TTY, or gating it behind
   `--verbose` / `QWIK_DEBUG`. Announcing every command is noisy for an alias that is
   meant to feel native; `git` does not print "Running git" before running.

Recommendation: stderr **and** silence by default when `not sys.stdout.isatty()`.

While here: the same file catches only `OSError` around `store.bump_usage(name)`
(`run.py:61-64`). `bump_usage` calls `store.load()`, which raises `RuntimeError` for
a corrupt or future-versioned store (see **B8**) — that would escape the `finally`
and mask the child's exit code, which the comment explicitly says must never happen.

## Acceptance Criteria

- `qwik run <alias> | cat` emits only the aliased command's stdout
- `$(qwik run <alias>)` captures only the command's output
- The banner still reaches an interactive user (on stderr)
- No banner at all when stdout is not a TTY, or the banner is behind an explicit
  verbosity flag — decide and document which
- Identical treatment in `qwik/commands/pick.py:68`
- `bump_usage` failures cannot mask the child exit code: broaden the `except OSError`
  to also cover `RuntimeError`
- A test asserting that stdout of `qwik run` byte-matches the underlying command's
  stdout

## Suggested Labels

`bug`, `cli`, `correctness`, `dx`

---
---

# B5 · [Bug] Concurrent store writes silently lose aliases — 11 of 20 parallel `qwik add` calls vanished

## Summary

`FileLock` exists and works, but is used in exactly **two** places: `Store.bump_usage`
and `sync pull`. Every other mutating command — `add`, `rm`, `rename`, `edit`, `tag`,
`untag`, `group`, `ungroup`, `enable`, `disable`, `import`, `overlay copy`, and the
picker's run path — performs an unlocked read-modify-write of the whole store.

Two overlapping writers each read the same snapshot, mutate their own copy, and the
last `save` wins. The loser's alias is gone, with a success message already printed.

## Motivation

This is the highest-consequence bug in the audit: it destroys user data, reports
success, and leaves no error anywhere.

It is not a theoretical race. The realistic triggers are ordinary:

- A dotfile bootstrap script that adds aliases in a loop with `&`
- Two terminal tabs, one adding an alias while the other runs one (`bump_usage`
  takes the lock, but `add` does not respect it — so the lock provides *no* mutual
  exclusion, only the illusion of it)
- A shell hook regenerating on shell start while the user edits in another window

The asymmetry is the sharp edge: `bump_usage` holds the lock and therefore *feels*
protected, but because `add` never acquires it, an `add` can still clobber a
concurrent `bump_usage`, and vice versa. A lock that only one side takes is not a
lock.

Windows makes it worse in a second way — see Root Cause.

## Repro Steps

```
export QWIK_CONFIG_DIR=$(mktemp -d)
qwik add seed "echo seed"

for i in $(seq 1 20); do
  qwik add "race$i" "echo $i" >/dev/null 2>&1 &
done
wait

grep -c '^\[aliases\.' "$QWIK_CONFIG_DIR/aliases.toml"
```

**Expected:** `21` (seed + 20).
**Actual:** `10`.

Every one of the 20 `qwik add` invocations exited `0` and printed
`✓ Added "raceN" → …`. Eleven of them were lies:

```
[aliases.race1]  [aliases.race14] [aliases.race15] [aliases.race16]
[aliases.race17] [aliases.race2]  [aliases.race5]  [aliases.race6]
[aliases.race9]  [aliases.seed]
```

## Root Cause

`qwik/core/store.py:143-158` is the only guarded read-modify-write:

```python
def bump_usage(self, name: str) -> None:
    lock = FileLock(self._path.with_suffix(".toml.lock"))
    with lock:
        data = self.load()
        ...
        self.save(data)
```

Every command instead follows this unguarded shape (`qwik/commands/add.py:55-156`
is representative):

```python
store = get_store()
store_data = store.load()      # ← read
...                            # ← modify, possibly across a user prompt
store.save_with_backup(store_data)   # ← write; clobbers anything since the read
```

`grep -rn FileLock qwik/` confirms only `core/store.py:151` and
`commands/sync.py:257` acquire it.

The write itself is atomic (`save()` writes a temp file and `replace()`s it,
`store.py:139-141`), which prevents *torn* files but does nothing about lost updates
— atomicity is not isolation.

Two secondary defects in the same area, worth folding into the fix:

1. **The temp file is not unique enough on a shared store.** `save()` uses
   `.tmp-{os.getpid()}`. PIDs are recycled and are not unique across containers or
   network mounts sharing a config dir. `tempfile.mkstemp` in the target directory is
   the safe form.
2. **`FileLock.release()` seeks to 0 but `acquire()` does not.** On Windows
   (`core/locking.py:33` vs `:53-54`) `msvcrt.locking` locks a byte range at the
   *current* file position; locking at the post-`a+b`-open position and unlocking at
   offset 0 is only accidentally symmetric because the lock file is always empty.
   Both sides should `seek(0)` explicitly.

Recommended shape: a `Store.mutate()` context manager that acquires the lock, loads,
yields the store, and saves — so a command physically cannot do an unlocked
read-modify-write. Note that user prompts must happen *outside* the lock (as
`sync pull` already does deliberately, `sync.py:249-253`) and the store re-read
*inside* it.

## Acceptance Criteria

- Every mutating command performs its read-modify-write under the store lock
- The 20-parallel-`add` repro above yields 21 aliases, deterministically
- A prompt (e.g. `rm` without `--yes`, `import` without `--yes`) never blocks while
  holding the lock; the store is re-read after confirmation
- Lock acquisition timeout produces a clear error, not a silent overwrite or a hang
- `save()` uses `tempfile.mkstemp` in the destination directory rather than a
  PID-suffixed name
- `FileLock.acquire()` and `.release()` operate on the same byte offset on Windows
- A concurrency test in CI (spawn N processes, assert N aliases survive) running on
  ubuntu, macos, and windows

## Suggested Labels

`bug`, `store`, `data-loss`, `correctness`

---
---

# B6 · [Bug] `qwik edit` silently deletes the alias's `group`

## Summary

`qwik edit` rebuilds the `Alias` from the fields present in the edited snippet. The
snippet it generates contains `command`, `tag`, `description`, and `enabled` — but
not `group`, and the reconstruction does not pass `group=` either. Editing any alias
therefore resets its group to `None`, even if the user changes nothing at all.

## Motivation

Groups were added in v0.3.0 as "the canonical primary namespace an alias belongs to"
and are wired through `add --group`, `list --group`, `search --group`, `group`, and
`ungroup`. A field with that much surface area silently disappearing on an unrelated
operation is a data-loss bug, not a cosmetic one.

The failure is invisible at the moment it happens: `qwik edit` prints
`✓ Updated "gs"`, and the group is only missed later when `qwik list --group git`
stops showing the alias. A user who edits several aliases will quietly dismantle
their grouping and have no way to tell which ones were affected without diffing a
backup.

`description` and `enabled` survive only because they happen to be in the snippet;
`last_used`, `run_count`, and `created_at` survive because they are explicitly
carried over. `group` is the one field that is neither.

## Repro Steps

```
export QWIK_CONFIG_DIR=$(mktemp -d)
qwik add gs "git status" --group git --tag git --description "status"
grep -A4 'aliases.gs' "$QWIK_CONFIG_DIR/aliases.toml"
```

```
[aliases.gs]
command = "git status"
tag = ["git"]
group = "git"
description = "status"
```

Now perform an edit that changes nothing — `EDITOR=true` exits 0 without touching the
file:

```
EDITOR=true qwik edit gs
grep -A4 'aliases.gs' "$QWIK_CONFIG_DIR/aliases.toml"
```

**Expected:** the entry is byte-identical apart from `updated_at`.
**Actual:** `group = "git"` is gone.

```
[aliases.gs]
command = "git status"
tag = ["git"]
description = "status"
```

`qwik show gs` confirms `Group  —`.

## Root Cause

`qwik/commands/edit.py:81-87` builds the snippet without `group`:

```python
snippet = (
    f'# Edit the fields below and save/quit to apply changes to "{name}"\n'
    f"command = {alias.command!r}\n"
    f"tag = {alias.tag!r}\n"
    f"description = {alias.description!r}\n"
    f"enabled = {alias.enabled!r}\n"
)
```

and `qwik/commands/edit.py:111-120` reconstructs without it:

```python
data.aliases[name] = Alias(
    command=str(new_fields.get("command", alias.command)),
    tag=list(new_fields.get("tag", alias.tag)) or [],
    description=str(new_fields.get("description", alias.description)),
    enabled=bool(new_fields.get("enabled", alias.enabled)),
    created_at=alias.created_at,
    updated_at=datetime.now(timezone.utc),
    last_used=alias.last_used,
    run_count=alias.run_count,
)
```

`group` defaults to `None`, so the field is dropped on every save.

The rebuild-from-scratch pattern is the underlying hazard: it silently discards any
field a future contributor adds to `Alias` unless they remember to touch this
function too. `alias.model_copy(update=new_fields)` — or building the update dict and
validating it against the existing model — makes the code correct by construction.

Two adjacent problems in the same command, worth fixing together:

- The snippet is generated with Python `repr()` but described as TOML. `tag = ['git']`
  and `enabled = True` are not valid TOML. It round-trips only because `edit` uses its
  own hand-rolled parser (`_parse_value`, `edit.py:40-50`) rather than a TOML parser.
  A user who edits it as real TOML (`enabled = true`, `tag = ["git"]`) happens to
  work; a user who writes a multi-line string does not.
- That parser requires the exact separator `" = "`. A line written as `command="x"`
  is silently ignored and the old value is kept, with no warning.

## Acceptance Criteria

- `EDITOR=true qwik edit <name>` is a no-op for every field except `updated_at`
- `group` appears in the generated snippet and can be set, changed, and cleared there
- The reconstruction preserves any field not present in the snippet, structurally
  (e.g. `model_copy(update=...)`) rather than by an explicit field list
- The snippet is emitted as, and parsed as, real TOML via `tomlkit`
- A malformed edited snippet reports an error instead of silently keeping old values
- A test that round-trips every field on `Alias` through `edit` unchanged, which will
  fail if a future field is added without updating this command

## Suggested Labels

`bug`, `commands`, `data-loss`, `correctness`

---
---

# B7 · [Bug] `qwik import --overwrite` destroys the store behind a preview that only lists additions

## Summary

`--overwrite` replaces the entire store with the imported file. The confirmation
preview shown beforehand lists the incoming commands and a count of "New aliases",
and says nothing about the aliases that are about to be **deleted**. A user
confirming that prompt is agreeing to something the prompt does not describe.

## Motivation

The preview is explicitly framed as a trust boundary — it exists so the user can look
before they leap. It is thorough about the risk it was designed for (incoming
commands run under `shell=True`) and silent about the larger one in this code path
(everything you have is about to be erased).

The wording actively misleads. Importing a one-alias file over a 40-alias store shows:

```
New aliases (1): onlyone
```

Read plainly, that says one alias will be added. What happens is that 40 are removed
and one remains.

`--overwrite` is documented in the README as `qwik import ~/aliases.toml --overwrite`
with the one-word gloss "merge / overwrite", so a user reaching for it has no strong
signal that it is destructive either.

There is a backup — `save_with_backup` runs first — but nothing in the output tells
the user that, or where it is, or how to use it. `qwik doctor`'s restore flow only
triggers when the store is *unreadable*, and a store that was overwritten is
perfectly readable.

## Repro Steps

```
export QWIK_CONFIG_DIR=$(mktemp -d)
qwik add keep1 "echo keep1"
qwik add keep2 "echo keep2"
qwik add keep3 "echo keep3"

cat > /tmp/ow.toml <<'EOF'
[aliases.onlyone]
command = "echo onlyone"
EOF

qwik import /tmp/ow.toml --overwrite -y
```

Output:

```
Commands to be imported:
  onlyone → echo onlyone
Importing aliases is a trust boundary — stored commands will run under `shell=True`.
New aliases (1): onlyone
✓ Imported 1 aliases.
```

**Expected:** the preview names `keep1`, `keep2`, `keep3` as pending deletions and the
prompt says the store will be replaced.
**Actual:** three aliases are destroyed with no mention anywhere in the output.

## Root Cause

`qwik/commands/importer.py:168-173`:

```python
if overwrite:
    if not preview_import(incoming, data, yes=yes, console=console):
        raise typer.Exit(0)
    store.save_with_backup(incoming)
    print_success(f"Imported {len(incoming.aliases)} aliases.", console=console)
    return
```

`preview_import` (`importer.py:18-69`) computes exactly two sets:

```python
new_names      = incoming_names - existing_names
conflict_names = incoming_names & existing_names
```

The third set — `existing_names - incoming_names`, the deletions — is never computed
and never displayed. `preview_import` has no idea which mode called it, so it cannot
tailor its wording either.

Fix: give `preview_import` an explicit mode (`merge` vs `replace`); in replace mode
compute and display the removal set, and change the prompt from `Apply import?` to
something that names the consequence (`Replace store — N aliases will be deleted.
Continue?`) with `default=False`.

The success line should also name the backup path, which the code already has.

## Acceptance Criteria

- `import --overwrite` lists every alias that will be **removed**, by name, capped
  with an "… and N more" like the existing preview
- The confirmation prompt text distinguishes replace from merge and states the
  deletion count
- The post-import summary reports `N added, M removed` and prints the backup path
- `-y` still skips the prompt, but the deletion summary is printed regardless (as the
  trust warning already is)
- Same treatment for any other full-store replacement path
- Tests covering: replace with deletions, replace with an empty incoming file, and
  replace where incoming is a superset (zero deletions)

## Suggested Labels

`bug`, `commands`, `data-loss`, `dx`

---
---

# B8 · [Bug] Imported `version` is never validated — one import bricks every later qwik command

## Summary

`Store.load()` refuses to read a store whose `version` is newer than
`LATEST_VERSION`, and points the user at `qwik doctor`. `qwik import` bypasses that
guard entirely: it validates the incoming file straight into `AliasStore` without
calling `migrate()`, and with `--overwrite` writes the unvalidated `version` into the
live store.

The next `qwik` command of any kind then crashes with an unhandled `RuntimeError` and
a Python traceback.

## Motivation

The version guard exists precisely to stop a store from a newer qwik being
misinterpreted by an older one. Import is the single most likely way such a file
arrives — it is the command for consuming files written by other people and other
machines. Guarding `load` but not `import` protects the path where the file is
already trusted and leaves the untrusted one open.

The result is self-inflicted denial of service from a documented, non-destructive-
sounding command, and the recovery instructions in the error are only partly true:
`qwik doctor` does offer a restore, but it is an interactive `[y/n]` prompt with no
`--yes` or `--restore` flag, so it hangs in any non-interactive context (a script, a
CI job, a dotfile bootstrap) rather than failing.

`migrate()` is called in `Store.load` (`store.py:91-94`), `Store._merge_overlay`
(`store.py:119-123`), `sync._read_sync_aliases` (`sync.py:87-92`), and
`overlay._read_overlay_aliases` (`overlay.py:54-58`). Import is the one reader that
skips it — an inconsistency that reads like an oversight rather than a decision.

## Repro Steps

```
export QWIK_CONFIG_DIR=$(mktemp -d)
qwik add keep1 "echo keep1"

cat > /tmp/future.toml <<'EOF'
version = 99
[aliases.onlyone]
command = "echo onlyone"
EOF

qwik import /tmp/future.toml --overwrite -y      # exits 0, reports success
head -1 "$QWIK_CONFIG_DIR/aliases.toml"          # → version = 99

qwik list
```

**Expected:** the import is rejected with the same message `load` uses —
`Store version 99 is newer than supported (max 1)`.
**Actual:** the import succeeds, and every subsequent command dies:

```
╭─ Traceback (most recent call last) ─────────────────────────────────╮
│   51 │   │   │   f"Upgrade qwik or restore from backup via 'qwik doctor'." │
╰─────────────────────────────────────────────────────────────────────╯
RuntimeError: Store version 99 is newer than supported (max 1).
Upgrade qwik or restore from backup via 'qwik doctor'.
```

`qwik list`, `qwik add`, `qwik doctor`, `qwik run` — all exit 1 with a traceback.
`qwik doctor </dev/null` reaches its restore prompt and then aborts, because the
prompt defaults to `n` and there is no non-interactive override.

In merge mode (without `--overwrite`) the store is not bricked, but the incoming
`version` is silently ignored and its aliases are merged in with no migration — the
same trust gap, quieter.

## Root Cause

`qwik/commands/importer.py:149-161`:

```python
if suffix == "toml":
    parsed = dict(tomlkit.parse(raw).unwrap())
elif suffix == "json":
    parsed = json.loads(raw)
...
incoming = AliasStore.model_validate(parsed)
```

No `migrate(parsed)` call. `AliasStore.version` is a plain `int` field
(`core/models.py:157`) with no bound, so `99` validates cleanly.

Two changes:

1. Call `migrate()` on the parsed dict before `model_validate`, exactly as the other
   four readers do. That raises the correct `RuntimeError` for a future version and
   forward-migrates an old one.
2. Add a bound to the model so this cannot regress:
   `version: int = Field(default=LATEST_VERSION, le=LATEST_VERSION, ge=0)`.

Separately, the CLI should not surface a bare traceback for an expected condition.
`RuntimeError` from `Store.load()` is a *handled* failure mode with a written-out
user message; it should be caught at the command boundary and rendered through
`print_error`, exiting non-zero without a stack trace.

And `qwik doctor` needs a non-interactive repair path — see the `--fix` proposal in
FEATURES.md (F6).

## Acceptance Criteria

- `qwik import` calls `migrate()` on parsed input, in both TOML and JSON paths, in
  both merge and overwrite modes
- Importing a `version = 99` file is rejected with the same message `load` produces,
  exit code 1, and leaves the live store untouched
- Importing an old (`version = 0` / absent) file forward-migrates it
- `AliasStore.version` rejects values greater than `LATEST_VERSION` at the model level
- No qwik command prints a raw Python traceback for a `RuntimeError` raised by
  `Store.load()`; it is rendered as an error panel with exit code 1
- Round-trip test: `export` → `import` of a store written by the current version is
  lossless

## Suggested Labels

`bug`, `store`, `correctness`, `data-loss`

---
---

# B9 · [Bug] Runtime argument quoting is POSIX-only — templated aliases are broken on cmd.exe

## Summary

`qwik/core/substitute.py` quotes every interpolated argument with `shlex.quote`,
which emits POSIX single-quote syntax. `qwik run` then executes the result with
`subprocess.run(expanded, shell=True)`, which on Windows means **`cmd.exe`** — a shell
that does not treat `'` as a quote character at all.

Every argument containing a space, and every argument that `shlex.quote` decides to
quote, is passed to the target program with literal apostrophes around it.

## Motivation

This is the core cross-platform defect. It affects the substitution engine, which is
the one component both execution paths share — the README states that native aliases
and `qwik run` "share the same store and substitution engine — behavior is
identical". On Windows that shared engine emits quoting the shell cannot parse.

The README's security note leans on this quoting explicitly:

> `{1}`, `{@}`, and `{N:-default}` interpolations are `shlex.quote`d at runtime, so
> args containing shell metacharacters are passed safely. […] `qwik run gco ';
> rm -rf /'` expands to `git checkout '; rm -rf /'` — the `;` is quoted and treated
> as a literal argument, not a command separator.

Under `cmd.exe` that reasoning does not hold: `'` is not a metacharacter, so
`git checkout '; rm -rf /'` is parsed as `git checkout ';` followed by a **new
command** `rm -rf /`. The documented injection defence is a POSIX-only defence
presented as a general one.

Windows is in the CI matrix (`test.yml` runs `windows-latest` on 3.12 and 3.13), but
the shell integration tests skip when the shell binary is absent and there is no cmd
or pwsh coverage of the substitution path, so nothing catches this.

## Repro Steps

Platform-independent demonstration of what gets handed to the shell:

```
python -c "
from qwik.core.substitute import expand
print(expand('git checkout {1}', ['my branch']))
print(expand('echo {1}', ['a\$b']))
"
```

```
git checkout 'my branch'
echo 'a$b'
```

On Windows, `qwik run gco "my branch"` therefore runs, via `cmd.exe`:

```
git checkout 'my branch'
```

**Expected:** `git` receives one argument, `my branch`.
**Actual:** `git` receives two arguments, `'my` and `branch'`, and fails with
`error: pathspec ''my' did not match any file(s) known to git`.

The injection case:

```
qwik run gco "; echo PWNED"
```

**Expected (per README):** `;` is quoted and inert.
**Actual on cmd.exe:** `git checkout ';` then `echo PWNED` — the separator is live.

## Root Cause

`qwik/core/substitute.py` uses `shlex.quote` in five places —
`_parse_positional` (`:210`, `:216`), `_replacer` (`:224`, `:226`, `:230`, `:235`),
and `expand`'s append-mode branch (`:300`) and surplus branch (`:312`).

`shlex` is documented as POSIX-only; `shlex.quote`'s output is meaningful to `sh`,
`bash`, `zsh`, and `fish`, and is meaningless to `cmd.exe`. PowerShell is a third
grammar again — it accepts `'…'` but with its own escaping rule (a literal quote is
doubled, `''`, not backslash-escaped).

The fix needs a quoting strategy selected by the shell that will actually execute the
string:

- **POSIX** — `shlex.quote` (current behaviour)
- **cmd.exe** — `"`-based quoting with `"` doubled and the cmd metacharacters
  (`& | < > ^ ( ) %` and `!` under delayed expansion) `^`-escaped
- **PowerShell** — `'…'` with embedded `'` doubled

with the choice driven by the real target shell rather than by `sys.platform` alone,
since a user can be running bash under Git Bash or WSL on a Windows host.

A stronger alternative worth weighing during design: stop using `shell=True` when the
expanded command needs no shell features, and pass an argv list. That removes the
quoting question entirely for the common case, at the cost of losing pipes and
redirects unless a shell is detected as necessary.

Note this is entangled with **B10**: qwik currently has no reliable way to know it is
on cmd or pwsh, so the fix for this issue depends on that one.

## Acceptance Criteria

- Argument quoting is chosen per target shell, not hardcoded to POSIX
- On Windows/cmd, `qwik run gco "my branch"` passes exactly one argument to `git`
- On Windows/pwsh, the same holds with PowerShell quoting rules
- `qwik run gco "; echo PWNED"` treats the payload as one literal argument on cmd,
  pwsh, and POSIX alike
- Unit tests for the quoting function per shell, covering: spaces, `"`, `'`, `%VAR%`,
  `$VAR`, `&`, `|`, `^`, and an empty string
- Windows CI actually exercises `qwik run` with a spaced argument under both cmd and
  pwsh, and fails if the argument arrives split
- The README's quoting/injection note states which shells the guarantee covers

## Suggested Labels

`bug`, `windows`, `cross-platform`, `correctness`, `security`

---
---

# B10 · [Bug] `detect_shell()` returns `None` on Windows and can never return cmd, nu, or xonsh

## Summary

Shell detection reads `$SHELL` and, failing that, `/proc/self/status`. `$SHELL` is a
POSIX convention that Windows does not set, and `/proc` does not exist there — so
`detect_shell()` returns `None` on every Windows host.

Independently of platform, the detector's vocabulary is only `bash`, `zsh`, `fish`,
`pwsh`. It has no branch that can ever return `cmd`, `nu`, or `xonsh`, even though
all three are registered renderers.

## Motivation

Everything that adapts qwik's behaviour to the user's shell is downstream of this
function, so all of it degrades on Windows and for three of the seven supported
shells:

- **The cmd template warning is unreachable code.** `qwik/commands/add.py:119` guards
  on `active_shell == "cmd"`, and the README documents the behaviour: "When the
  active shell is cmd and a template alias (`{1}`, `{name}`) is created, `qwik add`
  also warns that cmd/doskey cannot expand parameters." Since `detect_shell()` cannot
  return `"cmd"`, that warning has never fired for anyone who did not pass the hidden
  `--shell cmd` flag. The alias is then silently omitted from the cmd hook — the exact
  outcome the warning exists to prevent.
- **The `%VAR%` / `$VAR` expansion warnings** (`add.py:127-139`) are gated the same
  way and are equally unreachable.
- **Builtin conflict checks fall back to bash.** `is_builtin` defaults to the bash set
  when `shell is None` (`core/conflicts.py:59-63`), so a Windows user is checked
  against `mapfile`, `readarray`, and `shopt` while `dir`, `cls`, and `copy` are
  waved through.
- **`qwik doctor` reports `Shell detected: unknown`** on Windows and then reports the
  hook as not installed, because `_hook_installed(None)` returns `False`
  unconditionally (`commands/doctor.py:212-217`) — so doctor tells a correctly
  configured Windows user that their setup is broken.

## Repro Steps

Windows behaviour, reproducible anywhere by removing the POSIX signals:

```
env -u SHELL python -c "
from qwik.core.shell_detect import detect_shell, shell_name_from_env
print('from env :', shell_name_from_env())
print('detected :', detect_shell())
"
```

```
from env : None
detected : None
```

(On a real Windows host `shell_name_from_proc` also returns `None`, since
`/proc/self/status` does not exist and the `except Exception` swallows it.)

Reachability of the other three shells:

```
grep -n 'return "' qwik/core/shell_detect.py
```

Only `bash`, `zsh`, `fish`, `pwsh` are ever returned. `cmd`, `nu`, `xonsh` appear
nowhere in the file, while `supported_shells()` reports all seven.

Consequence:

```
qwik add gco "git checkout {1}"       # on Windows/cmd
```

**Expected (per README):** a warning that cmd/doskey cannot expand parameters and the
alias will be omitted from cmd hooks.
**Actual:** no warning; `qwik init cmd` later emits
`REM omitted gco: template mode unsupported in cmd`.

## Root Cause

`qwik/core/shell_detect.py` has exactly two strategies, both POSIX:

```python
def detect_shell() -> str | None:
    return shell_name_from_env() or shell_name_from_proc()
```

`shell_name_from_env` (`:17-33`) reads `$SHELL`; `shell_name_from_proc` (`:36-64`)
reads `/proc/self/status`. Neither has a Windows path, and neither knows the three
newer shell names.

Missing signals that would fix this:

- **Windows parent-process walk** — `psutil` if available, or `ctypes` +
  `CreateToolhelp32Snapshot` to find the parent image name (`cmd.exe`,
  `powershell.exe`, `pwsh.exe`, `nu.exe`).
- **`$PSModulePath`** is set inside PowerShell on all platforms; `$PROMPT` /
  `$ComSpec` heuristics for cmd.
- **`$NU_VERSION`** is set by Nushell; **`$XONSH_VERSION`** by xonsh — both are cheap,
  reliable, and cross-platform.
- **A POSIX parent-process fallback for macOS**, where `/proc` also does not exist —
  today macOS relies entirely on `$SHELL`, which is the *login* shell and may not be
  the running one.
- **A user override**, e.g. `QWIK_SHELL`, so detection can always be forced. The
  hidden `--shell` flag on `add`/`rename` already hints at the need.

## Acceptance Criteria

- `detect_shell()` identifies `cmd` and `pwsh` on Windows without `$SHELL`
- `detect_shell()` identifies `nu` and `xonsh` via their version env vars on all
  platforms
- macOS detection does not depend solely on `$SHELL`
- A documented `QWIK_SHELL` environment override takes precedence over all detection
- `is_builtin` consults the correct builtin set on Windows rather than falling back to
  bash (see also **B11**)
- The cmd template warning and the `%VAR%`/`$VAR` warnings actually fire under their
  documented conditions, with tests that assert this through `detect_shell` rather
  than by passing `--shell` explicitly
- `qwik doctor` reports the real shell on Windows and detects an installed pwsh hook
- Unit tests with a mocked Windows environment for each detection branch

## Suggested Labels

`bug`, `windows`, `cross-platform`, `correctness`

---
---

# B11 · [Bug] Shell-builtin conflict check is case-sensitive, but cmd and PowerShell are not

## Summary

`is_builtin` does an exact-case membership test against a `frozenset` of lowercase
names. cmd.exe and PowerShell resolve command names **case-insensitively**, so
`qwik add CD "echo nope"` is allowed on Windows and produces an alias that shadows
`cd` for real.

The `pwsh` builtin set is also modelled wrongly: it lists long-form cmdlets
(`Write-Output`, `Get-ChildItem`) and omits the short aliases users would actually
collide with (`ls`, `cd`, `cat`, `rm`, `cp`, `mv`, `pwd`, `echo`, `select`, `where`).

## Motivation

The conflict pipeline's stated purpose is to stop a user breaking their own shell.
The README frames it as a hard stop:

```
qwik add cd "echo nope"
✗ "cd" is a shell builtin. Shadowing it can break your shell.
```

On Windows that guarantee is one Shift key away from being bypassed, silently. And
because `detect_shell()` cannot return `cmd` or `pwsh` at all (**B10**), the check on
Windows is against the *bash* set today — so the practical state is that Windows
users get neither correct case handling nor a correct builtin list.

For PowerShell specifically, the current list cannot fire in normal use: alias names
must match `^[A-Za-z_][A-Za-z0-9_-]*$`, so `Write-Output` is a *syntactically legal*
alias name, but nobody names an alias that. The names a user will realistically pick —
`ls`, `cat`, `rm` — are PowerShell built-in aliases and are absent from the set, so
they are never flagged.

## Repro Steps

```
python -c "
from qwik.core.conflicts import is_builtin
for n in ['cd','CD','Cd','echo','ECHO','dir','DIR']:
    print(f'{n:5} cmd={is_builtin(n, \"cmd\")}')
"
```

```
cd    cmd=True
CD    cmd=False
Cd    cmd=False
echo  cmd=True
ECHO  cmd=False
dir   cmd=True
DIR   cmd=False
```

**Expected:** all of these are `True` — cmd resolves `CD`, `Cd`, and `cd` identically.
**Actual:** only the exact lowercase spelling is caught.

End-to-end on Windows:

```
qwik add CD "echo nope"        # accepted, no warning
qwik init cmd --install
CD ..                          # now runs `echo nope`
```

PowerShell coverage gap:

```
python -c "
from qwik.core.conflicts import is_builtin
for n in ['ls','cd','cat','rm','cp','mv','pwd','echo','select','where']:
    print(f'{n:7} pwsh={is_builtin(n, \"pwsh\")}')
"
```

All report `False`; every one of them is a built-in PowerShell alias.

## Root Cause

`qwik/core/conflicts.py:59-63`:

```python
def is_builtin(name: str, shell: str | None = None) -> bool:
    if shell is None:
        shell = "bash"
    return name in SHELL_BUILTINS.get(shell, SHELL_BUILTINS["bash"])
```

A plain `in` against a `frozenset[str]` — exact, case-sensitive. The lookup needs to
be case-folded for the shells whose command resolution is case-insensitive (cmd,
PowerShell) and left exact for those where it is not (bash, zsh, fish — where `CD`
and `cd` genuinely are different commands).

`SHELL_BUILTINS["pwsh"]` (`conflicts.py:43-50`) also needs rebuilding from the real
default alias table (`Get-Alias`) plus the language keywords (`if`, `foreach`,
`while`, `function`, `param`, `return`, `break`, `continue`, `switch`, `try`,
`catch`, `finally`, `throw`, `filter`, `class`, `enum`, `using`).

`SHELL_BUILTINS["cmd"]` is reasonable but incomplete — `start`, `pause`, `assoc`,
`ftype`, `pushd`, `popd`, `mklink`, `move`, `erase`, `mkdir`, `rmdir`, `chdir`,
`setlocal`, `endlocal`, `endlocal`, `color`, `mode`, `more`, `tree`, `where` are
missing.

There are no entries for `nu` or `xonsh` at all, so both silently fall back to bash's
set via the `.get(shell, ...)` default — which is also why an unknown shell name
never surfaces as an error.

## Acceptance Criteria

- Builtin lookup is case-insensitive for `cmd` and `pwsh`, and remains case-sensitive
  for `bash`, `zsh`, and `fish`
- `is_builtin("CD", "cmd")`, `is_builtin("Dir", "cmd")`, `is_builtin("LS", "pwsh")`
  all return `True`
- The `pwsh` set is rebuilt from PowerShell's default aliases plus language keywords
- The `cmd` set is completed with the missing internal commands listed above
- `nu` and `xonsh` get their own builtin sets rather than inheriting bash's
- An unknown shell name is distinguishable from "no shell detected" instead of both
  silently meaning bash
- Table-driven tests per shell covering exact, upper, and mixed case

## Suggested Labels

`bug`, `windows`, `cross-platform`, `correctness`

---
---

# B12 · [Bug] pwsh, nu, and cmd renderers never escape the command body — a `}` breaks out of the generated function

## Summary

`BashRenderer`, `ZshRenderer`, `FishRenderer`, and `XonshRenderer` all escape the
alias command before embedding it. `PwshRenderer`, `NuRenderer`, and `CmdRenderer`
interpolate it raw. A command containing `}` closes the generated function block
early, and everything after it is emitted as top-level code in the user's PowerShell
profile or Nushell config.

Because alias commands can arrive from `qwik import`, `qwik sync pull`, and
`qwik overlay`, this is reachable from content the user did not author.

## Motivation

The three unescaped renderers are exactly the ones with no integration test
(see **B20**), which is why this survived.

The severity comes from where the output lands. `qwik init pwsh --install` appends the
hook to `$PROFILE`, and `qwik init nu --install` to `config.nu`. Both are executed on
every shell start. Code injected past a broken function boundary does not run when the
alias is called — it runs when the shell opens, before the user does anything.

The overlay path makes this a genuine trust-boundary concern rather than a
foot-gun: `qwik overlay update` pulls alias definitions from a remote git repo with
no preview (**B15**), those definitions are rendered into the shell hook by
`qwik init`, and a `}` in one of them escapes the function scope.

qwik already treats imported commands as a trust boundary at *execution* time — the
import preview warns that "stored commands will run under `shell=True`". The same
commands are not treated as untrusted at *rendering* time.

## Repro Steps

```
export QWIK_CONFIG_DIR=$(mktemp -d)
qwik add brace 'echo hi } ; Write-Host PWNED ; function dummy {'
qwik init pwsh
```

**Expected:** one well-formed `function brace { … }` whose body is the literal command.
**Actual:**

```
function brace {
    echo hi } ; Write-Host PWNED ; function dummy { @args
}
```

The function ends at the first `}`. `Write-Host PWNED` is now a top-level statement in
the profile, executed at every shell start.

Nushell, same input:

```
qwik init nu
```

```
def brace [...args] {
    ^echo hi } ; Write-Host PWNED ; function dummy { ...$args
}
```

cmd, same input — `doskey` has no block syntax, but the payload passes through raw:

```
doskey brace=echo hi } ; Write-Host PWNED ; function dummy { $*
```

For contrast, bash handles the analogous case correctly (`qwik/shells/bash.py:44`):

```
qwik add q "echo it's fine"
qwik init bash
# alias q='echo it'"'"'s fine'
```

## Root Cause

`qwik/shells/pwsh.py:45` — raw interpolation:

```python
return f"function {name} {{\n    {alias.command} @args\n}}"
```

`qwik/shells/nu.py:44` — raw interpolation:

```python
return f"def {name} [...args] {{\n    ^{alias.command} ...$args\n}}"
```

`qwik/shells/cmd.py:52` — raw interpolation:

```python
return f"doskey {name}={alias.command} $*"
```

None of the three has an escaping step. Each target needs its own:

- **PowerShell** — the safe form is a single-quoted string invoked through the call
  operator, `& { … }` or `Invoke-Expression 'cmd'` with `'` doubled; a raw statement
  body cannot be made safe without a parser.
- **Nushell** — same shape; the command body needs to become a quoted string passed to
  a runner rather than spliced in as source.
- **cmd/doskey** — macro text cannot contain a newline at all, and `$`, `^`, and `&`
  are special to doskey; these need escaping or the alias needs rejecting.

There is a second, cheaper layer worth adding regardless of the per-shell fix: no
renderer currently rejects a command containing a newline, and a newline in any of
these three formats breaks the hook unconditionally. Validating at `qwik add` time
(and warning at render time for commands that arrived via import) would catch the
whole class.

## Acceptance Criteria

- pwsh, nu, and cmd renderers escape or safely quote the command body
- The `}` repro above produces a hook where `PWNED` is never executed, on all three
- A command containing a newline is either escaped correctly or rejected with a clear
  message at `add`/`import` time
- Commands containing `"`, `'`, `` ` ``, `$`, `%`, `&`, `|`, `^`, and `;` render
  correctly on every supported shell
- A shared renderer test matrix: one adversarial command set × all seven renderers,
  asserting the rendered hook parses in that shell where the shell is available
- Documented statement of which characters are supported per shell

## Suggested Labels

`bug`, `shells`, `security`, `correctness`

---
---

# B13 · [Bug] `qwik completion zsh --install` writes bare `compinit` — every new zsh shell prints "command not found"

## Summary

The zsh completion installer appends `fpath=($HOME/.zfunc $fpath)` followed by
`compinit` to `~/.zshrc`. `compinit` is an autoloadable function, not a builtin — it
must be loaded with `autoload -Uz compinit` first. Without that line, every new zsh
session prints `command not found: compinit` and completions never activate.

## Motivation

The command's entire purpose is to make `qwik <Tab>` work. It does the opposite: it
leaves completions non-functional *and* adds a startup error to a file the user
probably will not think to blame.

The error appears on every shell open, in a config file qwik modified without
displaying the lines it added, so the connection back to `qwik completion` is not
obvious. The README presents the install as reliable — "Installs are idempotent […]
and back up the rc file with a timestamp before modifying it" — which is true of the
mechanics and beside the point about the content.

The idempotency marker makes it stickier: the appended block is marked
`# qwik completion (zsh)`, and re-running the command sees the marker and reports
"already installed", so a user who reruns it after upgrading qwik keeps the broken
block.

## Repro Steps

Exactly the lines the installer writes:

```
zsh -c 'fpath=($HOME/.zfunc $fpath); compinit'
```

**Expected:** silence, and the completion system initialised.
**Actual:**

```
zsh:1: command not found: compinit
```

The correct form, for comparison:

```
zsh -c 'fpath=($HOME/.zfunc $fpath); autoload -Uz compinit; compinit'   # silent
```

End to end:

```
qwik completion zsh --install
zsh -i -c 'true'      # prints: command not found: compinit
qwik completion zsh --install
# → "already installed" — the broken block is never repaired
```

## Root Cause

`qwik/commands/completion.py:139`:

```python
hook_line = f"\n{marker}\nfpath=($HOME/.zfunc $fpath)\ncompinit\n"
```

The `autoload -Uz compinit` line is missing. The conventional block is:

```zsh
fpath=($HOME/.zfunc $fpath)
autoload -Uz compinit
compinit
```

Two related issues in the same block:

1. **`compinit` may already be called** by the user's framework (oh-my-zsh, prezto)
   or later in their `.zshrc`. Calling it twice is slow and can emit insecure-directory
   warnings. Guarding with
   `(( $+functions[compdef] )) || { autoload -Uz compinit; compinit; }` is the safer
   spelling, or appending only the `fpath` line and documenting that the user needs
   `compinit` — which most zsh users already have.
2. **The path is hardcoded to `$HOME/.zfunc`** in the rc line (`completion.py:139`)
   while the script is written to `rc.parent / ".zfunc"` (`completion.py:127`). These
   agree only when `rc.parent == $HOME`. The bash installer has the same split —
   `script_path` is derived from `rc.parent` (`:103`) but the source line is the
   literal `source ~/.bash_completions/qwik.sh` (`:115`).

Both installers should write the resolved absolute path they actually used.

## Acceptance Criteria

- The zsh block includes `autoload -Uz compinit` before `compinit`
- `zsh -i -c true` after `qwik completion zsh --install` produces no errors and
  `qwik <Tab>` completes
- `compinit` is not invoked a second time when the user's config already ran it
- The bash and zsh installers write the absolute path they actually wrote the script
  to, rather than a hardcoded `~/…`
- An upgrade path for users with the broken block: either the marker gains a version
  suffix so a reinstall replaces it, or `qwik doctor` detects and reports it
- An integration test that sources the modified rc in a real zsh and asserts a clean
  startup, skipped when zsh is unavailable

## Suggested Labels

`bug`, `shells`, `dx`, `correctness`

---
---

# B14 · [Bug] `qwik list` and `qwik search` say "No aliases yet" for overlay-only users

## Summary

`list` and `search` gate on `data.aliases` — the user's own aliases — while `init`,
`pick`, and the store's merged view use `data.all_aliases()`, which includes the
overlay. A user whose aliases all come from a team overlay is told they have none,
while their shell hook is simultaneously generating all of them.

## Motivation

The README states the contract plainly:

> Overlay aliases appear in search, `qwik init`, and the picker, but cannot be edited
> or removed (they're read-only).

Two of those three are wrong. `search` is named in the sentence and does not work.

The overlay feature exists so a team can distribute a shared alias set that members
consume without copying. "Consume without copying" is precisely the state in which
`data.aliases` is empty — so the intended primary use case is the one that reports
nothing. A new team member's first two commands are likely `qwik overlay add …`
followed by `qwik list`, and the second one tells them the first failed.

## Repro Steps

```
export QWIK_CONFIG_DIR=$(mktemp -d)
mkdir -p "$QWIK_CONFIG_DIR/overlay-repo"
printf 'url = "https://example.com/team"\nbranch = "main"\n' > "$QWIK_CONFIG_DIR/overlay.toml"
printf 'version = 1\n[aliases.teamalias]\ncommand = "echo team"\n' \
  > "$QWIK_CONFIG_DIR/overlay-repo/aliases.toml"

qwik list
qwik search team
qwik init bash
```

**Expected:** `list` and `search` show `teamalias`, marked as coming from the overlay.
**Actual:**

```
$ qwik list
No aliases yet. Run `qwik add <name> <command>` to create one.

$ qwik search team
No aliases yet.

$ qwik init bash
alias teamalias='echo team'
```

The hook renders it; the two commands for looking at it deny it exists.

## Root Cause

`qwik/commands/list.py:26-30`:

```python
if not data.aliases:
    console.print("[dim]No aliases yet. Run `qwik add <name> <command>` to create one.[/dim]")
    raise typer.Exit(0)
```

`qwik/commands/search.py:26-28` has the same guard.

The renderer beneath `list` has the same scope problem — `render_list_table`
(`qwik/ui/tables.py:56`) iterates `store.aliases` only, so even past the guard the
overlay rows would not appear.

`search_aliases` (`qwik/core/search.py:80`) *does* iterate `store.all_aliases()`, so
`search` would work correctly if the guard and the table were fixed.

Compare the paths that get it right: `qwik/commands/init_shell.py:92` renders
`data.all_aliases()`, and `qwik/ui/picker.py:153` checks `store.all_aliases()`.

The fix should also introduce a visible provenance marker, since a user needs to know
which aliases they cannot edit — `qwik overlay list` already uses a `(user)` /
`(overlay)` marker (`commands/overlay.py:213`) that `list` could adopt.

## Acceptance Criteria

- `qwik list` and `qwik search` include overlay aliases
- The empty-state message appears only when `all_aliases()` is empty
- Overlay-sourced rows are visually distinguishable from user-owned rows
- `list --tag` / `--group` filters apply to overlay aliases too
- A user alias shadowing an overlay alias of the same name is shown once, as the user's
- Tests for: overlay-only store, mixed store, and the shadowing case

## Suggested Labels

`bug`, `overlay`, `dx`, `documentation`

---
---

# B15 · [Bug] `qwik overlay update` pulls and installs remote commands with no preview or confirmation

## Summary

`qwik import` and `qwik sync pull` both show a trust-boundary preview listing the
incoming commands and require confirmation. `qwik overlay add` and
`qwik overlay update` pull alias definitions from a remote git repo and apply them
with neither. The pulled commands then enter the user's shell hook on the next
`qwik init`.

## Motivation

The overlay is the *most* remote of the three ingestion paths — a repo controlled by
someone else, refreshed on demand — and it is the only one without a gate.

The threat is not exotic. The overlay is designed for a team-shared repo; anyone with
push access to it, or anyone who compromises it, can add or modify an alias. On the
next `qwik overlay update`, that command is silently installed into every member's
shell hook and executes the next time they type the alias name — or, given **B12**,
at shell startup.

The inconsistency is the clearest argument that this is an oversight rather than a
design choice. `preview_and_merge` already exists in `qwik/commands/importer.py` and
is deliberately shared between `import` and `sync pull`; the README documents the
reasoning:

> **Trust warning:** pulled stores are a code-execution vector. Always review the
> command preview before confirming a `sync pull`; only sync with repos you control.

The same sentence applies verbatim to the overlay, and the overlay documentation
contains no equivalent warning.

A secondary correctness problem sits alongside it: `_do_add` builds the overlay repo
with `git init` + `git remote add` + `git pull` (`overlay.py:119-129`) rather than
`git clone`. That leaves no upstream tracking branch, makes `git pull` on a
subsequent `update` depend on argument-supplied refs, and will merge rather than fast
-forward if the local tree ever diverges — producing merge commits or conflicts in a
directory the user never edits.

## Repro Steps

```
export QWIK_CONFIG_DIR=$(mktemp -d)
qwik overlay add --url <a repo you control> --branch main
```

Push a new alias to that repo, then:

```
qwik overlay update
qwik init bash
```

**Expected:** the same preview `import` and `sync pull` show — the incoming commands
listed, the `shell=True` warning, and a confirmation prompt.
**Actual:** `✓ Overlay updated from <url> (main).` and nothing else. The new alias is
already in `qwik init bash` output.

For contrast, the same content through the sanctioned path:

```
qwik import /tmp/incoming.toml
# Commands to be imported:
#   newalias → …
# Importing aliases is a trust boundary — stored commands will run under `shell=True`.
# Apply import? [y/n] (n):
```

## Root Cause

`qwik/commands/overlay.py:182-187` — `_do_update` is a bare pull:

```python
try:
    git_pull(overlay_repo, "origin", branch)
    print_success(f"Overlay updated from {url} ({branch}).", console=console)
except RuntimeError as exc:
    ...
```

`_do_add` (`overlay.py:125-149`) likewise pulls, saves the config, and reports a
count — it reads the incoming aliases only to print how many there are, never to show
them.

Neither imports `preview_import`, which is exported from
`qwik/commands/importer.py:15` precisely for this.

Suggested shape:

- Show the diff, not the whole set — on `update`, list aliases **added**, **removed**,
  and **changed** relative to the currently-checked-out overlay, since an unchanged
  overlay should not prompt at all.
- Require confirmation when the diff is non-empty, with `--yes` to skip.
- Replace `init` + `remote add` + `pull` with `git clone --depth 1` on `add`, and
  `git fetch` + `git reset --hard origin/<branch>` on `update` — the overlay is
  read-only by design, so a hard reset is correct and avoids merge states entirely.
- Add the same trust warning to the README's overlay section that the sync section
  already carries.

## Acceptance Criteria

- `qwik overlay update` shows added/removed/changed aliases and prompts before
  applying, with `--yes` to bypass
- `qwik overlay add` shows the incoming command list and prompts, like `import` does
- An update with no changes reports "already up to date" and does not prompt
- The overlay repo is created with `git clone` and refreshed with fetch + reset, so it
  cannot enter a merge-conflict state
- README's overlay section carries the same trust warning as the sync section
- Tests covering: first add, no-op update, update with an added alias, update with a
  changed command, and declining the prompt

## Suggested Labels

`bug`, `overlay`, `security`, `dx`

---
---

# B16 · [Bug] `search_aliases` ignores `limit` for empty queries

## Summary

`search_aliases` applies its `limit` parameter only on the scored path. The
early-return branch for an empty query returns every candidate, so a caller asking
for 20 results can receive thousands.

## Motivation

Minor in isolation, but it is on the interactive picker's hot path. `_refresh`
(`qwik/ui/picker.py:244`) calls `search_aliases(store, query, limit=50)` and is
invoked on **every keystroke** — including the initial render with an empty query,
and every time the user clears the input.

With a large store, the picker builds and formats a list of every alias in the store
on those refreshes, then hands the whole thing to `FormattedTextControl` for a window
capped at ten visible rows (`picker.py:166`). The work is thrown away.

The API is also just wrong as documented: the docstring says "limit: Maximum number of
results to return", with no exception noted.

## Repro Steps

```
python -c "
from qwik.core.models import Alias, AliasStore
from qwik.core.search import search_aliases
s = AliasStore(aliases={f'a{i}': Alias(command='x') for i in range(500)})
print('empty query, limit=20 ->', len(search_aliases(s, '',   limit=20)))
print('real query,  limit=20 ->', len(search_aliases(s, 'a1', limit=20)))
"
```

**Expected:**

```
empty query, limit=20 -> 20
real query,  limit=20 -> 20
```

**Actual:**

```
empty query, limit=20 -> 500
real query,  limit=20 -> 20
```

## Root Cause

`qwik/core/search.py:89-91`:

```python
if not query:
    # No query → return all candidates alphabetically with dummy score.
    return [(n, a, 0.0) for n, a in sorted(candidates)]
```

The scored path below it (`:97`) ends with `return scored[:limit]`; this branch has no
slice.

The fix is one slice, `[:limit]`. Worth pairing with a look at the picker's refresh
strategy while in the area — rebuilding two `FormattedTextControl` objects per
keystroke (`picker.py:262-267`, and again in every arrow-key handler at `:92-97` and
`:103-108`) allocates a new control on each event rather than updating the existing
one's data source.

## Acceptance Criteria

- `search_aliases(store, "", limit=N)` returns at most `N` results
- Sorting semantics for the empty-query path are unchanged (alphabetical)
- The docstring matches the behaviour
- A test asserting the limit holds for empty, whitespace, and non-matching queries

## Suggested Labels

`bug`, `correctness`, `performance`

---
---

# B17 · [Bug] The picker's Ctrl+E and Ctrl+D route through `typer.testing.CliRunner`

## Summary

When the user presses Ctrl+E (edit) or Ctrl+D (delete) in the fuzzy picker,
`pick_command` re-enters the CLI by constructing a `typer.testing.CliRunner` and
invoking the app in-process. `CliRunner` is a **test harness**: it replaces
`sys.stdin` with an empty stream and captures `sys.stdout`.

The delete path consequently cannot receive the confirmation the `rm` command asks
for, and both paths buffer their output instead of streaming it.

## Motivation

Ctrl+D is advertised in the README (`Ctrl+D` deletes it) and in the picker's own
footer. `rm` prompts for confirmation unless `--yes` is passed
(`qwik/commands/remove.py:36-40`), and the invocation here does not pass it — so the
prompt is issued against `CliRunner`'s empty stdin, hits EOF, and Click aborts. The
user presses Ctrl+D, sees an "Aborted." blob, and the alias is still there.

Beyond the immediate bug, importing a testing module at runtime is a structural
problem: `typer.testing` is not part of Typer's supported runtime surface, it pulls in
`click.testing`, and it is not guaranteed to exist in a minimal install. A refactor
in Typer that moves or hardens `typer.testing` breaks a user-facing feature at
runtime, and nothing in the type checker or the test suite would flag it.

## Repro Steps

Interactive, requires a TTY:

```
export QWIK_CONFIG_DIR=$(mktemp -d)
qwik add doomed "echo doomed"
qwik pick
# highlight `doomed`, press Ctrl+D
qwik list
```

**Expected:** a confirmation, then the alias is removed.
**Actual:** the picker exits and prints captured output containing Click's abort; the
alias survives. `qwik list` still shows `doomed`.

The mechanism, without a TTY:

```
grep -n "typer.testing\|CliRunner" qwik/commands/pick.py
```

```
32:        from typer.testing import CliRunner
35:        result = CliRunner().invoke(app, ["edit", name])
41:        from typer.testing import CliRunner
44:        result = CliRunner().invoke(app, ["rm", name])
```

## Root Cause

`qwik/commands/pick.py:29-46`:

```python
if selected.startswith("__edit__:"):
    name = selected.split(":", 1)[1]
    # Delegate to edit command by re-invoking CLI
    from typer.testing import CliRunner
    from qwik.cli import app

    result = CliRunner().invoke(app, ["edit", name])
    console.print(result.output)
    raise typer.Exit(result.exit_code)
```

and the identical block for `__delete__`.

The intent — reuse the existing command rather than duplicating its logic — is right;
the mechanism is not. The commands are plain functions (`edit_command`,
`remove_command`) and can be called directly:

```python
from qwik.commands.edit import edit_command
edit_command(name)
```

Their `typer.Argument`/`typer.Option` defaults do need handling when called outside
Click, which is the usual argument for a thin internal function underneath each
command that both the CLI wrapper and the picker call. That is the cleaner target
shape.

The `__edit__:` / `__delete__:` string protocol between `run_picker` and
`pick_command` (`qwik/ui/picker.py:124`, `:130`) is worth replacing at the same time —
an alias literally named `__edit__:x` is impossible today only because the name regex
forbids `:`, which is a fragile thing to rely on. A small result dataclass
(`PickerResult(action, name)`) removes the ambiguity.

## Acceptance Criteria

- Ctrl+D deletes the selected alias, prompting for confirmation on the real terminal
- Ctrl+E opens `$EDITOR` with a real TTY and applies the edit
- `typer.testing` is not imported anywhere under `qwik/`
- The picker communicates its action via a typed result, not a string prefix
- Tests for the picker's edit and delete actions that assert the store changed, driven
  through `prompt_toolkit`'s pipe input like the existing picker tests

## Suggested Labels

`bug`, `ui`, `dx`, `correctness`

---
---

# B18 · [Bug] `--no-color` and `NO_COLOR` are ignored by rm, rename, tag, export, and init

## Summary

Most commands build their console with `get_console()`, which honours the
`--no-color` flag and the `NO_COLOR` environment variable. Five construct
`rich.console.Console()` directly, bypassing both — and also losing the qwik theme, so
theme tokens like `[qwik.error]` are not resolved.

## Motivation

`NO_COLOR` is an ecosystem convention with a specific promise: set it once, and no
program emits escape sequences. Honouring it in most commands and not others is worse
than not honouring it at all, because a user who sets it and spot-checks
`qwik list` will reasonably assume the whole CLI complies, then find escape codes in a
log written by `qwik rm`.

The README documents both mechanisms in the Environment Variables table
(`NO_COLOR` — "Disable colored output (also `--no-color`)") without qualification.

The theme loss is the more visible half. `Console()` has no `theme=THEME`, so a markup
tag like `[qwik.error]` is not a known style. Any string relying on qwik's theme tokens
rendered through one of these consoles does not get the intended styling.

## Repro Steps

```
export QWIK_CONFIG_DIR=$(mktemp -d)
qwik add gs "git status"

NO_COLOR=1 qwik list  | cat -v | head -3      # clean
NO_COLOR=1 qwik rm gs -y | cat -v             # contains ESC sequences
```

**Expected:** no escape sequences from either.
**Actual:** `qwik rm` emits `^[[1;32m…` despite `NO_COLOR=1`.

Same for the flag:

```
qwik --no-color rm gs -y | cat -v
```

The affected call sites:

```
grep -rn "Console()" qwik/commands/
```

```
qwik/commands/remove.py:22
qwik/commands/rename.py:31
qwik/commands/tag.py:23
qwik/commands/tag.py:45
qwik/commands/exporter.py:29
qwik/commands/init_shell.py:84
```

## Root Cause

`qwik/ui/theme.py:40-55` is the single correct constructor — it applies `THEME` and
resolves `color_system=None` when `_no_color_active()`:

```python
def get_console(*, no_color: bool = False, **kwargs: Any) -> Console:
    color_system = None if (no_color or _no_color_active()) else "auto"
    return Console(theme=THEME, color_system=color_system, **kwargs)
```

The six sites above call `Console()` instead, getting neither.

There is a related sequencing subtlety worth fixing at the same time. `--no-color` is
applied by mutating a module global in the top-level callback
(`qwik/cli.py:137-138`):

```python
import qwik.ui.theme as _theme
_theme._NO_COLOR_OVERRIDE = no_color
```

That works for consoles built *after* the callback runs, but it unconditionally
assigns `no_color` — so it is also the mechanism by which a `False` is written on
every invocation. It is fine today because nothing else sets the global, but a
module-level mutable flag set from a CLI callback is fragile; carrying the setting on
the Typer context, or reading it inside `_no_color_active()` from a single resolved
config object, is more robust.

## Acceptance Criteria

- Every command's console comes from `get_console()`
- `NO_COLOR=1` and `--no-color` produce escape-free output from every command,
  verified by a test that runs each registered command and asserts no `\x1b` in output
- Theme tokens (`[qwik.error]`, `[qwik.success]`, …) resolve everywhere
- `grep -rn "Console()" qwik/` returns no hits outside `qwik/ui/theme.py`
- The `--no-color` state is carried explicitly rather than by assigning a module global

## Suggested Labels

`bug`, `ui`, `dx`

---
---

# B19 · [Chore] `mypy --strict` fails with 16 errors on master and CI installs mypy unpinned

## Summary

`.github/workflows/test.yml` runs `mypy qwik` as a gating step after
`pip install mypy` — unpinned. With current mypy (2.3.1) that step fails with 16
errors in `qwik/ui/picker.py`, on a clean checkout of `master` with no local changes.

## Motivation

A gate that fails on master is not a gate. Either the Tests workflow is red on every
PR — in which case contributors learn to ignore it — or it is green only because CI is
resolving an older mypy than a developer would get locally, which means the gate's
verdict depends on the day the job ran.

The unpinned install is the root problem. `pre-commit` pins mypy to `v1.11.2`
(`.pre-commit-config.yaml`), so a developer running the hooks and CI running the
workflow are checking against different type checkers with different strictness. The
project explicitly opts into `strict = true` in `pyproject.toml`, which makes it
especially sensitive to version drift.

## Repro Steps

Clean checkout of `master` (`6cbe7de`), no modifications:

```
git status --porcelain          # empty
pip install mypy                # → 2.3.1
mypy qwik
```

**Expected:** clean, matching the CI gate's intent.
**Actual:**

```
qwik/ui/picker.py:104: error: Incompatible return value type ...  [return-value]
qwik/ui/picker.py:107: error: Argument 1 to "FormattedTextControl" has incompatible type ...  [arg-type]
...
Found 16 errors in 1 file (checked 44 source files)
```

All 16 are in `qwik/ui/picker.py`:

```
mypy qwik 2>&1 | grep -oP '^\S+?\.py' | sort | uniq -c
     16 qwik/ui/picker.py
```

## Root Cause

Two separate things.

**1. The type errors.** `_get_result_lines` and `_get_preview_lines`
(`qwik/ui/picker.py:39-70`) are annotated `-> list[tuple[str, str]]`, but
`prompt_toolkit`'s `FormattedTextControl` expects `AnyFormattedText`, whose list form
is `list[tuple[str, str] | tuple[str, str, Callable[[MouseEvent], object]]]`.
`list` is invariant, so `list[tuple[str, str]]` is not assignable to it. The fix is to
annotate the helpers with `StyleAndTextTuples` (prompt_toolkit's own alias) rather
than the narrower concrete type.

**2. The unpinned install.** `.github/workflows/test.yml`:

```yaml
- name: Install dependencies
  run: |
    python -m pip install --upgrade pip
    pip install .[dev]
    pip install mypy          # ← unpinned
```

mypy belongs in the `dev` extra in `pyproject.toml` with a version constraint, so that
`pip install .[dev]`, pre-commit, and CI all resolve the same checker. The same applies
to `ruff`, which is pinned in pre-commit and absent from both the dev extra and CI
(see **B21**).

## Acceptance Criteria

- `mypy qwik` is clean on master with the pinned version
- `mypy` and `ruff` are declared in the `dev` extra with version constraints
- CI installs them from the extra, not with a bare `pip install mypy`
- The pinned version matches `.pre-commit-config.yaml`, so local hooks and CI agree
- Dependabot covers the pins so upgrades arrive as reviewable PRs rather than as
  surprise CI failures — add a `github-actions` ecosystem entry to
  `.github/dependabot.yml` while there

## Suggested Labels

`chore`, `ci`, `testing`

---
---

# B20 · [Chore] Shell integration tests never invoke a generated alias — the gap that let B1 and B2 ship

## Summary

`tests/test_integration_shells.py` is the only place a generated hook meets a real
shell. It covers three of seven shells, and none of its four tests actually calls an
alias defined by the hook — they call `qwik run` instead, which does not exercise the
rendered output at all. The bash test's assertion accepts three different exit codes,
including failure.

This is why the fish renderer (**B1**) and the xonsh renderer (**B2**) shipped
completely non-functional with a green suite.

## Motivation

The renderers are the project's product. Everything else — the store, the picker, the
substitution engine — exists to feed them. They are also the component that cannot be
verified by unit tests or snapshots, because the only question that matters is whether
the target shell accepts the output, and the snapshot tests
(`tests/__snapshots__/test_shell_snapshots.ambr`) currently pin the *broken* fish
output as correct.

The suite reports 449 passing tests and 87% coverage. Both fish and xonsh are
completely broken. That gap is the finding.

## Repro Steps

Which shells are covered:

```
grep -n "^def test_" tests/test_integration_shells.py
```

```
40:def test_bash_hook_runs_alias
56:def test_zsh_hook_runs_alias
70:def test_fish_hook_runs_alias
84:def test_pwsh_hook_runs_alias
```

No `nu`, `xonsh`, or `cmd` test exists — all three were added in v1.0.0.

What the tests assert:

```
grep -n "assert" tests/test_integration_shells.py
```

```
52:    assert result.returncode in (0, 1, 128)
66:    assert "git checkout main" in result.stdout or "git checkout" in result.stderr
80:    assert "git checkout main" in result.stdout or "git checkout" in result.stderr
94:    assert "git checkout main" in result.stdout or "git checkout" in result.stderr
```

Line 52 passes on success, on generic failure, and on signal death.

Lines 66/80/94 test the alias `gco` — a **template** alias, whose generated definition
is a wrapper that shells out to `qwik run`. So the assertion passes as long as
`qwik run` works, regardless of whether the shell-specific rendering is correct. The
append-mode alias `gs` is created by the fixture (`test_integration_shells.py:34`)
and never invoked by any test — and append mode is exactly where B1 lives.

Demonstration that the fish test passes while fish is broken:

```
pytest tests/test_integration_shells.py::test_fish_hook_runs_alias -q   # passes
fish -c "source <(qwik init fish); gs"                                  # Unknown command
```

## Root Cause

Three compounding gaps:

1. **Wrong alias under test.** Every assertion targets the template alias, whose
   rendering delegates to `qwik run` in every shell. Testing it proves the substitution
   engine works — which the unit tests already prove — and proves nothing about the
   renderer.
2. **Assertions too weak to fail.** `returncode in (0, 1, 128)` cannot detect a broken
   hook. The `or "git checkout" in result.stderr` clause in the other three means an
   error message mentioning `git checkout` also satisfies the test.
3. **Silent skips.** Each test opens with `if not _shell_available(...): pytest.skip`.
   On a machine without fish, the fish test skips green. Nothing in CI asserts that
   the shells were present, so a CI image change that drops a shell silently reduces
   coverage — and `fail-fast: false` in the matrix means it would not be noticed.

Recommended shape:

- Test the **append-mode** alias in every shell, asserting on its exact stdout.
- Test the **template** alias too, asserting the expanded command's output.
- Test at least one adversarial command per shell (see **B12**'s matrix).
- Install the shells in CI (`apt-get install fish zsh nushell`, `pipx install xonsh`,
  pwsh on the Windows/macOS runners) and make a skip **fail** on CI via an env flag
  like `QWIK_REQUIRE_SHELLS=1`, so a missing shell is a CI error rather than a silent
  pass.
- Add cmd coverage on the Windows runner.

## Acceptance Criteria

- Every registered renderer has an integration test that sources the hook in the real
  shell and invokes both an append-mode and a template alias
- Assertions compare exact expected stdout, with no `or`-clauses on stderr and no
  multi-value exit-code allowances
- CI installs all testable shells and fails when one is missing rather than skipping
- The fish snapshot in `test_shell_snapshots.ambr` is regenerated after **B1** lands
- Windows CI exercises the cmd and pwsh renderers end to end
- Reverting the **B1** fix makes the fish test fail — verify this explicitly when
  writing it

## Suggested Labels

`chore`, `testing`, `shells`

---
---

# B21 · [Chore] ruff runs in pre-commit but not CI; Sonar action pinned to `@master`; publish still uses a long-lived PyPI token

## Summary

Three unrelated CI/release hygiene gaps, grouped because they touch the same three
workflow files:

1. `ruff` is configured in `.pre-commit-config.yaml` but runs in no workflow; the
   tree currently has 165 violations.
2. `.github/workflows/sonarqube.yml` pins `SonarSource/sonarqube-scan-action@master`
   — a mutable ref with `SONAR_TOKEN` in scope.
3. `.github/workflows/publish.yml` authenticates to PyPI with a long-lived
   `PYPI_API_TOKEN`, despite v1.0.0 being released as "OIDC publishing".

## Motivation

**Lint.** A linter that only runs when a contributor has installed pre-commit locally
is advisory. The 165 outstanding violations include real signal — 7 unused imports,
4 unused variables, 14 blind `except`, 7 `subprocess.run` calls without `check` — mixed
into style noise, and the pile only grows while nothing enforces it.

**Sonar action.** `@master` re-resolves on every run. Anyone who can push to that
branch, upstream or via a compromised maintainer account, executes code in a job that
holds `SONAR_TOKEN` and a `GITHUB_TOKEN`. This is the standard supply-chain pattern
the GitHub hardening guidance calls out; the repo already pins every other action to a
major version (`actions/checkout@v4`, `actions/setup-python@v5`), so this one is an
outlier rather than a policy.

**PyPI token.** The v1.0.0 release commit is titled "M5 ecosystem & growth — plugins,
overlay store, TUI, Nushell/Xonsh, OIDC publishing", but `publish.yml` has no
`id-token: write` permission and uses `twine upload` with
`TWINE_PASSWORD: ${{ secrets.PYPI_API_TOKEN }}`. A long-lived token that can publish
to PyPI is a materially worse artifact to hold than a short-lived OIDC credential, and
the release notes claim otherwise.

**Publish-time testing is also weaker than PR-time testing.** `publish.yml` runs
`pytest -v` on ubuntu/3.12 only and does not run mypy — so a release can ship a
configuration the PR gate would have rejected.

## Repro Steps

```
ruff check qwik tests --statistics | head
```

```
36  UP037    quoted-annotation
34  I001     unsorted-imports
20  UP017    datetime-timezone-utc
14  BLE001   blind-except
12  UP045    non-pep604-annotation-optional
10  RUF022   unsorted-dunder-all
 7  F401     unused-import
 7  PLW1510  subprocess-run-without-check
 4  B008     function-call-in-default-argument
 4  F841     unused-variable
...
Found 165 errors.
```

```
grep -rn "uses:" .github/workflows/
```

```
.github/workflows/sonarqube.yml: uses: SonarSource/sonarqube-scan-action@master
```

```
grep -n "id-token\|TWINE_PASSWORD\|permissions" .github/workflows/publish.yml
```

```
permissions:
  contents: read
TWINE_PASSWORD: ${{ secrets.PYPI_API_TOKEN }}
```

No `id-token: write`, so Trusted Publishing is not in use.

## Root Cause

- No workflow step invokes ruff; `ruff` is absent from the `dev` extra in
  `pyproject.toml`, and there is no `[tool.ruff]` section, so it runs on defaults with
  no agreed rule set.
- `sonarqube.yml` was written against the action's `master` branch and never pinned.
- `publish.yml` predates the OIDC work and was not updated when the milestone claimed
  it.

## Acceptance Criteria

**Lint**
- A `[tool.ruff]` section in `pyproject.toml` fixes the rule set and target version
- `ruff` added to the `dev` extra, pinned to the pre-commit version
- `ruff check` and `ruff format --check` run in `test.yml`
- The existing 165 violations are either fixed or explicitly ignored in config, so the
  gate starts green

**Actions**
- `SonarSource/sonarqube-scan-action` pinned to a release tag or commit SHA
- A `github-actions` ecosystem entry in `.github/dependabot.yml` so pins get updated

**Release**
- `publish.yml` uses PyPI Trusted Publishing (`id-token: write` +
  `pypa/gh-action-pypi-publish`) and `PYPI_API_TOKEN` is revoked, or the v1.0.0
  release notes are corrected to say token-based publishing
- `publish.yml` runs the same gates as `test.yml` (full matrix or an explicit
  `needs:` on the test workflow) before uploading

## Suggested Labels

`chore`, `ci`, `security`

---
---

# B22 · [Bug] `qwik init` adds ~300 ms to every shell start — prompt_toolkit and pydantic are imported eagerly

## Summary

The shell hook runs `eval "$(qwik init bash)"` on every new shell. That invocation
takes ~300 ms, most of it spent importing modules `init` never uses — the entire
`prompt_toolkit` TUI stack is pulled in because `qwik/cli.py` imports every command
module at module scope, including the picker.

## Motivation

300 ms is well past the threshold where a shell feels sluggish; it is roughly the
entire startup budget people spend effort trimming out of their `.zshrc`. It is paid
on every terminal, every split, every `tmux` pane, every subshell that sources the rc.

The cost is also almost entirely avoidable — nothing in the `init` code path needs a
TUI framework. The command loads the store, picks a renderer, and prints strings.

There is a second multiplier: `qwik/shells/base.py:32` runs
`SUPPORTED_SHELLS = supported_shells()` at **import** time, which scans installed
distribution metadata for the `qwik.shell_renderers` entry-point group. `get_renderer`
then re-scans on every call (`base.py:107`). Entry-point discovery is a filesystem
walk over site-packages; doing it at import time means every `qwik` invocation pays it
whether or not a renderer is needed.

`qwik/cli.py:88` likewise calls `_discover_plugin_commands()` at import time, scanning
a second entry-point group and `ep.load()`-ing every plugin found — so third-party
plugin code is imported and executed on every `qwik --version`.

## Repro Steps

```
export QWIK_CONFIG_DIR=$(mktemp -d)
qwik add gs "git status"

python - <<'EOF'
import subprocess, time
t = [ ]
for _ in range(5):
    s = time.perf_counter()
    subprocess.run(["qwik", "init", "bash"], capture_output=True)
    t.append(time.perf_counter() - s)
print(f"min={min(t)*1000:.0f}ms avg={sum(t)/len(t)*1000:.0f}ms")
EOF
```

```
min=300ms avg=313ms
```

Where it goes:

```
python -X importtime -c "import qwik.cli" 2>&1 | sort -t'|' -k2 -rn | head -8
```

```
    2580 |     261194 | qwik.cli
     565 |     120962 |   qwik.commands.add
     285 |      87565 |     qwik.core.conflicts
    8561 |      87220 |       qwik.core.models          ← pydantic
     165 |      81571 |   qwik.commands.pick
     202 |      81406 |     qwik.ui.picker
     144 |      72444 |       prompt_toolkit            ← TUI stack, unused by init
     323 |      30974 |   typer
```

~72 ms of `prompt_toolkit` and ~87 ms of pydantic are imported to print a list of
`alias` lines.

## Root Cause

`qwik/cli.py:11-29` imports all 22 command modules at module scope so they can be
registered with `app.command(...)`. Importing `qwik.commands.pick` (`cli.py:22`)
transitively imports `qwik.ui.picker`, which imports `prompt_toolkit.Application`,
`.buffer`, `.layout`, `.styles`, and `.key_binding` at module scope
(`qwik/ui/picker.py:8-20`).

Standard remedies, in rough order of payoff:

1. **Lazy command loading** — register commands via a Typer/Click lazy-group so a
   command module is imported only when its name is invoked. This alone removes
   `prompt_toolkit` from every non-`pick` invocation.
2. **Move heavy imports into function bodies** — `qwik/ui/picker.py` can import
   `prompt_toolkit` inside `run_picker`. The codebase already uses this idiom for
   `has_placeholders` in every renderer.
3. **Cache entry-point discovery** — `functools.cache` on `supported_shells()` and a
   dict lookup in `get_renderer`, and make `SUPPORTED_SHELLS` lazy rather than a
   module-level constant.
4. **Defer plugin discovery** — `_discover_plugin_commands()` should not run for
   `--version`, `--help`, or `init`.
5. **A fast path for `init`** — the hook does not need the full Typer app; a
   short-circuit in `__main__` for `init` would cut Typer's own ~31 ms too.

A target of **under 80 ms** for `qwik init <shell>` is realistic with 1–3 alone.

## Acceptance Criteria

- `qwik init <shell>` completes in under 80 ms on a warm cache with a 100-alias store
- `python -X importtime -c "import qwik.cli"` shows no `prompt_toolkit` import
- `qwik pick` still works, with the TUI imported on demand
- Entry-point discovery happens at most once per process, and not at import time
- Plugin command modules are not imported for `qwik --version`
- A benchmark test under the existing `benchmark` marker that asserts a startup
  ceiling, so this cannot silently regress
- README notes the measured shell-startup cost of the hook

## Suggested Labels

`bug`, `performance`, `dx`, `shells`
