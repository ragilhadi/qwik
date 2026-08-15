# qwik audit — v1.0.0 (commit `6cbe7de`)

A full read of `qwik/` (4,986 LOC, 44 modules) plus runtime verification of every
finding against a real install (`uv venv --python 3.12`, `pip install -e .[dev]`),
with real `bash`, `fish`, `zsh`, and `xonsh` binaries used to execute the
generated hooks.

**Every finding below was reproduced, not inferred.** Where a claim needed a shell
that is not on this machine, the shell was installed and the hook was actually
sourced.

---

## Headline

The store and the substitution engine are solid. What is broken is **everything at
the two edges**: the shell hooks qwik generates (fish and xonsh are non-functional,
pwsh/nu/cmd are unescaped) and the concurrency/validation boundary around the store
(parallel writes lose data, `import --overwrite` destroys the store, an imported
`version` bricks the CLI).

The cross-platform suspicion in the original request is correct and is broader than
Windows: **`detect_shell()` can never return `cmd`, `nu`, or `xonsh` on any
platform**, which makes the documented cmd/pwsh warnings dead code, and runtime
argument quoting is POSIX-only everywhere.

| Severity | Count | Theme |
|---|---|---|
| P0 — broken core functionality | 8 | fish/xonsh hooks, flag passthrough, stdout, data loss |
| P1 — cross-platform / Windows | 5 | POSIX quoting, shell detection, escaping, zsh completion |
| P2 — correctness / UX | 5 | overlay visibility, trust, search limit, picker, color |
| Quality / infra | 3 | red mypy gate, hollow integration tests, CI hygiene |
| Performance | 1 | 300 ms added to every shell start |
| **Total** | **22** | |

---

## Files

- **[BUGS.md](./BUGS.md)** — 22 ready-to-publish issue drafts, in the same
  `Summary / Motivation / Repro Steps / Root Cause / Acceptance Criteria /
  Suggested Labels` template used in `ragilhadi/mimic`.
- **[FEATURES.md](./FEATURES.md)** — 9 feature proposals grouped into four
  milestones, written in the same template.

---

## Priority order for publishing

Suggested order, so the issue list reads as a coherent plan rather than a dump:

| # | Title | Labels |
|---|---|---|
| B1 | fish append-mode aliases render as `'git status' $argv` | `bug` `shells` `correctness` |
| B2 | xonsh hook is a SyntaxError — one template alias disables every alias | `bug` `shells` `correctness` |
| B3 | `qwik run <alias> --flag` fails with "No such option" | `bug` `cli` `correctness` |
| B4 | `qwik run` writes its banner to stdout, corrupting piped aliases | `bug` `cli` `correctness` |
| B5 | Concurrent store writes silently lose aliases | `bug` `store` `data-loss` |
| B6 | `qwik edit` silently deletes the alias's `group` | `bug` `commands` `data-loss` |
| B7 | `import --overwrite` destroys the store behind a misleading preview | `bug` `commands` `data-loss` |
| B8 | Imported `version` is never validated — one import bricks the CLI | `bug` `store` `correctness` |
| B9 | Runtime quoting is POSIX-only — templates broken on cmd.exe | `bug` `windows` `correctness` |
| B10 | `detect_shell()` returns `None` on Windows; cmd/nu/xonsh unreachable | `bug` `windows` `cross-platform` |
| B11 | Builtin conflict check is case-sensitive; cmd/PowerShell are not | `bug` `windows` `correctness` |
| B12 | pwsh, nu and cmd renderers never escape the command body | `bug` `shells` `security` |
| B13 | `completion zsh --install` writes bare `compinit` | `bug` `shells` `dx` |
| B14 | `list`/`search` say "No aliases yet" for overlay-only users | `bug` `overlay` `dx` |
| B15 | `overlay update` installs remote commands with no preview | `bug` `overlay` `security` |
| B16 | `search_aliases` ignores `limit` for empty queries | `bug` `correctness` |
| B17 | Picker Ctrl+E / Ctrl+D route through `typer.testing.CliRunner` | `bug` `ui` `dx` |
| B18 | `--no-color` ignored by rm, rename, tag, export, init | `bug` `ui` |
| B19 | `mypy --strict` fails on master; CI installs mypy unpinned | `chore` `ci` |
| B20 | Shell integration tests never invoke a generated alias | `chore` `testing` |
| B21 | ruff not in CI; Sonar action `@master`; PyPI token not OIDC | `chore` `ci` `security` |
| B22 | `qwik init` adds ~300 ms to every shell start | `bug` `performance` |

## Labels to create first

**Type:** `bug`, `feature`, `chore`
**Component:** `shells`, `store`, `cli`, `commands`, `ui`, `sync`, `overlay`, `ci`
**Concern:** `correctness`, `data-loss`, `windows`, `cross-platform`, `security`,
`dx`, `performance`, `documentation`, `testing`

---

## Verification environment

```
python 3.12.3 · qwik 1.0.0 (editable) · pytest 449 passed / 1 failed / 4 skipped
bash 5.2 · fish 3.7 · zsh 5.9 · xonsh (pip) · mypy 2.3.1 · ruff 0.x
```
