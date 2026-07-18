# Changelog

All notable changes to this project are documented here.
Format based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

### Changed
- `--global/-g` flag on `qwik add` is now hidden until implemented.
- Fish append-mode renderer wraps the command in single quotes so escaping is meaningful.
- Commands construct their `Console` via `qwik.ui.theme.get_console` so `NO_COLOR` is honored globally.

### Removed
- Dead `_has_shell_metacharacters` helper from `qwik.commands.run`.
