# Milestone 5 — Ecosystem & Growth (v1.0.0) Design

## Overview

Milestone 5 completes qwik's journey to 1.0-readiness with six features from `PLAN.MD` lines 92-101:

1. Plugin/hook extensibility (entry-point-based renderers/commands)
2. Team/shared read-only overlay store (remote git URL, merged beneath user store)
3. TUI enhancements (command history view, richer preview, selection stability)
4. Nushell/Xonsh shell renderers
5. Performance: benchmark fuzzy search, optimize if needed
6. PyPI trusted publishing (OIDC) + 1.0.0 release

Decomposed into 3 PRs:

- **PR1 (v0.5.0):** Plugin system + Nushell/Xonsh renderers
- **PR2 (v0.6.0):** Overlay store + TUI enhancements + performance
- **PR3 (v1.0.0):** PyPI OIDC publishing + 1.0.0 release bump

No new runtime dependencies required. All features use stdlib (`importlib.metadata`), existing libs, or the official PyPI GitHub Action.

---

## PR1 — Plugin System + Nushell/Xonsh Renderers (v0.5.0)

### Entry-Point Registration

Add two entry-point groups to `pyproject.toml`:

```toml
[project.entry-points."qwik.shell_renderers"]
bash  = "qwik.shells.bash:BashRenderer"
zsh   = "qwik.shells.zsh:ZshRenderer"
fish  = "qwik.shells.fish:FishRenderer"
pwsh  = "qwik.shells.pwsh:PwshRenderer"
cmd   = "qwik.shells.cmd:CmdRenderer"
nu    = "qwik.shells.nu:NuRenderer"
xonsh = "qwik.shells.xonsh:XonshRenderer"
```

Built-in CLI commands remain statically registered in `cli.py` for mypy-friendliness and fast import. A `[project.entry-points."qwik.commands"]` group is reserved for future third-party commands; `cli.py` discovers and registers them dynamically after built-ins.

### ShellRenderer ABC Extensions

Extend `qwik/shells/base.py` `ShellRenderer` with two optional methods so plugins self-contain their rc-path and install-hook logic:

```python
class ShellRenderer(ABC):
    # existing abstract methods and defaults remain

    def rc_path(self) -> Path | None:
        """RC file path for this shell. Return None to skip --install."""
        return None

    def install_hook_line(self) -> str | None:
        """Hook line to write into rc file. Return None to skip --install."""
        return None
```

Each built-in renderer implements `rc_path()` and `install_hook_line()`, replacing the hardcoded `_rc_path` function and `hook_line` construction in `commands/init_shell.py`. `init_shell` becomes shell-agnostic: it calls `get_renderer(shell)`, gets `rc_path()` and `install_hook_line()`, and writes the hook. Third-party plugins implement these methods in their own renderer class with zero core edits.

### get_renderer Rewrite

`qwik/shells/base.py`:

```python
def get_renderer(shell: str) -> ShellRenderer:
    for ep in importlib.metadata.entry_points(group="qwik.shell_renderers"):
        if ep.name == shell:
            return ep.load()()
    raise ValueError(f"Unknown shell: {shell!r}")
```

### SUPPORTED_SHELLS Becomes Dynamic

```python
def supported_shells() -> tuple[str, ...]:
    return tuple(sorted(
        ep.name for ep in importlib.metadata.entry_points(group="qwik.shell_renderers")
    ))
```

Callers updated:
- `doctor.py:80` — `if shell not in supported_shells()`
- `init_shell.py` help text — dynamically generated from `supported_shells()`
- `test_shells.py:11`, `test_shell_snapshots.py:25` — iterate `supported_shells()`

### init_shell.py Refactor

Current `_rc_path(shell)` function (lines 32-70) and `hook_line` construction (lines 120-124) are removed. `init_shell_command` becomes:

1. `renderer = get_renderer(shell)`
2. `rc = renderer.rc_path()` — if `None`, error: "Shell {shell} does not support --install"
3. `hook = renderer.render_all(store.aliases)`
4. Write hook to rc file (with backup + idempotent markers, as now)
5. Print install instructions using `renderer.install_hook_line()`

### NushellRenderer (shells/nu.py, ~50 lines)

- `shell_name = "nu"`
- Template mode: `def name [...args] { qwik run "name" ...$args }`
- Append mode: `def name [...args] { ^command ...$args }` (Nushell external command prefix `^`)
- `rc_path()`: `$env.NU_CONFIG_DIR` env var, fallback `~/.config/nushell/config.nu` (Windows: `~/AppData/Roaming/nushell/config.nu` via `platformdirs`)
- `install_hook_line()`: `source (qwik init nu | into string)` — Nushell's source equivalent
- `render_header()`: `# qwik aliases — managed by qwik init` (comment header)

