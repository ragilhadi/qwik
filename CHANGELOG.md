# Changelog

All notable changes to this project are documented here.
Format based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
