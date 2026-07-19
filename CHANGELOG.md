# Changelog

All notable changes to this project are documented here.
Format based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.4.0] - 2026-07-19

### Added
- `qwik add` now warns when a template alias is created and the active shell is cmd (cmd/doskey cannot expand parameters).
- `qwik add` warns when the command contains a `%VAR%` (cmd) or `$VAR` (pwsh) reference that will be expanded by the shell at run time.

### Fixed
- Builtin-conflict detection at `qwik add`/`rename` now uses the detected shell's builtin set, not bash's. Previously `setopt`/`abbr`/`Write-Output`/`dir` were allowed on their native shells.

## [0.3.1] - 2026-07-19

### Added
- `qwik doctor` can now restore the live store from the latest valid backup when the store is corrupt (interactive confirm).
- Syrupy snapshots now lock per-shell hook rendering output (bash/zsh/fish/pwsh/cmd).
- CLI-level rollback tests verify `qwik rm`/`rename`/`edit`/`import` create backups and `doctor` can restore the pre-operation state.

### Fixed
- Malformed placeholders (e.g. `{bad name}`) are now rejected at `qwik add` time instead of silently being treated as literal text.

## [0.3.0] - 2026-07-19

### Fixed
- Command injection through unquoted template args (`{N}`, `{@}`, `{N:-default}`) — all interpolated args are now `shlex.quote`d (`substitute.py`).
- `qwik edit` no longer crashes with `FileNotFoundError` when `$EDITOR` is unset on Windows; defaults to `notepad` on Windows, `vi` elsewhere, and honors `$VISUAL`.
- `qwik run` no longer creates a backup on every invocation; usage counters updated under a file lock.
- `store.load()` now raises an actionable error pointing at `qwik doctor` and the backup directory.
- Backup filenames now include microseconds to prevent same-second collisions.
- `qwik import` wraps parse/validation errors with a friendly message and previews incoming commands before applying.
- Fish rc path now honors `XDG_CONFIG_HOME` and `__fish_config_dir`.

### Added
- `validate_placeholders_static` rejects `{0}` and malformed placeholders at `qwik add` time.
- `--no-color` CLI flag (wired to `get_console`).
- `QWIK_DEBUG=1` enables debug logging.
- Per-shell `SHELL_BUILTINS` sets and `is_builtin(name, shell)`.
- `CHANGELOG.md`.
- Schema migration framework with forward-only auto-migration on load (`qwik/core/migrations.py`); stores a `version = N` field in `aliases.toml`.
- `qwik completion <shell> [--install/-i]` command: prints or installs shell completion scripts (bash/zsh/fish/pwsh/powershell) with rc backup and idempotent markers.
- `Alias.group` optional field (canonical primary namespace) with `_coerce_group` validation (`^[A-Za-z_][A-Za-z0-9_-]*$`); persisted to `aliases.toml`.
- `--group/-g` option on `qwik add` to assign the primary group at creation.
- `qwik group <name> <group>` / `qwik ungroup <name>` commands to assign or clear the group of an existing alias.
- `--group/-g` filter on `qwik list` and `qwik search`.
- `Group` column in `qwik list` table and `Group` row in `qwik show` detail.
- Group-aware search scoring (`group_score` boost in `score_alias`).
- `qwik sync <init|push|pull|status>` command for git-backed dotfile sharing across machines. Exports the live store to a separate repo at `<config_dir>/qwik-sync/`, commits and pushes on `sync push`, and pulls + import-merges (with a trust-boundary preview) on `sync pull`.

### Changed
- `-g` short flag on `qwik add`, `qwik list`, and `qwik search` now means `--group`.
- Fish append-mode renderer wraps the command in single quotes so escaping is meaningful.
- Commands construct their `Console` via `qwik.ui.theme.get_console` so `NO_COLOR` is honored globally.

### Removed
- Dead `_has_shell_metacharacters` helper from `qwik.commands.run`.
- `--global/-g` dead reserved flag on `qwik add` (replaced by `--group/-g`).
