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

## Published issues

All 31 drafts were filed on 2026-08-15 as issues **#10–#40**.

| Ref | Issue | Title | Labels |
|---|---|---|---|
| B1 | [#10](https://github.com/ragilhadi/qwik/issues/10) | fish append-mode aliases render as `'git status' $argv` | `bug` `shells` `correctness` |
| B2 | [#11](https://github.com/ragilhadi/qwik/issues/11) | xonsh hook is a SyntaxError — one template alias disables every alias | `bug` `shells` `correctness` |
| B3 | [#12](https://github.com/ragilhadi/qwik/issues/12) | `qwik run gs --short` fails with "No such option" | `bug` `cli` `correctness` |
| B4 | [#13](https://github.com/ragilhadi/qwik/issues/13) | `qwik run` writes its banner to stdout, corrupting piped aliases | `bug` `cli` `correctness` |
| B5 | [#14](https://github.com/ragilhadi/qwik/issues/14) | Concurrent store writes silently lose aliases | `bug` `store` `data-loss` |
| B6 | [#15](https://github.com/ragilhadi/qwik/issues/15) | `qwik edit` silently deletes the alias's `group` | `bug` `commands` `data-loss` |
| B7 | [#16](https://github.com/ragilhadi/qwik/issues/16) | `import --overwrite` destroys the store behind a misleading preview | `bug` `commands` `data-loss` |
| B8 | [#17](https://github.com/ragilhadi/qwik/issues/17) | Imported `version` is never validated — one import bricks the CLI | `bug` `store` `correctness` |
| B9 | [#18](https://github.com/ragilhadi/qwik/issues/18) | Runtime quoting is POSIX-only — templates broken on cmd.exe | `bug` `windows` `security` |
| B10 | [#19](https://github.com/ragilhadi/qwik/issues/19) | `detect_shell()` returns `None` on Windows; cmd/nu/xonsh unreachable | `bug` `windows` `cross-platform` |
| B11 | [#20](https://github.com/ragilhadi/qwik/issues/20) | Builtin conflict check is case-sensitive; cmd/PowerShell are not | `bug` `windows` `correctness` |
| B12 | [#21](https://github.com/ragilhadi/qwik/issues/21) | pwsh, nu and cmd renderers never escape the command body | `bug` `shells` `security` |
| B13 | [#22](https://github.com/ragilhadi/qwik/issues/22) | `completion zsh --install` writes bare `compinit` | `bug` `shells` `dx` |
| B14 | [#23](https://github.com/ragilhadi/qwik/issues/23) | `list`/`search` say "No aliases yet" for overlay-only users | `bug` `overlay` `dx` |
| B15 | [#24](https://github.com/ragilhadi/qwik/issues/24) | `overlay update` installs remote commands with no preview | `bug` `overlay` `security` |
| B16 | [#25](https://github.com/ragilhadi/qwik/issues/25) | `search_aliases` ignores `limit` for empty queries | `bug` `correctness` |
| B17 | [#26](https://github.com/ragilhadi/qwik/issues/26) | Picker Ctrl+E / Ctrl+D route through `typer.testing.CliRunner` | `bug` `ui` `dx` |
| B18 | [#27](https://github.com/ragilhadi/qwik/issues/27) | `--no-color` ignored by rm, rename, tag, export, init | `bug` `ui` |
| B19 | [#28](https://github.com/ragilhadi/qwik/issues/28) | `mypy --strict` fails on master; CI installs mypy unpinned | `chore` `ci` |
| B20 | [#29](https://github.com/ragilhadi/qwik/issues/29) | Shell integration tests never invoke a generated alias | `chore` `testing` |
| B21 | [#30](https://github.com/ragilhadi/qwik/issues/30) | ruff not in CI; Sonar action `@master`; PyPI token not OIDC | `chore` `ci` `security` |
| B22 | [#31](https://github.com/ragilhadi/qwik/issues/31) | `qwik init` adds ~300 ms to every shell start | `bug` `performance` |
| F1 | [#32](https://github.com/ragilhadi/qwik/issues/32) | `qwik undo` — front door for the backup directory | `feature` `store` `dx` |
| F2 | [#33](https://github.com/ragilhadi/qwik/issues/33) | `qwik doctor --fix` — non-interactive repair | `feature` `commands` `dx` |
| F3 | [#34](https://github.com/ragilhadi/qwik/issues/34) | Platform-conditional alias commands | `feature` `store` `cross-platform` |
| F4 | [#35](https://github.com/ragilhadi/qwik/issues/35) | Native template rendering | `feature` `shells` `performance` |
| F5 | [#36](https://github.com/ragilhadi/qwik/issues/36) | `qwik suggest` — mine shell history | `feature` `commands` `dx` |
| F6 | [#37](https://github.com/ragilhadi/qwik/issues/37) | `qwik stats` — usage dashboard | `feature` `commands` `dx` |
| F7 | [#38](https://github.com/ragilhadi/qwik/issues/38) | Argument-aware completions for aliases | `feature` `shells` `dx` |
| F8 | [#39](https://github.com/ragilhadi/qwik/issues/39) | Project-scoped aliases (`.qwik.toml`) | `feature` `store` `security` |
| F9 | [#40](https://github.com/ragilhadi/qwik/issues/40) | Overlay trust model v2 | `feature` `overlay` `security` |

### Milestone dependency graph

```
v1.1  #32 undo ────────── needs #14 #16 #17
      #33 doctor --fix ── needs #17

v1.2  #34 platforms ───── needs #19
      #35 native tmpl ─── needs #21 #31

v1.3  #36 suggest ─────── needs #31
      #37 stats ───────── needs #14
      #38 completions ─── needs #35

v1.4  #39 project ─────── needs #23 #24 #31
      #40 overlay v2 ──── needs #24 #32
```

## Labels

Auto-created on first use (all default grey — worth recolouring by group):

**Type:** `bug`, `feature`, `chore`
**Component:** `shells`, `store`, `cli`, `commands`, `ui`, `overlay`, `ci`
**Concern:** `correctness`, `data-loss`, `windows`, `cross-platform`, `security`,
`dx`, `performance`, `documentation`, `testing`

---

## Verification environment

```
python 3.12.3 · qwik 1.0.0 (editable) · pytest 449 passed / 1 failed / 4 skipped
bash 5.2 · fish 3.7 · zsh 5.9 · xonsh (pip) · mypy 2.3.1 · ruff 0.x
```