### XonshRenderer (shells/xonsh.py, ~40 lines)

- `shell_name = "xonsh"`
- Template mode: `def name(*args): qwik run("name", *args)` (xonsh is Python-syntax shell)
- Append mode: `aliases["name"] = "command"` (xonsh supports string aliases directly)
- `rc_path()`: `$XONSHRC` env var, fallback `~/.xonshrc`
- `install_hook_line()`: `execx($(qwik init xonsh))` — xonsh's exec expression
- `render_header()`: `# qwik aliases — managed by qwik init`

### CLI Command Plugin Discovery

In `cli.py`, after static built-in registration:

```python
def _discover_plugin_commands() -> None:
    for ep in importlib.metadata.entry_points(group="qwik.commands"):
        try:
            cmd = ep.load()
            app.command(ep.name)(cmd)
        except Exception as exc:
            # Non-fatal: warn but don't crash on bad plugins
            import sys
            print(f"Warning: failed to load plugin command {ep.name!r}: {exc}", file=sys.stderr)

_discover_plugin_commands()
```

### Tests

- `test_shell_snapshots.py`: add `nu` and `xonsh` snapshot cases (5 aliases each, same as existing shells)
- `test_shells.py`: `get_renderer` entry-point discovery test (mock `entry_points`), `supported_shells()` test
- `test_init_shell.py`: `init_shell` with plugin renderer (rc_path/install_hook_line), nu/xonsh rc_path tests (Windows/Linux)
- `test_plugin_commands.py`: mock entry-point command registration, verify app has the command
- Direct renderer tests: `test_nu_renderer.py`, `test_xonsh_renderer.py` (template/append modes, header, footer)

---

## PR2 — Overlay Store + TUI + Performance (v0.6.0)

### 2a. Team/Shared Read-Only Overlay Store

#### Concept

A remote git repository contains an `aliases.toml` (qwik export format). The user adds it once via `qwik overlay add <url>`. On every command that reads the store, qwik merges the overlay beneath the user store (user-wins precedence). Overlay aliases are read-only. Running an overlay alias copies it to the user store (copy-on-run) so `bump_usage` works normally.

#### Config

Separate `<config_dir>/overlay.toml`:

```toml
url = "https://github.com/team/qwik-aliases"
branch = "main"
auto_update = true
```

New `Config` properties:
- `overlay_config_file` → `<config_dir>/overlay.toml`
- `overlay_repo_dir` → `<config_dir>/overlay-repo/`
- `overlay_aliases_file` → `<config_dir>/overlay-repo/aliases.toml`

#### Commands

- `qwik overlay add <url> [--branch main]` — clones to `overlay_repo_dir`, records config in `overlay.toml`
- `qwik overlay remove` — removes overlay config + deletes `overlay_repo_dir`
- `qwik overlay update` — `git pull` in `overlay_repo_dir`
- `qwik overlay list` — shows overlay aliases with `[overlay]` marker
- `qwik overlay copy <name>` — copies an overlay alias into the user store explicitly

#### AliasStore Extension

`AliasStore` gets a new field:

```python
class AliasStore(BaseModel):
    version: int = 1
    aliases: dict[str, Alias] = {}
    overlay_aliases: dict[str, Alias] = {}  # read-only, not persisted
```

`overlay_aliases` is excluded from serialization (not written to `aliases.toml`). A new `all_aliases()` property returns `{**overlay_aliases, **aliases}` (user wins). Downstream code uses `all_aliases()` for search, render, pick — giving a merged view.

#### Load-Time Merge

`Store.load()` gains `include_overlay: bool = True` parameter. When true:

1. Load user store normally (migrate + validate)
2. If `overlay_config_file` exists and `auto_update` is true, attempt `git pull` in `overlay_repo_dir` (non-fatal on failure — warn and continue). Throttled: skip pull if last pull was < 5 minutes ago (tracked via mtime of a `<overlay_repo_dir>/.last_update` sentinel file)
3. Load `overlay_aliases_file` → validate as `AliasStore` (migrate + validate)
4. Merge: for each alias in overlay not present in user store, add to `store.overlay_aliases`
5. Return merged store

Network failures during load are non-fatal. If overlay fetch fails, warn and continue with user store only.

#### Copy-on-Run

`commands/run.py` checks if the alias is overlay-only (`name in store.overlay_aliases and name not in store.aliases`). If so, copies it to the user store before `bump_usage`. This makes the user store the source of truth for usage data.

#### Overlay Alias Protection

`rm`, `edit`, `rename` commands check:

```python
if name in store.overlay_aliases and name not in store.aliases:
    print_error(f"{name!r} is an overlay alias (read-only). "
                f"Copy it first: qwik overlay copy {name}")
    raise typer.Exit(1)
```

#### Sync vs Overlay

`sync` is personal dotfile sharing (your store to your other machines, bidirectional). `overlay` is team sharing (read-only, one-directional). Different commands, different config, different semantics.

#### Tests

- `test_overlay.py`: add/remove/update/list commands, config persistence
- `test_overlay_merge.py`: load-time merge, user-wins precedence, overlay-only alias protection
- `test_overlay_copy_on_run.py`: run overlay alias → copied to user store → bump_usage works
- `test_overlay_errors.py`: network failure (non-fatal), corrupt overlay file (non-fatal), missing overlay config (no overlay)
- `test_overlay_cli.py`: CLI-level `qwik overlay` subcommands via CliRunner

### 2b. TUI Enhancements

#### History View (Ctrl-R)

New `Ctrl-R` keybinding toggles "recent" mode in the picker:

- `Ctrl-R`: switch results to aliases sorted by `last_used` (descending), showing `format_last_used()` in the result line
- `Ctrl-R` again: back to search mode
- In recent mode, typing still filters (search within recents)

`_PickerState` gains:

```python
self.history_mode: bool = False
```

When `history_mode` is true, `_refresh` calls `search_aliases` with the query, then re-sorts results by `last_used` instead of score.

#### Richer Preview

Extend `_get_preview_lines` to show all `Alias` fields:

```
  Name:    gco
  Cmd:     git checkout {1}
  Group:   git
  Tag:     vcs, checkout
  Used:    42 times (last: 2 hours ago)
  Created: 2026-01-15
  Enabled: yes
  Desc:    Checkout a git branch
```

Uses existing `Alias` fields + `format_last_used()`. Fields with no value (empty description, no group) show `—`.

#### Selection Stability

`_refresh` preserves selection by name across keystrokes instead of resetting to index 0:

1. Before refresh, record `current_name = state.results[state.selected_index][0]` (if results non-empty)
2. After refresh, find `current_name` in new results; set `selected_index` to its position
3. If not found, clamp to last index (name scrolled off results)

#### Tests

- `test_picker.py`: extend existing harness with:
  - `Ctrl-R` toggles history mode, shows recent-first
  - Preview shows all fields (name, cmd, group, tags, used, created, enabled, desc)
  - Selection preserved across keystrokes (type a char, verify selected_name unchanged)
  - Overlay aliases appear in picker with `[overlay]` marker in result line

### 2c. Performance Benchmark

#### Benchmark Test

`tests/benchmarks/test_search_perf.py`:

- Generate 1000/5000/10000 aliases with realistic names/commands
- Measure `search_aliases` latency per call (warm cache, median of 10 runs)
- Measure `_refresh` full cycle (search + rebuild)
- Assert per-keystroke latency < 50ms at 1000 aliases, < 200ms at 10000

Marked `@pytest.mark.benchmark` (excluded from default CI run, run manually or in a dedicated benchmark job).

#### Optimization (Only If Benchmark Fails)

1. **Early-exit in `score_alias`**: check `name_score` first, skip remaining signals if < 30
2. **Cache candidate list**: module-level cache keyed by `id(store)` + filter params, invalidated on store mutation
3. **Precompute lowercased fields**: build `{name: (name_lower, tags_lower, group_lower, field_text)}` on first search, reuse across keystrokes
4. **Picker debounce**: if >50ms even after search optimization, add 30ms debounce in `_refresh` via `event.app.create_background_task` + `asyncio.sleep`

#### Tests

- `test_search_perf.py`: benchmark assertions (skipped if < 1000 aliases in store)
- Optimization tests: cache invalidation on store mutation, early-exit behavior, precomputed index correctness

---

## PR3 — PyPI Trusted Publishing + 1.0.0 Release (v1.0.0)

### PyPI Trusted Publishing (OIDC)

#### publish.yml Rewrite

Split into 3 jobs: `test` (matrix), `build`, `publish`.

```yaml
name: Build & Publish to PyPI

on:
  release:
    types: [published]
  workflow_dispatch:

permissions:
  contents: read

jobs:
  test:
    runs-on: ${{ matrix.os }}
    strategy:
      fail-fast: false
      matrix:
        os: [ubuntu-latest, macos-latest, windows-latest]
        python-version: ["3.12", "3.13"]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}
      - run: |
          python -m pip install --upgrade pip
          pip install .[dev] mypy
      - run: mypy qwik
      - run: pytest -q

  build:
    needs: test
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install build
      - run: python -m build
      - uses: actions/upload-artifact@v4
        with:
          name: dist
          path: dist/

  publish:
    needs: build
    runs-on: ubuntu-latest
    environment: pypi
    permissions:
      contents: read
      id-token: write
    steps:
      - uses: actions/download-artifact@v4
        with:
          name: dist
          path: dist/
      - uses: pypa/gh-action-pypi-publish@release/v1
        with:
          attestations: true
```

#### Key Changes

- Split into 3 jobs: `test` (matrix), `build`, `publish`
- `publish` job has `environment: pypi` (PyPI-side environment gating + optional required reviewers)
- `permissions: id-token: write` on the publish job (required for OIDC)
- Uses `pypa/gh-action-pypi-publish@release/v1` (official action, handles OIDC token exchange)
- `attestations: true` for PEP 740 provenance (supply-chain hygiene for 1.0)
- Removes `PYPI_API_TOKEN` secret entirely
- Removes inline `pytest` from publish workflow (now in `test` job with proper matrix)
- Test job duplicates `test.yml` content — acceptable for reliability (publish shouldn't proceed if tests fail, even if `test.yml` had a transient issue)

#### PyPI Setup (Manual, Outside Code)

- Create `qwik` project on PyPI (or confirm it exists)
- Add GitHub Actions publisher: owner=`ragilhadi`, repo=`qwik`, workflow=`publish.yml`, environment=`pypi`
- Add `Programming Language :: Python :: 3.13` classifier

### 1.0.0 Release Bump

- `pyproject.toml`: version → `1.0.0`
- `qwik/__init__.py`: `__version__ = "1.0.0"`
- `pyproject.toml` classifier: `Development Status :: 5 - Production/Stable`
- `CHANGELOG.md`: new `## [1.0.0]` section summarizing all M5 changes

### README/Docs Updates

- Remove "not published" caveat from README (it now IS on PyPI)
- Add `qwik overlay` command docs
- Add `qwik completion` command docs (already shipped in M3 but may not be in README)
- Add Nushell/Xonsh to the supported shells list
- Document the plugin system (`[project.entry-points."qwik.shell_renderers"]` and `"qwik.commands"`) for third-party developers

### Tests

- `test_version.py`: assert `__version__ == "1.0.0"` matches `pyproject.toml`
- `test_publish_workflow.py`: validate `publish.yml` structure (OIDC permissions, environment, no PYPI_API_TOKEN)
- No functional code changes beyond version bump + workflow rewrite

---

## Version Progression

| PR | Version | Scope |
|---|---|---|
| PR1 | 0.5.0 | Plugin system + Nushell/Xonsh renderers |
| PR2 | 0.6.0 | Overlay store + TUI enhancements + performance |
| PR3 | 1.0.0 | PyPI OIDC publishing + 1.0.0 release bump |

Each PR is independently mergeable. PR2 depends on PR1's `supported_shells()` for overlay alias rendering. PR3 depends on PR1+PR2 for the 1.0.0 changelog.

## Files Touched (Summary)

### PR1
- `pyproject.toml` — entry-point groups, version bump
- `qwik/shells/base.py` — `get_renderer` rewrite, `supported_shells()`, `ShellRenderer.rc_path()`/`install_hook_line()`
- `qwik/shells/bash.py`, `zsh.py`, `fish.py`, `pwsh.py`, `cmd.py` — add `rc_path()`/`install_hook_line()`
- `qwik/shells/nu.py` (new) — `NuRenderer`
- `qwik/shells/xonsh.py` (new) — `XonshRenderer`
- `qwik/commands/init_shell.py` — refactor to use renderer methods
- `qwik/cli.py` — plugin command discovery
- `qwik/__init__.py` — version bump
- `CHANGELOG.md` — `## [0.5.0]` section
- Tests: `test_shell_snapshots.py`, `test_shells.py`, `test_init_shell.py`, `test_plugin_commands.py` (new), `test_nu_renderer.py` (new), `test_xonsh_renderer.py` (new)

### PR2
- `qwik/core/models.py` — `overlay_aliases` field, `all_aliases()` property
- `qwik/core/store.py` — `load(include_overlay=...)`, overlay merge
- `qwik/core/config.py` — overlay paths
- `qwik/commands/overlay.py` (new) — overlay subcommands
- `qwik/commands/run.py` — copy-on-run
- `qwik/commands/rm.py`, `edit.py`, `rename.py` — overlay protection
- `qwik/cli.py` — register overlay command
- `qwik/ui/picker.py` — history view, richer preview, selection stability
- `qwik/core/search.py` — optional optimization
- `qwik/__init__.py` — version bump
- `CHANGELOG.md` — `## [0.6.0]` section
- Tests: `test_overlay*.py` (new), `test_picker.py` (extended), `tests/benchmarks/test_search_perf.py` (new)

### PR3
- `.github/workflows/publish.yml` — OIDC rewrite
- `pyproject.toml` — version `1.0.0`, classifier updates
- `qwik/__init__.py` — version `1.0.0`
- `CHANGELOG.md` — `## [1.0.0]` section
- `README.md` — docs updates
- Tests: `test_version.py` (new or extended), `test_publish_workflow.py` (new)