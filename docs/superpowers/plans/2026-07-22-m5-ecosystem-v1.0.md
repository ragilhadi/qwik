# Milestone 5 — Ecosystem & Growth (v1.0.0) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement plugin extensibility, team overlay store, TUI enhancements, Nushell/Xonsh renderers, performance benchmarking, and PyPI trusted publishing to reach v1.0.0.

**Architecture:** Three PRs executed sequentially. PR1 converts the hardcoded shell-renderer registry into an entry-point-based plugin system and adds Nushell/Xonsh renderers. PR2 adds a read-only remote git overlay store merged beneath the user store, enhances the TUI picker, and benchmarks/optimizes search. PR3 rewrites the publish workflow for OIDC trusted publishing and bumps to 1.0.0.

**Tech Stack:** Python 3.12+, Typer, Rich, Pydantic v2, tomlkit, prompt_toolkit, rapidfuzz, `importlib.metadata` (stdlib), hatchling, GitHub Actions OIDC.

## Global Constraints

- Python 3.12.10 at `$env:LOCALAPPDATA\Programs\Python\Python312\python.exe` — `python`/`pytest` on PATH are Microsoft Store stubs, must use full path
- Run pytest as: `& "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe" -m pytest <args>`
- Run mypy as: `& "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe" -m mypy qwik`
- Default branch is `master` (not `main`)
- `mypy --strict` must pass with zero errors (pyproject.toml `[tool.mypy] strict = true`)
- Coverage gate: `--cov-fail-under=85` in pyproject.toml addopts
- No new runtime dependencies — use stdlib `importlib.metadata` for entry points
- No comments in code unless explicitly requested
- Test alias names must use `zz_` prefix to avoid PATH-shadow prompts on Windows CI (WiX `lit.exe` on PATH)
- Shell renderers delegate template-mode aliases to `qwik run "<name>" "$@"` — never re-implement substitution in shell
- `SUPPORTED_SHELLS` is currently `("bash", "zsh", "fish", "pwsh", "cmd")` at `qwik/shells/base.py:17`
- `get_renderer` is currently a hardcoded if/elif chain at `qwik/shells/base.py:89-122`
- `init_shell.py` `_rc_path(shell)` is at `qwik/commands/init_shell.py:32-70`, hook_line at `init_shell.py:120-124`
- `completion.py` also uses `_rc_path` and `_fish_config_dir` from `init_shell.py`
- `doctor.py:22` imports `SUPPORTED_SHELLS` and `doctor.py:228` uses `_rc_path("pwsh")`
- `AliasStore` at `qwik/core/models.py:145-226` has `aliases: dict[str, Alias]` and `version: int = 1`
- `Store.load()` at `qwik/core/store.py:73-100` returns `AliasStore`
- `search_aliases` at `qwik/core/search.py:56-98` iterates `store.aliases.items()`
- `run_picker` at `qwik/ui/picker.py:125-216` uses `store.aliases` (line 139)
- `run_command` at `qwik/commands/run.py:23-62` loads store, gets alias, expands, runs, bumps usage
- `publish.yml` at `.github/workflows/publish.yml` uses `PYPI_API_TOKEN` secret (line 41)
- Version is `0.4.0` in both `pyproject.toml:7` and `qwik/__init__.py:24`

---

## PR1 — Plugin System + Nushell/Xonsh Renderers (v0.5.0)

### Task 1: Entry-Point Registration for Shell Renderers

**Files:**
- Modify: `pyproject.toml`
- Modify: `qwik/shells/base.py`
- Modify: `qwik/commands/doctor.py:22,80`
- Modify: `qwik/commands/init_shell.py:73-76` (help text)
- Modify: `tests/test_shells.py:4,11`
- Modify: `tests/test_shell_snapshots.py:12,25`

**Interfaces:**
- Produces: `supported_shells() -> tuple[str, ...]` in `qwik/shells/base.py` (replaces `SUPPORTED_SHELLS` constant)
- Produces: `get_renderer(shell)` rewritten to use `importlib.metadata.entry_points(group="qwik.shell_renderers")`
- Produces: `SUPPORTED_SHELLS` kept as a deprecated alias for backward compat: `SUPPORTED_SHELLS = supported_shells()`

- [ ] **Step 1: Add entry-point group to pyproject.toml**

Edit `pyproject.toml` to add after the `[project.scripts]` section (line 37):

```toml
[project.entry-points."qwik.shell_renderers"]
bash  = "qwik.shells.bash:BashRenderer"
zsh   = "qwik.shells.zsh:ZshRenderer"
fish  = "qwik.shells.fish:FishRenderer"
pwsh  = "qwik.shells.pwsh:PwshRenderer"
cmd   = "qwik.shells.cmd:CmdRenderer"
```

- [ ] **Step 2: Rewrite get_renderer and add supported_shells in base.py**

Replace `qwik/shells/base.py` lines 1-122 with:

```python
"""Abstract base class and per-shell renderers for shell hook generation."""

from __future__ import annotations

import importlib.metadata
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from qwik.core.models import Alias

__all__ = [
    "ShellRenderer",
    "get_renderer",
    "supported_shells",
    "SUPPORTED_SHELLS",
]

_ENTRY_POINT_GROUP = "qwik.shell_renderers"


def supported_shells() -> tuple[str, ...]:
    """Return all registered shell identifiers, sorted.

    Discovers shells via the ``qwik.shell_renderers`` entry-point group.
    """
    eps = importlib.metadata.entry_points(group=_ENTRY_POINT_GROUP)
    return tuple(sorted(ep.name for ep in eps))


# Backward-compat alias (evaluated at import time).
SUPPORTED_SHELLS: tuple[str, ...] = supported_shells()


class ShellRenderer(ABC):
    """ABC for emitting shell-native alias definitions.

    Each concrete subclass must produce syntax that, when evaluated by
    the target shell, makes every *enabled* alias callable as a real
    command (either via ``alias`` or via a wrapper function).
    """

    @property
    @abstractmethod
    def shell_name(self) -> str:
        """Return the canonical shell identifier."""
        ...

    @abstractmethod
    def render_alias(self, name: str, alias: "Alias") -> str:
        """Return a single alias/function definition for *name*.

        Args:
            name: Alias identifier.
            alias: The alias definition.

        Returns:
            A string containing shell-native code (e.g. ``alias gs='git status'``).
        """
        ...

    def render_header(self) -> str:
        """Return an optional header emitted before alias definitions."""
        return ""

    def render_footer(self) -> str:
        """Return an optional footer emitted after alias definitions."""
        return ""

    def render_all(self, aliases: dict[str, "Alias"]) -> str:
        """Render a complete hook snippet for the given alias map.

        Only **enabled** aliases are included.  Output is sorted by name
        for stable generation.
        """
        lines: list[str] = []
        header = self.render_header()
        if header:
            lines.append(header)
        for name in sorted(aliases):
            alias = aliases[name]
            if alias.enabled:
                lines.append(self.render_alias(name, alias))
        footer = self.render_footer()
        if footer:
            lines.append(footer)
        return "\n".join(lines)


def get_renderer(shell: str) -> ShellRenderer:
    """Return the concrete renderer for *shell*.

    Discovers renderers via the ``qwik.shell_renderers`` entry-point group.

    Raises:
        ValueError: If *shell* is not supported.
    """
    shell = shell.lower().strip()
    for ep in importlib.metadata.entry_points(group=_ENTRY_POINT_GROUP):
        if ep.name == shell:
            cls = ep.load()
            return cls()
    raise ValueError(
        f"Unsupported shell: {shell}. Choose from {supported_shells()}."
    )
```

- [ ] **Step 3: Update doctor.py**

In `qwik/commands/doctor.py`:
- Line 22: change `from qwik.shells.base import SUPPORTED_SHELLS` to `from qwik.shells.base import supported_shells`
- Line 80: change `if shell in SUPPORTED_SHELLS:` to `if shell in supported_shells():`

- [ ] **Step 4: Update init_shell.py help text**

In `qwik/commands/init_shell.py` line 74-75, change the help text to be dynamic. Replace:

```python
    shell: str = typer.Argument(
        "bash", help="Target shell (bash, zsh, fish, pwsh, cmd)."
    ),
```

with:

```python
    shell: str = typer.Argument(
        "bash", help="Target shell (e.g. bash, zsh, fish, pwsh, cmd)."
    ),
```

- [ ] **Step 5: Update test imports**

In `tests/test_shells.py` line 4, change:
```python
from qwik.shells.base import SUPPORTED_SHELLS, get_renderer
```
to:
```python
from qwik.shells.base import supported_shells, get_renderer
```
And line 11, change `for shell in SUPPORTED_SHELLS:` to `for shell in supported_shells():`

In `tests/test_shell_snapshots.py` line 12, change:
```python
from qwik.shells.base import SUPPORTED_SHELLS, get_renderer
```
to:
```python
from qwik.shells.base import supported_shells, get_renderer
```
And line 25, change `@pytest.mark.parametrize("shell", SUPPORTED_SHELLS)` to `@pytest.mark.parametrize("shell", supported_shells())`

- [ ] **Step 6: Run tests to verify**

Run: `& "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe" -m pytest tests/test_shells.py tests/test_shell_snapshots.py -v`
Expected: All existing tests pass (entry points are registered via the installed package; if running from source, may need `pip install -e .`)

- [ ] **Step 7: Run mypy**

Run: `& "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe" -m mypy qwik`
Expected: No errors

- [ ] **Step 8: Commit**

```bash
git add pyproject.toml qwik/shells/base.py qwik/commands/doctor.py qwik/commands/init_shell.py tests/test_shells.py tests/test_shell_snapshots.py
git commit -m "feat: entry-point-based shell renderer discovery"
```

---

### Task 2: ShellRenderer rc_path()/install_hook_line() + init_shell Refactor

**Files:**
- Modify: `qwik/shells/base.py` (add `rc_path` and `install_hook_line` to ABC)
- Modify: `qwik/shells/bash.py` (add `rc_path`, `install_hook_line`)
- Modify: `qwik/shells/zsh.py` (add `rc_path`, `install_hook_line`)
- Modify: `qwik/shells/fish.py` (add `rc_path`, `install_hook_line`)
- Modify: `qwik/shells/pwsh.py` (add `rc_path`, `install_hook_line`)
- Modify: `qwik/shells/cmd.py` (add `rc_path`, `install_hook_line` returning None)
- Modify: `qwik/commands/init_shell.py` (refactor to use renderer methods, keep `_fish_config_dir` and `_rc_path` as backward-compat re-exports for completion.py/doctor.py)
- Modify: `tests/test_init_shell.py` (update tests that monkeypatch `_rc_path`)

**Interfaces:**
- Produces: `ShellRenderer.rc_path() -> Path | None` — returns RC file path for this shell
- Produces: `ShellRenderer.install_hook_line() -> str | None` — returns the hook source line to append to rc file
- `init_shell_command` uses `renderer.rc_path()` and `renderer.install_hook_line()` instead of `_rc_path(shell)` and hardcoded hook_line
- `_fish_config_dir()` and `_rc_path()` remain in `init_shell.py` for `completion.py` and `doctor.py` backward compat

- [ ] **Step 1: Add rc_path and install_hook_line to ShellRenderer ABC**

In `qwik/shells/base.py`, add after `render_footer` method (before `render_all`):

```python
    def rc_path(self) -> "Path | None":
        """Return the RC file path for this shell, or ``None`` if unsupported."""
        return None

    def install_hook_line(self) -> str | None:
        """Return the hook line to append to the RC file, or ``None``."""
        return None
```

Add `from pathlib import Path` to the imports at the top (outside TYPE_CHECKING — it's used in runtime default returns, which return None, but the type annotation needs it; actually the return type annotation can be a string if `from __future__ import annotations` is active, which it is. So add `Path` under TYPE_CHECKING):

Actually, since `from __future__ import annotations` is active, the `Path` in the return type annotation is a string. But we need `Path` at runtime in the renderer implementations. So add to the TYPE_CHECKING block:

```python
if TYPE_CHECKING:
    from pathlib import Path
    from qwik.core.models import Alias
```

- [ ] **Step 2: Add rc_path and install_hook_line to BashRenderer**

In `qwik/shells/bash.py`, add imports and methods:

```python
from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

from qwik.shells.base import ShellRenderer

if TYPE_CHECKING:
    from qwik.core.models import Alias

__all__ = ["BashRenderer"]


class BashRenderer(ShellRenderer):
    # ... existing shell_name and render_alias ...

    def rc_path(self) -> Path | None:
        return Path.home() / ".bashrc"

    def install_hook_line(self) -> str | None:
        return '\neval "$(qwik init bash)"\n'
```

Add these two methods at the end of the class (after `render_alias`).

- [ ] **Step 3: Add rc_path and install_hook_line to ZshRenderer**

In `qwik/shells/zsh.py`:

```python
from pathlib import Path
```

Add at end of class:

```python
    def rc_path(self) -> Path | None:
        return Path.home() / ".zshrc"

    def install_hook_line(self) -> str | None:
        return '\neval "$(qwik init zsh)"\n'
```

- [ ] **Step 4: Add rc_path and install_hook_line to FishRenderer**

In `qwik/shells/fish.py`:

```python
import os
from pathlib import Path
```

Add at end of class:

```python
    def rc_path(self) -> Path | None:
        env_val = os.environ.get("__fish_config_dir")
        if env_val:
            return Path(env_val) / "config.fish"
        xdg = os.environ.get("XDG_CONFIG_HOME")
        if xdg:
            return Path(xdg) / "fish" / "config.fish"
        return Path.home() / ".config" / "fish" / "config.fish"

    def install_hook_line(self) -> str | None:
        return "\nqwik init fish | source -\n"
```

- [ ] **Step 5: Add rc_path and install_hook_line to PwshRenderer**

In `qwik/shells/pwsh.py`:

```python
import os
import sys
from pathlib import Path
```

Add at end of class:

```python
    def rc_path(self) -> Path | None:
        if sys.platform == "win32":
            userprofile = os.environ.get("USERPROFILE")
            docs = Path(userprofile) if userprofile else Path.home()
            try:
                import ctypes

                csidl_personal = 5
                buf = ctypes.create_unicode_buffer(260)
                ctypes.windll.shell32.SHGetFolderPathW(
                    None, csidl_personal, None, 0, buf
                )
                pwsh_dir = Path(buf.value) / "PowerShell"
            except Exception:
                pwsh_dir = docs / "Documents" / "PowerShell"
        else:
            pwsh_dir = Path.home() / ".config" / "powershell"
        return pwsh_dir / "Microsoft.PowerShell_profile.ps1"

    def install_hook_line(self) -> str | None:
        return "\nInvoke-Expression (qwik init pwsh | Out-String)\n"
```

- [ ] **Step 6: Add rc_path and install_hook_line to CmdRenderer**

In `qwik/shells/cmd.py`, `rc_path()` and `install_hook_line()` both return `None` (the default from ABC, so no override needed. But for clarity, add explicit overrides):

```python
    def rc_path(self) -> "Path | None":
        return None

    def install_hook_line(self) -> str | None:
        return None
```

(No Path import needed since using string annotation with `from __future__ import annotations`.)

- [ ] **Step 7: Refactor init_shell.py to use renderer methods**

In `qwik/commands/init_shell.py`, refactor `init_shell_command` to use `renderer.rc_path()` and `renderer.install_hook_line()`. Keep `_fish_config_dir` and `_rc_path` as module-level functions for backward compat (used by `completion.py` and `doctor.py`).

Replace the install section (lines 98-130) of `init_shell_command`:

```python
    rc = renderer.rc_path()
    if rc is None:
        print_error(f"Shell {shell} does not support --install.", console=console)
        raise typer.Exit(1)

    rc.parent.mkdir(parents=True, exist_ok=True)

    rc_content = rc.read_text(encoding="utf-8") if rc.exists() else ""

    hook_marker = f"# qwik shell hook ({shell})"
    if hook_marker in rc_content:
        print_info(f"Hook already present in {rc}.", console=console)
        print_info(f"Open a new terminal or run: source {rc}", console=console)
        raise typer.Exit(0)

    if rc.exists():
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        backup = rc.parent / f"{rc.name}.qwik-backup-{stamp}"
        shutil.copy2(rc, backup)
        print_success(f"Backed up {rc} to {backup}", console=console)

    hook_line = renderer.install_hook_line()
    if hook_line is None:
        print_error(f"Shell {shell} does not support --install.", console=console)
        raise typer.Exit(1)

    with rc.open("a", encoding="utf-8") as fh:
        fh.write(f"\n# qwik shell hook ({shell})\n")
        fh.write(hook_line)

    print_success(f"Added hook to {rc}", console=console)
    print_info(f"Open a new terminal or run: source {rc}", console=console)
```

- [ ] **Step 8: Update test_init_shell.py**

The tests that monkeypatch `init_shell._rc_path` need to monkeypatch the renderer's `rc_path` instead. For backward compat, `_rc_path` is still in `init_shell.py` but `init_shell_command` no longer calls it. Tests should mock at the renderer level.

Update `TestInitShellInstall._run_install` to patch `BashRenderer.rc_path` (or the appropriate renderer):

```python
    def _run_install(self, shell: str, rc: Path) -> Any:
        from qwik.shells.base import get_renderer

        renderer_cls = type(get_renderer(shell))
        orig = renderer_cls.rc_path
        try:
            renderer_cls.rc_path = lambda self: rc
            result = runner.invoke(app, ["init", shell, "--install"])
        finally:
            renderer_cls.rc_path = orig
        return result
```

Update `test_install_rc_path_none` and `test_init_install_unknown_shell` to patch the renderer returning None:

```python
    def test_install_rc_path_none(self, tmp_path, monkeypatch) -> None:
        from qwik.config import _reset_config
        from qwik.shells.bash import BashRenderer

        monkeypatch.setenv("QWIK_CONFIG_DIR", str(tmp_path))
        _reset_config()
        orig = BashRenderer.rc_path
        try:
            BashRenderer.rc_path = lambda self: None
            result = runner.invoke(app, ["init", "bash", "--install"])
            assert result.exit_code == 1
            assert "does not support" in result.output
        finally:
            BashRenderer.rc_path = orig
```

The `TestInitShellRcPath` tests still test `_rc_path` directly which is fine — that function remains for backward compat.

- [ ] **Step 9: Run tests**

Run: `& "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe" -m pytest tests/test_init_shell.py tests/test_shells.py -v`
Expected: All pass

- [ ] **Step 10: Run mypy**

Run: `& "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe" -m mypy qwik`
Expected: No errors

- [ ] **Step 11: Commit**

```bash
git add qwik/shells/ qwik/commands/init_shell.py tests/test_init_shell.py
git commit -m "refactor: move rc_path and install_hook_line into ShellRenderer"
```

---

### Task 3: NushellRenderer

**Files:**
- Create: `qwik/shells/nu.py`
- Modify: `pyproject.toml` (add `nu` entry point)
- Modify: `tests/test_shells.py` (add nu tests)
- Create: snapshot via `tests/test_shell_snapshots.py` (auto-generates)

**Interfaces:**
- Produces: `NuRenderer` in `qwik/shells/nu.py` registered as entry point `nu`
- Nushell `def name [...args] { qwik run "name" ...$args }` for template mode
- Nushell `def name [...args] { ^command ...$args }` for append mode

- [ ] **Step 1: Write failing tests for NushellRenderer**

Add to `tests/test_shells.py`:

```python
    def test_nu_template_function(self) -> None:
        renderer = get_renderer("nu")
        out = renderer.render_alias("gco", Alias(command="git checkout {1}"))
        assert 'qwik run "gco"' in out
        assert "...$args" in out

    def test_nu_append_function(self) -> None:
        renderer = get_renderer("nu")
        out = renderer.render_alias("gs", Alias(command="git status"))
        assert "def gs" in out
        assert "^git status" in out

    def test_nu_rc_path(self, tmp_path, monkeypatch) -> None:
        from qwik.shells.nu import NuRenderer

        monkeypatch.delenv("NU_CONFIG_DIR", raising=False)
        monkeypatch.setenv("HOME", str(tmp_path))
        rc = NuRenderer().rc_path()
        assert rc is not None
        assert "nushell" in str(rc).lower()

    def test_nu_rc_path_env_override(self, tmp_path, monkeypatch) -> None:
        from qwik.shells.nu import NuRenderer

        custom = tmp_path / "nuconfig"
        monkeypatch.setenv("NU_CONFIG_DIR", str(custom))
        rc = NuRenderer().rc_path()
        assert rc == custom / "config.nu"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `& "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe" -m pytest tests/test_shells.py -k nu -v`
Expected: FAIL — `nu` not registered

- [ ] **Step 3: Create NuRenderer**

Create `qwik/shells/nu.py`:

```python
"""Nushell shell hook renderer."""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

from qwik.shells.base import ShellRenderer

if TYPE_CHECKING:
    from qwik.core.models import Alias

__all__ = ["NuRenderer"]


class NuRenderer(ShellRenderer):
    """Emit Nushell ``def`` definitions."""

    @property
    def shell_name(self) -> str:
        return "nu"

    def render_alias(self, name: str, alias: "Alias") -> str:
        from qwik.core.substitute import has_placeholders

        if has_placeholders(alias.command):
            return f'def {name} [...args] {{\n    qwik run "{name}" ...$args\n}}'
        return f"def {name} [...args] {{\n    ^{alias.command} ...$args\n}}"

    def rc_path(self) -> Path | None:
        env_val = os.environ.get("NU_CONFIG_DIR")
        if env_val:
            return Path(env_val) / "config.nu"
        return Path.home() / ".config" / "nushell" / "config.nu"

    def install_hook_line(self) -> str | None:
        return "\nsource (qwik init nu | into string)\n"
```

- [ ] **Step 4: Add entry point to pyproject.toml**

In `pyproject.toml`, add to the `[project.entry-points."qwik.shell_renderers"]` section:

```toml
nu    = "qwik.shells.nu:NuRenderer"
```

- [ ] **Step 5: Reinstall package (picks up new entry point)**

Run: `& "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe" -m pip install -e .`

- [ ] **Step 6: Run tests to verify they pass**

Run: `& "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe" -m pytest tests/test_shells.py -k nu -v`
Expected: PASS

- [ ] **Step 7: Run snapshot test (auto-generates snapshot)**

Run: `& "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe" -m pytest tests/test_shell_snapshots.py -v --snapshot-update`
Expected: PASS (creates new snapshot for `nu`)

- [ ] **Step 8: Run mypy**

Run: `& "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe" -m mypy qwik`
Expected: No errors

- [ ] **Step 9: Commit**

```bash
git add qwik/shells/nu.py pyproject.toml tests/test_shells.py tests/test_shell_snapshots.py tests/__snapshots__/
git commit -m "feat: add Nushell shell renderer"
```

---

### Task 4: XonshRenderer

**Files:**
- Create: `qwik/shells/xonsh.py`
- Modify: `pyproject.toml` (add `xonsh` entry point)
- Modify: `tests/test_shells.py` (add xonsh tests)
- Create: snapshot via `tests/test_shell_snapshots.py`

**Interfaces:**
- Produces: `XonshRenderer` in `qwik/shells/xonsh.py` registered as entry point `xonsh`
- Xonsh `def name(*args): qwik run("name", *args)` for template mode
- Xonsh `aliases["name"] = "command"` for append mode

- [ ] **Step 1: Write failing tests for XonshRenderer**

Add to `tests/test_shells.py`:

```python
    def test_xonsh_template_function(self) -> None:
        renderer = get_renderer("xonsh")
        out = renderer.render_alias("gco", Alias(command="git checkout {1}"))
        assert 'qwik run' in out
        assert "gco" in out

    def test_xonsh_append_alias(self) -> None:
        renderer = get_renderer("xonsh")
        out = renderer.render_alias("gs", Alias(command="git status"))
        assert "aliases" in out
        assert "git status" in out

    def test_xonsh_rc_path(self, tmp_path, monkeypatch) -> None:
        from qwik.shells.xonsh import XonshRenderer

        monkeypatch.delenv("XONSHRC", raising=False)
        monkeypatch.setenv("HOME", str(tmp_path))
        rc = XonshRenderer().rc_path()
        assert rc is not None
        assert rc.name == ".xonshrc"

    def test_xonsh_rc_path_env_override(self, tmp_path, monkeypatch) -> None:
        from qwik.shells.xonsh import XonshRenderer

        custom = tmp_path / "custom.xonshrc"
        monkeypatch.setenv("XONSHRC", str(custom))
        rc = XonshRenderer().rc_path()
        assert rc == custom
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `& "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe" -m pytest tests/test_shells.py -k xonsh -v`
Expected: FAIL

- [ ] **Step 3: Create XonshRenderer**

Create `qwik/shells/xonsh.py`:

```python
"""Xonsh shell hook renderer."""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

from qwik.shells.base import ShellRenderer

if TYPE_CHECKING:
    from qwik.core.models import Alias

__all__ = ["XonshRenderer"]


class XonshRenderer(ShellRenderer):
    """Emit xonsh alias definitions."""

    @property
    def shell_name(self) -> str:
        return "xonsh"

    def render_alias(self, name: str, alias: "Alias") -> str:
        from qwik.core.substitute import has_placeholders

        if has_placeholders(alias.command):
            return f'def {name}(*args):\n    qwik run("{name}", *args)'
        escaped = alias.command.replace('"', '\\"')
        return f'aliases["{name}"] = "{escaped}"'

    def rc_path(self) -> Path | None:
        env_val = os.environ.get("XONSHRC")
        if env_val:
            return Path(env_val)
        return Path.home() / ".xonshrc"

    def install_hook_line(self) -> str | None:
        return "\nexecx($(qwik init xonsh))\n"
```

- [ ] **Step 4: Add entry point to pyproject.toml**

Add to `[project.entry-points."qwik.shell_renderers"]`:

```toml
xonsh = "qwik.shells.xonsh:XonshRenderer"
```

- [ ] **Step 5: Reinstall and run tests**

Run: `& "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe" -m pip install -e .`
Run: `& "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe" -m pytest tests/test_shells.py -k xonsh -v`
Expected: PASS

- [ ] **Step 6: Update snapshots**

Run: `& "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe" -m pytest tests/test_shell_snapshots.py -v --snapshot-update`
Expected: PASS

- [ ] **Step 7: Run mypy**

Run: `& "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe" -m mypy qwik`
Expected: No errors

- [ ] **Step 8: Commit**

```bash
git add qwik/shells/xonsh.py pyproject.toml tests/test_shells.py tests/test_shell_snapshots.py tests/__snapshots__/
git commit -m "feat: add Xonsh shell renderer"
```

---

### Task 5: CLI Plugin Command Discovery + Version Bump + CHANGELOG

**Files:**
- Modify: `qwik/cli.py` (add `_discover_plugin_commands`)
- Modify: `qwik/__init__.py` (version → 0.5.0)
- Modify: `pyproject.toml` (version → 0.5.0)
- Modify: `CHANGELOG.md` (add 0.5.0 section)
- Create: `tests/test_plugin_commands.py`

**Interfaces:**
- Produces: `_discover_plugin_commands()` in `cli.py` — discovers `qwik.commands` entry points and registers them

- [ ] **Step 1: Write failing test for plugin command discovery**

Create `tests/test_plugin_commands.py`:

```python
"""Tests for entry-point-based CLI command plugin discovery."""

from __future__ import annotations

from typer.testing import CliRunner

from qwik.cli import app

runner = CliRunner()


def test_builtin_commands_registered() -> None:
    """All built-in commands should be present in the app."""
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for cmd in ["add", "list", "show", "edit", "rename", "rm", "run", "search", "pick", "init", "doctor"]:
        assert cmd in result.output


def test_discover_plugin_commands_does_not_crash() -> None:
    """Plugin discovery should handle no plugins gracefully."""
    from qwik.cli import _discover_plugin_commands

    _discover_plugin_commands()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `& "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe" -m pytest tests/test_plugin_commands.py -v`
Expected: FAIL — `_discover_plugin_commands` not found

- [ ] **Step 3: Add plugin discovery to cli.py**

In `qwik/cli.py`, add after line 71 (after all `app.command()` calls):

```python
def _discover_plugin_commands() -> None:
    """Register CLI commands from the ``qwik.commands`` entry-point group."""
    import importlib.metadata
    import sys

    for ep in importlib.metadata.entry_points(group="qwik.commands"):
        try:
            cmd = ep.load()
            app.command(ep.name)(cmd)
        except Exception as exc:
            print(f"Warning: failed to load plugin command {ep.name!r}: {exc}", file=sys.stderr)


_discover_plugin_commands()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `& "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe" -m pytest tests/test_plugin_commands.py -v`
Expected: PASS

- [ ] **Step 5: Bump version to 0.5.0**

In `pyproject.toml` line 7, change `version = "0.4.0"` to `version = "0.5.0"`.
In `qwik/__init__.py` line 24, change `__version__ = "0.4.0"` to `__version__ = "0.5.0"`.

- [ ] **Step 6: Update CHANGELOG.md**

Add at the top (after line 6, before `## [0.4.0]`):

```markdown
## [0.5.0] - 2026-07-22

### Added
- Plugin/hook extensibility: shell renderers are now discovered via the `qwik.shell_renderers` entry-point group. Third-party packages can register custom renderers without modifying qwik core.
- `ShellRenderer.rc_path()` and `ShellRenderer.install_hook_line()` methods let renderer plugins self-contain their rc-file path and hook installation logic.
- CLI command plugins: commands can be registered via the `qwik.commands` entry-point group.
- Nushell (`nu`) shell renderer with template/append modes and rc-path detection.
- Xonsh (`xonsh`) shell renderer with template/append modes and rc-path detection.

### Changed
- `get_renderer(shell)` now uses `importlib.metadata.entry_points` instead of a hardcoded if/elif chain.
- `SUPPORTED_SHELLS` is now derived dynamically from installed entry points via `supported_shells()`.
- `qwik init <shell> --install` now uses `renderer.rc_path()` and `renderer.install_hook_line()` instead of hardcoded paths.
```

- [ ] **Step 7: Run full test suite + mypy**

Run: `& "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe" -m pytest -v`
Run: `& "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe" -m mypy qwik`
Expected: All tests pass, mypy clean

- [ ] **Step 8: Commit**

```bash
git add qwik/cli.py qwik/__init__.py pyproject.toml CHANGELOG.md tests/test_plugin_commands.py
git commit -m "feat: CLI plugin command discovery + version 0.5.0"
```

---

## PR2 — Overlay Store + TUI Enhancements + Performance (v0.6.0)

### Task 6: AliasStore.overlay_aliases Field + all_aliases() + Config Overlay Paths

**Files:**
- Modify: `qwik/core/models.py` (add `overlay_aliases` field, `all_aliases()` property)
- Modify: `qwik/core/store.py` (exclude `overlay_aliases` from serialization)
- Modify: `qwik/config.py` (add `overlay_config_file`, `overlay_repo_dir`, `overlay_aliases_file`)
- Modify: `tests/test_models.py` or create `tests/test_overlay_model.py`

**Interfaces:**
- Produces: `AliasStore.overlay_aliases: dict[str, Alias]` — read-only, not persisted, excluded from serialization
- Produces: `AliasStore.all_aliases() -> dict[str, Alias]` — returns `{**overlay_aliases, **aliases}` (user wins)
- Produces: `Config.overlay_config_file`, `Config.overlay_repo_dir`, `Config.overlay_aliases_file`

- [ ] **Step 1: Write failing tests**

Create `tests/test_overlay_model.py`:

```python
"""Tests for AliasStore overlay_aliases field and all_aliases()."""

from __future__ import annotations

from qwik.core.models import Alias, AliasStore


def test_overlay_aliases_default_empty() -> None:
    store = AliasStore()
    assert store.overlay_aliases == {}


def test_all_aliases_user_wins() -> None:
    store = AliasStore()
    store.add("gs", Alias(command="git status"))
    store.overlay_aliases["gs"] = Alias(command="git stash")
    store.overlay_aliases["gco"] = Alias(command="git checkout {1}")
    merged = store.all_aliases()
    assert merged["gs"].command == "git status"
    assert merged["gco"].command == "git checkout {1}"


def test_all_aliases_no_overlay() -> None:
    store = AliasStore()
    store.add("gs", Alias(command="git status"))
    merged = store.all_aliases()
    assert merged == store.aliases


def test_overlay_aliases_not_serialized(tmp_path) -> None:
    import tomlkit

    from qwik.core.store import Store

    store = AliasStore()
    store.add("gs", Alias(command="git status"))
    store.overlay_aliases["gco"] = Alias(command="git checkout {1}")
    doc = Store._store_to_document(store)
    raw = tomlkit.dumps(doc)
    assert "overlay" not in raw
    assert "gco" not in raw
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `& "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe" -m pytest tests/test_overlay_model.py -v`
Expected: FAIL — `overlay_aliases` field not found

- [ ] **Step 3: Add overlay_aliases and all_aliases to AliasStore**

In `qwik/core/models.py`, add to `AliasStore` class after `aliases` field (line 155):

```python
    overlay_aliases: dict[str, Alias] = Field(default_factory=dict)
```

Add after the `_validate_names` method:

```python
    def all_aliases(self) -> dict[str, Alias]:
        """Return merged view: user aliases take precedence over overlay."""
        merged = dict(self.overlay_aliases)
        merged.update(self.aliases)
        return merged
```

- [ ] **Step 4: Add Config overlay paths**

In `qwik/config.py`, add after `sync_config_file` property (line 96):

```python
    @property
    def overlay_config_file(self) -> Path:
        """Return the overlay config file path."""
        return self._config_dir / "overlay.toml"

    @property
    def overlay_repo_dir(self) -> Path:
        """Return the directory for the cloned overlay git repo."""
        return self._config_dir / "overlay-repo"

    @property
    def overlay_aliases_file(self) -> Path:
        """Return the overlay repo's aliases.toml path."""
        return self.overlay_repo_dir / "aliases.toml"
```

- [ ] **Step 5: Verify _store_to_document doesn't serialize overlay_aliases**

`_store_to_document` in `store.py:152-188` only iterates `store.aliases` (line 167), so `overlay_aliases` is naturally excluded. The test from step 1 verifies this.

- [ ] **Step 6: Run tests to verify they pass**

Run: `& "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe" -m pytest tests/test_overlay_model.py -v`
Expected: PASS

- [ ] **Step 7: Run mypy**

Run: `& "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe" -m mypy qwik`
Expected: No errors

- [ ] **Step 8: Commit**

```bash
git add qwik/core/models.py qwik/config.py tests/test_overlay_model.py
git commit -m "feat: AliasStore.overlay_aliases + all_aliases() + Config overlay paths"
```

---

### Task 7: Overlay Commands (add/remove/update/list/copy)

**Files:**
- Create: `qwik/commands/overlay.py`
- Modify: `qwik/cli.py` (register `overlay` command)
- Create: `tests/test_overlay.py`

**Interfaces:**
- Produces: `overlay_command` in `qwik/commands/overlay.py` — Typer subcommand with actions: add, remove, update, list, copy
- Consumes: `Config.overlay_config_file`, `Config.overlay_repo_dir`, `Config.overlay_aliases_file` from Task 6
- Consumes: `qwik.core.git` functions for git operations

- [ ] **Step 1: Write failing tests**

Create `tests/test_overlay.py`:

```python
"""Tests for qwik overlay commands."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import tomlkit
from typer.testing import CliRunner

from qwik.cli import app

runner = CliRunner()


def _setup_store(tmp_path, monkeypatch):
    from qwik.config import _reset_config

    monkeypatch.setenv("QWIK_CONFIG_DIR", str(tmp_path))
    _reset_config()
    runner.invoke(app, ["add", "gs", "git", "status"])


def test_overlay_add_without_git_fails(tmp_path, monkeypatch):
    _setup_store(tmp_path, monkeypatch)
    with patch("qwik.commands.overlay.git_available", return_value=False):
        result = runner.invoke(app, ["overlay", "add", "https://github.com/team/aliases"])
    assert result.exit_code == 1
    assert "git not found" in result.output


def test_overlay_list_no_overlay(tmp_path, monkeypatch):
    _setup_store(tmp_path, monkeypatch)
    result = runner.invoke(app, ["overlay", "list"])
    assert result.exit_code == 0
    assert "No overlay configured" in result.output


def test_overlay_remove_no_overlay(tmp_path, monkeypatch):
    _setup_store(tmp_path, monkeypatch)
    result = runner.invoke(app, ["overlay", "remove"])
    assert result.exit_code == 1
    assert "No overlay configured" in result.output


def test_overlay_copy_not_overlay_alias(tmp_path, monkeypatch):
    _setup_store(tmp_path, monkeypatch)
    result = runner.invoke(app, ["overlay", "copy", "gs"])
    assert result.exit_code == 1
    assert "not an overlay alias" in result.output.lower() or "not found" in result.output.lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `& "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe" -m pytest tests/test_overlay.py -v`
Expected: FAIL — `overlay` command not found

- [ ] **Step 3: Create overlay.py**

Create `qwik/commands/overlay.py`:

```python
"""``qwik overlay`` — team/shared read-only overlay store management."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import tomlkit
import typer

from qwik.config import get_config
from qwik.core.git import (
    git_available,
    init_repo,
    add_remote,
    pull as git_pull,
    has_remote,
    get_remote_url,
)
from qwik.core.models import Alias, AliasStore
from qwik.core.store import get_store
from qwik.ui.prompts import print_error, print_info, print_success, print_warning
from qwik.ui.theme import get_console

if TYPE_CHECKING:
    from rich.console import Console

__all__ = ["overlay_command"]

_DEFAULT_BRANCH = "main"

_OVERLAY_MARKER = "# qwik overlay"


def _load_overlay_config(config_file: Path) -> tuple[str | None, str, bool]:
    """Return ``(url, branch, auto_update)`` from overlay config."""
    if not config_file.exists():
        return None, _DEFAULT_BRANCH, True
    parsed = tomlkit.parse(config_file.read_text(encoding="utf-8"))
    url = parsed.get("url")
    branch = str(parsed.get("branch", _DEFAULT_BRANCH))
    auto_update = bool(parsed.get("auto_update", True))
    url_str = str(url) if url is not None else None
    return url_str, branch, auto_update


def _save_overlay_config(config_file: Path, url: str, branch: str) -> None:
    doc = tomlkit.document()
    doc.add("url", url)
    doc.add("branch", branch)
    doc.add("auto_update", True)
    config_file.parent.mkdir(parents=True, exist_ok=True)
    config_file.write_text(tomlkit.dumps(doc), encoding="utf-8")


def _read_overlay_aliases(overlay_file: Path) -> AliasStore:
    from qwik.core.migrations import migrate

    raw = overlay_file.read_text(encoding="utf-8")
    data = dict(tomlkit.parse(raw).unwrap())
    data = migrate(data)
    return AliasStore.model_validate(data)


def overlay_command(
    action: str = typer.Argument(..., help="add|remove|update|list|copy"),
    url: str | None = typer.Option(None, "--url", help="Overlay repo URL (for add)."),
    branch: str = typer.Option(_DEFAULT_BRANCH, "--branch", help="Overlay repo branch."),
    name: str | None = typer.Option(None, "--name", help="Alias name (for copy)."),
) -> None:
    """Manage the team/shared read-only overlay store."""
    console = get_console()
    config = get_config()

    if action == "add":
        _do_add(config, url, branch, console=console)
    elif action == "remove":
        _do_remove(config, console=console)
    elif action == "update":
        _do_update(config, console=console)
    elif action == "list":
        _do_list(config, console=console)
    elif action == "copy":
        if name is None:
            print_error("Usage: qwik overlay copy --name <alias>", console=console)
            raise typer.Exit(1)
        _do_copy(config, name, console=console)
    else:
        print_error(
            f"Unknown overlay action '{action}'.",
            suggestion="Use one of: add, remove, update, list, copy.",
            console=console,
        )
        raise typer.Exit(1)


def _do_add(
    config,
    url: str | None,
    branch: str,
    *,
    console: "Console",
) -> None:
    if url is None:
        print_error("Usage: qwik overlay add --url <git-url>", console=console)
        raise typer.Exit(1)

    if not git_available():
        print_error(
            "git not found on PATH.",
            suggestion="Install git or run 'qwik doctor'.",
            console=console,
        )
        raise typer.Exit(1)

    overlay_repo = config.overlay_repo_dir
    overlay_repo.mkdir(parents=True, exist_ok=True)

    if not (overlay_repo / ".git").exists():
        init_repo(overlay_repo)

    if not has_remote(overlay_repo):
        add_remote(overlay_repo, url)
    _save_overlay_config(config.overlay_config_file, url, branch)

    try:
        git_pull(overlay_repo, "origin", branch)
    except RuntimeError as exc:
        print_error(f"Failed to pull overlay: {exc}", console=console)
        raise typer.Exit(1)

    overlay_file = config.overlay_aliases_file
    if not overlay_file.exists():
        print_warning(
            f"No aliases.toml found in overlay repo at {overlay_file}.",
            console=console,
        )
    else:
        try:
            incoming = _read_overlay_aliases(overlay_file)
            print_success(
                f"Overlay configured with {len(incoming.aliases)} aliases.",
                console=console,
            )
        except Exception as exc:
            print_error(f"Could not read overlay aliases: {exc}", console=console)

    print_info("Run `qwik overlay update` to refresh.", console=console)


def _do_remove(config, *, console: "Console") -> None:
    config_file = config.overlay_config_file
    overlay_repo = config.overlay_repo_dir
    if not config_file.exists() and not overlay_repo.exists():
        print_error("No overlay configured.", console=console)
        raise typer.Exit(1)

    import shutil

    if config_file.exists():
        config_file.unlink()
    if overlay_repo.exists():
        shutil.rmtree(overlay_repo, ignore_errors=True)
    print_success("Overlay removed.", console=console)


def _do_update(config, *, console: "Console") -> None:
    config_file = config.overlay_config_file
    overlay_repo = config.overlay_repo_dir

    if not config_file.exists():
        print_error("No overlay configured.", console=console)
        raise typer.Exit(1)

    url, branch, _ = _load_overlay_config(config_file)

    if not git_available():
        print_error("git not found on PATH.", console=console)
        raise typer.Exit(1)

    try:
        git_pull(overlay_repo, "origin", branch)
        print_success(f"Overlay updated from {url} ({branch}).", console=console)
    except RuntimeError as exc:
        print_error(f"Failed to update overlay: {exc}", console=console)
        raise typer.Exit(1)


def _do_list(config, *, console: "Console") -> None:
    config_file = config.overlay_config_file
    overlay_repo = config.overlay_repo_dir

    if not config_file.exists():
        print_info("No overlay configured.", console=console)
        return

    url, branch, auto_update = _load_overlay_config(config_file)
    console.print(f"[bold]Overlay:[/bold] {url} ({branch})")
    console.print(f"  Auto-update: {'on' if auto_update else 'off'}")

    overlay_file = config.overlay_aliases_file
    if not overlay_file.exists():
        console.print("  Aliases: 0 (no aliases.toml in overlay repo)")
        return

    try:
        incoming = _read_overlay_aliases(overlay_file)
        store = get_store()
        user_data = store.load()
        console.print(f"  Aliases: {len(incoming.aliases)}")
        for n in sorted(incoming.aliases):
            marker = "[dim](user)[/dim]" if n in user_data.aliases else "[dim](overlay)[/dim]"
            console.print(f"    {n} {marker}")
    except Exception as exc:
        console.print(f"  Aliases: [qwik.warning]unreadable ({exc})[/qwik.warning]")


def _do_copy(config, name: str, *, console: "Console") -> None:
    overlay_file = config.overlay_aliases_file
    if not overlay_file.exists():
        print_error("No overlay configured.", console=console)
        raise typer.Exit(1)

    try:
        incoming = _read_overlay_aliases(overlay_file)
    except Exception as exc:
        print_error(f"Could not read overlay: {exc}", console=console)
        raise typer.Exit(1)

    if name not in incoming.aliases:
        print_error(f"'{name}' is not an overlay alias.", console=console)
        raise typer.Exit(1)

    store = get_store()
    data = store.load()

    if name in data.aliases:
        print_warning(f"'{name}' already exists in user store.", console=console)
        raise typer.Exit(0)

    data.add(name, incoming.aliases[name])
    store.save_with_backup(data)
    print_success(f"Copied '{name}' from overlay to user store.", console=console)
```

- [ ] **Step 4: Register overlay command in cli.py**

In `qwik/cli.py`, add import:
```python
from qwik.commands.overlay import overlay_command
```

Add after line 70 (after `app.command("sync")(sync_command)`):
```python
app.command("overlay")(overlay_command)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `& "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe" -m pytest tests/test_overlay.py -v`
Expected: PASS

- [ ] **Step 6: Run mypy**

Run: `& "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe" -m mypy qwik`
Expected: No errors

- [ ] **Step 7: Commit**

```bash
git add qwik/commands/overlay.py qwik/cli.py tests/test_overlay.py
git commit -m "feat: qwik overlay add/remove/update/list/copy commands"
```

---

### Task 8: Store Load-Time Overlay Merge + Copy-on-Run + Overlay Protection

**Files:**
- Modify: `qwik/core/store.py` (add `load(include_overlay=...)` overlay merge)
- Modify: `qwik/commands/run.py` (copy-on-run for overlay-only aliases)
- Modify: `qwik/commands/pick.py` (copy-on-run for overlay-only aliases)
- Modify: `qwik/commands/remove.py` (overlay protection)
- Modify: `qwik/commands/edit.py` (overlay protection)
- Modify: `qwik/commands/rename.py` (overlay protection)
- Modify: `qwik/core/search.py` (search `all_aliases()` instead of `aliases`)
- Modify: `qwik/ui/picker.py` (use `all_aliases()`)
- Modify: `qwik/commands/init_shell.py` (render `all_aliases()`)
- Create: `tests/test_overlay_merge.py`

**Interfaces:**
- Consumes: `AliasStore.overlay_aliases`, `AliasStore.all_aliases()` from Task 6
- Consumes: `Config.overlay_config_file`, `Config.overlay_aliases_file` from Task 6
- Produces: `Store.load(include_overlay=True)` merges overlay into `overlay_aliases`
- Produces: Copy-on-run in `run_command` and `pick_command`

- [ ] **Step 1: Write failing tests**

Create `tests/test_overlay_merge.py`:

```python
"""Tests for overlay merge at load time and overlay alias protection."""

from __future__ import annotations

import tomlkit
from pathlib import Path
from typer.testing import CliRunner

from qwik.cli import app

runner = CliRunner()


def _setup_with_overlay(tmp_path, monkeypatch, overlay_aliases: dict[str, str]):
    from qwik.config import _reset_config

    monkeypatch.setenv("QWIK_CONFIG_DIR", str(tmp_path))
    _reset_config()
    runner.invoke(app, ["add", "gs", "git", "status"])

    config = tmp_path / "overlay.toml"
    config.write_text(tomlkit.dumps({"url": "https://example.com", "branch": "main", "auto_update": False}))

    overlay_repo = tmp_path / "overlay-repo"
    overlay_repo.mkdir(parents=True)
    doc = tomlkit.document()
    doc.add("version", 1)
    aliases_table = tomlkit.table()
    for name, cmd in overlay_aliases.items():
        t = tomlkit.table()
        t.add("command", cmd)
        aliases_table.add(name, t)
    doc.add("aliases", aliases_table)
    (overlay_repo / "aliases.toml").write_text(tomlkit.dumps(doc))


def test_load_merges_overlay(tmp_path, monkeypatch):
    _setup_with_overlay(tmp_path, monkeypatch, {"team_alias": "echo hello"})
    from qwik.core.store import get_store

    store = get_store()
    data = store.load()
    assert "gs" in data.aliases
    assert "team_alias" in data.overlay_aliases
    assert "team_alias" not in data.aliases


def test_all_aliases_merges_overlay(tmp_path, monkeypatch):
    _setup_with_overlay(tmp_path, monkeypatch, {"team_alias": "echo hello"})
    from qwik.core.store import get_store

    store = get_store()
    data = store.load()
    merged = data.all_aliases()
    assert "gs" in merged
    assert "team_alias" in merged


def test_load_without_overlay(tmp_path, monkeypatch):
    from qwik.config import _reset_config

    monkeypatch.setenv("QWIK_CONFIG_DIR", str(tmp_path))
    _reset_config()
    runner.invoke(app, ["add", "gs", "git", "status"])

    from qwik.core.store import get_store

    store = get_store()
    data = store.load()
    assert data.overlay_aliases == {}


def test_rm_overlay_alias_blocked(tmp_path, monkeypatch):
    _setup_with_overlay(tmp_path, monkeypatch, {"team_alias": "echo hello"})
    result = runner.invoke(app, ["rm", "team_alias", "--yes"])
    assert result.exit_code == 1
    assert "overlay" in result.output.lower()


def test_edit_overlay_alias_blocked(tmp_path, monkeypatch):
    _setup_with_overlay(tmp_path, monkeypatch, {"team_alias": "echo hello"})
    result = runner.invoke(app, ["edit", "team_alias"])
    assert result.exit_code == 1
    assert "overlay" in result.output.lower()


def test_rename_overlay_alias_blocked(tmp_path, monkeypatch):
    _setup_with_overlay(tmp_path, monkeypatch, {"team_alias": "echo hello"})
    result = runner.invoke(app, ["rename", "team_alias", "new_name", "--force"])
    assert result.exit_code == 1
    assert "overlay" in result.output.lower()


def test_copy_on_run(tmp_path, monkeypatch):
    _setup_with_overlay(tmp_path, monkeypatch, {"zz_echo": "echo hello"})
    from qwik.core.store import get_store

    store = get_store()
    data = store.load()
    assert "zz_echo" in data.overlay_aliases
    assert "zz_echo" not in data.aliases

    runner.invoke(app, ["run", "zz_echo"])

    data = store.load()
    assert "zz_echo" in data.aliases
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `& "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe" -m pytest tests/test_overlay_merge.py -v`
Expected: FAIL

- [ ] **Step 3: Add overlay merge to Store.load**

In `qwik/core/store.py`, modify `load()` to accept `include_overlay` parameter and merge overlay:

Replace `load()` method (lines 73-100) with:

```python
    def load(self, include_overlay: bool = True) -> AliasStore:
        """Read the alias database from disk.

        Args:
            include_overlay: If ``True`` and an overlay config exists, merge
                overlay aliases into ``store.overlay_aliases`` (read-only).

        Returns:
            An :class:`~qwik.core.models.AliasStore` populated from the TOML
            file.  If the file does not exist, an empty store is returned.
        """
        if not self._path.exists():
            store = AliasStore()
        else:
            try:
                raw = self._path.read_text(encoding="utf-8")
                doc = tomlkit.parse(raw)
                data: dict[str, Any] = doc.unwrap()
                from qwik.core.migrations import migrate

                pre_version = data.get("version")
                data = migrate(data)
                migrated = data.get("version") != pre_version
                store = AliasStore.model_validate(data)
                if migrated:
                    self.save_with_backup(store)
            except (TOMLDecodeError, ValueError) as exc:
                raise RuntimeError(
                    f"Could not read alias store at {self._path}: {exc}. "
                    f"Run `qwik doctor` to diagnose or restore from "
                    f"{self._backup_dir}."
                ) from exc

        if include_overlay:
            self._merge_overlay(store)
        return store

    def _merge_overlay(self, store: AliasStore) -> None:
        """Merge overlay aliases into ``store.overlay_aliases`` (non-fatal)."""
        config_file = self._config.overlay_config_file
        if not config_file.exists():
            return
        overlay_file = self._config.overlay_aliases_file
        if not overlay_file.exists():
            return
        try:
            from qwik.core.migrations import migrate as do_migrate

            raw = overlay_file.read_text(encoding="utf-8")
            data: dict[str, Any] = dict(tomlkit.parse(raw).unwrap())
            data = do_migrate(data)
            overlay_store = AliasStore.model_validate(data)
            for name, alias in overlay_store.aliases.items():
                if name not in store.aliases:
                    store.overlay_aliases[name] = alias
        except Exception:
            pass
```

- [ ] **Step 4: Add copy-on-run to run.py**

In `qwik/commands/run.py`, after loading the store and getting the alias (line 33), add copy-on-run for overlay aliases:

Replace lines 28-36 with:

```python
    store = get_store()
    data = store.load()
    console = get_console()

    alias = data.get(name)
    if alias is None and name in data.overlay_aliases:
        alias = data.overlay_aliases[name]
        data.add(name, alias)
        store.save_with_backup(data)
    if alias is None:
        print_error(f'Alias "{name}" does not exist.', console=console)
        raise typer.Exit(1)
```

- [ ] **Step 5: Add copy-on-run to pick.py**

In `qwik/commands/pick.py`, after loading the store (line 22) and before `run_picker`, if the selected alias is overlay-only, copy it. After selection (line 48), replace:

```python
    name = selected
    alias = data.get(name)
    if alias is None and name in data.overlay_aliases:
        alias = data.overlay_aliases[name]
        data.add(name, alias)
        store.save_with_backup(data)
    if alias is None:
        print_error(f'Alias "{name}" disappeared.', console=console)
        raise typer.Exit(1)
```

- [ ] **Step 6: Add overlay protection to rm, edit, rename**

In `qwik/commands/remove.py`, after loading data (line 21), before the `if name not in data.aliases` check, add:

```python
    if name in data.overlay_aliases and name not in data.aliases:
        print_error(
            f"'{name}' is an overlay alias (read-only). "
            f"Copy it first: qwik overlay copy --name {name}",
            console=console,
        )
        raise typer.Exit(1)
```

In `qwik/commands/edit.py`, after loading data (line 58), before the `alias = data.get(name)` check, add:

```python
    if name in data.overlay_aliases and name not in data.aliases:
        print_error(
            f"'{name}' is an overlay alias (read-only). "
            f"Copy it first: qwik overlay copy --name {name}",
            console=console,
        )
        raise typer.Exit(1)
```

In `qwik/commands/rename.py`, after loading data (line 30), before the `if old not in data.aliases` check, add:

```python
    if old in data.overlay_aliases and old not in data.aliases:
        print_error(
            f"'{old}' is an overlay alias (read-only). "
            f"Copy it first: qwik overlay copy --name {old}",
            console=console,
        )
        raise typer.Exit(1)
```

- [ ] **Step 7: Update search.py to use all_aliases**

In `qwik/core/search.py` line 80, change:
```python
    for name, alias in store.aliases.items():
```
to:
```python
    for name, alias in store.all_aliases().items():
```

- [ ] **Step 8: Update picker.py to use all_aliases**

In `qwik/ui/picker.py` line 139, change:
```python
    if not store.aliases:
```
to:
```python
    if not store.all_aliases():
```

- [ ] **Step 9: Update init_shell.py to render all_aliases**

In `qwik/commands/init_shell.py` line 92, change:
```python
    snippet = renderer.render_all(data.aliases)
```
to:
```python
    snippet = renderer.render_all(data.all_aliases())
```

- [ ] **Step 10: Run tests**

Run: `& "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe" -m pytest tests/test_overlay_merge.py -v`
Expected: PASS

- [ ] **Step 11: Run full suite + mypy**

Run: `& "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe" -m pytest -v`
Run: `& "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe" -m mypy qwik`
Expected: All pass, mypy clean

- [ ] **Step 12: Commit**

```bash
git add qwik/core/store.py qwik/commands/run.py qwik/commands/pick.py qwik/commands/remove.py qwik/commands/edit.py qwik/commands/rename.py qwik/core/search.py qwik/ui/picker.py qwik/commands/init_shell.py tests/test_overlay_merge.py
git commit -m "feat: overlay merge at load time, copy-on-run, overlay protection"
```

---

### Task 9: TUI Enhancements — History View, Richer Preview, Selection Stability

**Files:**
- Modify: `qwik/ui/picker.py`
- Modify: `tests/test_picker.py`

**Interfaces:**
- Produces: `Ctrl-R` toggles history mode (recent-first by `last_used`)
- Produces: `_get_preview_lines` shows all Alias fields
- Produces: `_refresh` preserves selection by name across keystrokes
- Produces: `_PickerState.history_mode: bool`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_picker.py`:

```python
def test_picker_ctrl_r_toggles_history(store_with_aliases):
    from qwik.core.models import Alias
    import datetime as dt

    store_with_aliases.aliases["gs"].last_used = dt.datetime.now(dt.timezone.utc)
    with create_pipe_input() as inp:
        inp.send_text("\x12")
        result = run_picker(store_with_aliases, input_=inp, output=DummyOutput())
    assert result is not None


def test_preview_shows_all_fields(store_with_aliases):
    from qwik.core.models import Alias
    from qwik.ui.picker import _get_preview_lines

    store_with_aliases.add("full", Alias(
        command="git status",
        tag=["vcs"],
        group="git",
        description="Show working tree status",
    ))
    results = [("full", store_with_aliases.aliases["full"], 1.0)]
    lines = _get_preview_lines(results, 0)
    text = "".join(s for _, s in lines)
    assert "Name:" in text
    assert "Cmd:" in text
    assert "Group:" in text
    assert "Tag:" in text
    assert "Used:" in text
    assert "Desc:" in text


def test_picker_preserves_selection(store_with_aliases):
    with create_pipe_input() as inp:
        inp.send_text("\x1b[B\r")
        result = run_picker(store_with_aliases, input_=inp, output=DummyOutput())
    assert result is not None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `& "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe" -m pytest tests/test_picker.py -v -k "ctrl_r or preview_shows or preserves_selection"`
Expected: Some FAIL

- [ ] **Step 3: Implement history view, richer preview, selection stability**

In `qwik/ui/picker.py`:

1. Add `history_mode` to `_PickerState`:
```python
class _PickerState:
    def __init__(self) -> None:
        self.selected_index: int = 0
        self.results: list[tuple[str, Alias, float]] = []
        self.selected_name: str | None = None
        self.history_mode: bool = False
```

2. Extend `_get_preview_lines` (replace lines 52-63):
```python
def _get_preview_lines(
    results: list[tuple[str, Alias, float]], selected_index: int
) -> list[tuple[str, str]]:
    if not results or selected_index >= len(results):
        return [("dim", "  (no selection)\n")]
    name, alias, _ = results[selected_index]
    lines: list[tuple[str, str]] = [
        ("bold", f"  Name: {name}\n"),
        ("", f"  Cmd:  {alias.command}\n"),
        ("", f"  Group: {alias.group or '—'}\n"),
        ("", f"  Tag:  {', '.join(alias.tag) or '—'}\n"),
        ("", f"  Used: {alias.run_count} times (last: {alias.format_last_used()})\n"),
        ("", f"  Created: {alias.created_at.strftime('%Y-%m-%d')}\n"),
        ("", f"  Enabled: {'yes' if alias.enabled else 'no'}\n"),
    ]
    if alias.description:
        lines.append(("", f"  Desc:  {alias.description}\n"))
    return lines
```

3. Add `Ctrl-R` keybinding in `_bind_keys`:
```python
    @kb.add("c-r")
    def _toggle_history(event) -> None:
        state.history_mode = not state.history_mode
        _refresh(store, state, result_window, preview_window, "")
```

Wait — `_bind_keys` doesn't have access to `store`. Need to pass it. Let me restructure.

Actually, looking at the current code, `_refresh` is called from the `Buffer.on_text_changed` lambda which has `store` in scope. The keybinding needs `store` too. Let me add `store` as a parameter to `_bind_keys`:

Replace `_bind_keys` signature and add the keybinding. The `_bind_keys` function (lines 73-122) needs `store` passed. Change signature to:

```python
def _bind_keys(
    kb: KeyBindings,
    store: "AliasStore",
    state: _PickerState,
    result_window: Window,
    preview_window: Window,
) -> None:
```

Add after the `_delete` handler:

```python
    @kb.add("c-r")
    def _toggle_history(event) -> None:
        state.history_mode = not state.history_mode
        _refresh(store, state, result_window, preview_window, "")
```

4. Update `_refresh` to handle history mode and preserve selection:

```python
def _refresh(
    store: "AliasStore",
    state: _PickerState,
    result_window: Window,
    preview_window: Window,
    query: str,
) -> None:
    current_name = None
    if state.results and state.selected_index < len(state.results):
        current_name = state.results[state.selected_index][0]

    state.results = search_aliases(store, query, limit=50)

    if state.history_mode:
        state.results.sort(
            key=lambda t: t[1].last_used or datetime.min.replace(tzinfo=timezone.utc),
            reverse=True,
        )

    if current_name is not None:
        for i, (n, _, _) in enumerate(state.results):
            if n == current_name:
                state.selected_index = i
                break
        else:
            state.selected_index = 0
    else:
        state.selected_index = 0

    result_window.content = FormattedTextControl(
        lambda: _get_result_lines(state.results, state.selected_index)
    )
    preview_window.content = FormattedTextControl(
        lambda: _get_preview_lines(state.results, state.selected_index)
    )
```

Add import at top: `from datetime import datetime, timezone`

5. Update `_bind_keys` call in `run_picker` (line 163):
```python
    _bind_keys(kb, store, state, result_window, preview_window)
```

6. Update the help line to include Ctrl-R:
```python
    "↑↓ navigate  Enter run  Ctrl-E edit  Ctrl-D delete  Ctrl-R history  Esc cancel",
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `& "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe" -m pytest tests/test_picker.py -v`
Expected: PASS

- [ ] **Step 5: Run mypy**

Run: `& "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe" -m mypy qwik`
Expected: No errors

- [ ] **Step 6: Commit**

```bash
git add qwik/ui/picker.py tests/test_picker.py
git commit -m "feat: TUI history view (Ctrl-R), richer preview, selection stability"
```

---

### Task 10: Performance Benchmark + Version 0.6.0 Bump + CHANGELOG

**Files:**
- Create: `tests/test_search_perf.py`
- Modify: `qwik/__init__.py` (version → 0.6.0)
- Modify: `pyproject.toml` (version → 0.6.0)
- Modify: `CHANGELOG.md`

**Interfaces:**
- Produces: `tests/test_search_perf.py` — benchmark test for search performance

- [ ] **Step 1: Write benchmark test**

Create `tests/test_search_perf.py`:

```python
"""Performance benchmarks for fuzzy search.

Not run by default CI (no marker gate); run manually with:
    pytest tests/test_search_perf.py -v -s
"""

from __future__ import annotations

import time

import pytest

from qwik.core.models import Alias, AliasStore
from qwik.core.search import search_aliases


def _build_store(n: int) -> AliasStore:
    store = AliasStore()
    for i in range(n):
        store.add(f"alias_{i:05d}", Alias(command=f"echo command_{i}"))
    return store


@pytest.mark.parametrize("count", [1000, 5000, 10000])
def test_search_perf_under_200ms(count: int) -> None:
    store = _build_store(count)
    query = "alias_00"
    times: list[float] = []
    for _ in range(10):
        start = time.perf_counter()
        search_aliases(store, query, limit=50)
        elapsed = (time.perf_counter() - start) * 1000
        times.append(elapsed)
    median = sorted(times)[len(times) // 2]
    print(f"\n  {count} aliases: {median:.1f}ms median (limit: 200ms)")
    assert median < 200, f"Search too slow: {median:.1f}ms for {count} aliases"


def test_search_empty_query_fast() -> None:
    store = _build_store(1000)
    start = time.perf_counter()
    search_aliases(store, "", limit=50)
    elapsed = (time.perf_counter() - start) * 1000
    assert elapsed < 50, f"Empty query too slow: {elapsed:.1f}ms"
```

- [ ] **Step 2: Run benchmark**

Run: `& "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe" -m pytest tests/test_search_perf.py -v -s`
Expected: PASS (if < 200ms; if fails, add early-exit optimization to `score_alias`)

- [ ] **Step 3: Bump version to 0.6.0**

In `pyproject.toml` line 7: `version = "0.6.0"`
In `qwik/__init__.py` line 24: `__version__ = "0.6.0"`

- [ ] **Step 4: Update CHANGELOG.md**

Add after line 6 (before `## [0.5.0]`):

```markdown
## [0.6.0] - 2026-07-22

### Added
- Team/shared read-only overlay store: `qwik overlay add/remove/update/list/copy` commands for merging a remote git-hosted alias set beneath the user store.
- Overlay aliases are merged at load time (user store takes precedence); overlay-only aliases are copy-on-run (copied to user store on first execution).
- Overlay alias protection: `rm`, `edit`, `rename` are blocked on overlay-only aliases with an actionable message.
- TUI history view: `Ctrl-R` in the picker toggles recent-first mode sorted by `last_used`.
- Richer picker preview: shows group, tags, usage with relative time, created date, enabled status, and description.
- Selection stability: the picker preserves the highlighted alias across keystrokes instead of resetting to the top.
- Search performance benchmark test at 1k/5k/10k alias counts.

### Changed
- `Store.load()` accepts `include_overlay` parameter (default `True`) to merge overlay aliases.
- `search_aliases` and `run_picker` operate on `all_aliases()` (merged view) instead of `aliases` only.
- `qwik init` renders `all_aliases()` so overlay aliases appear in shell hooks.
```

- [ ] **Step 5: Run full suite + mypy**

Run: `& "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe" -m pytest -v`
Run: `& "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe" -m mypy qwik`
Expected: All pass, mypy clean

- [ ] **Step 6: Commit**

```bash
git add tests/test_search_perf.py qwik/__init__.py pyproject.toml CHANGELOG.md
git commit -m "feat: search benchmark + version 0.6.0"
```

---

## PR3 — PyPI Trusted Publishing + 1.0.0 Release (v1.0.0)

### Task 11: publish.yml OIDC Rewrite

**Files:**
- Modify: `.github/workflows/publish.yml`
- Create: `tests/test_publish_workflow.py`

**Interfaces:**
- Produces: `publish.yml` with 3 jobs: `test` (matrix), `build`, `publish` (OIDC)
- Produces: `test_publish_workflow.py` validating workflow structure

- [ ] **Step 1: Write failing test**

Create `tests/test_publish_workflow.py`:

```python
"""Validate publish.yml workflow structure for OIDC trusted publishing."""

from __future__ import annotations

from pathlib import Path

import yaml


def _load_workflow() -> dict:
    workflow_path = Path(__file__).parent.parent / ".github" / "workflows" / "publish.yml"
    with open(workflow_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def test_publish_uses_oidc_not_token() -> None:
    wf = _load_workflow()
    wf_str = str(wf)
    assert "PYPI_API_TOKEN" not in wf_str, "Should not use long-lived API token"


def test_publish_has_id_token_write() -> None:
    wf = _load_workflow()
    jobs = wf.get("jobs", {})
    publish_job = jobs.get("publish", {})
    permissions = publish_job.get("permissions", {})
    assert permissions.get("id-token") == "write", (
        "publish job must have id-token: write for OIDC"
    )


def test_publish_has_pypi_environment() -> None:
    wf = _load_workflow()
    jobs = wf.get("jobs", {})
    publish_job = jobs.get("publish", {})
    assert publish_job.get("environment") == "pypi", (
        "publish job must use 'pypi' environment"
    )


def test_publish_uses_pypi_action() -> None:
    wf = _load_workflow()
    jobs = wf.get("jobs", {})
    publish_job = jobs.get("publish", {})
    steps = publish_job.get("steps", [])
    uses = [s.get("uses", "") for s in steps if "uses" in s]
    assert any("pypi-publish" in u for u in uses), (
        "Should use pypa/gh-action-pypi-publish"
    )


def test_test_job_has_matrix() -> None:
    wf = _load_workflow()
    jobs = wf.get("jobs", {})
    test_job = jobs.get("test", {})
    strategy = test_job.get("strategy", {})
    matrix = strategy.get("matrix", {})
    assert "ubuntu-latest" in matrix.get("os", [])
    assert "windows-latest" in matrix.get("os", [])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `& "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe" -m pytest tests/test_publish_workflow.py -v`
Expected: FAIL (current workflow uses `PYPI_API_TOKEN`, no OIDC)

- [ ] **Step 3: Rewrite publish.yml**

Replace `.github/workflows/publish.yml` entirely:

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

- [ ] **Step 4: Ensure PyYAML is available for the test**

Run: `& "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe" -m pip install pyyaml`

Check if pyyaml is in dev deps — if not, add to `[project.optional-dependencies] dev`:
```toml
    "pyyaml>=6.0",
```

- [ ] **Step 5: Run test to verify it passes**

Run: `& "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe" -m pytest tests/test_publish_workflow.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add .github/workflows/publish.yml tests/test_publish_workflow.py pyproject.toml
git commit -m "ci: PyPI trusted publishing (OIDC) with matrix test + attestations"
```

---

### Task 12: 1.0.0 Version Bump + README + CHANGELOG

**Files:**
- Modify: `pyproject.toml` (version → 1.0.0, classifier → Production/Stable, add 3.13 classifier)
- Modify: `qwik/__init__.py` (version → 1.0.0)
- Modify: `README.md` (update install instructions, supported shells, document overlay/completion/plugins)
- Modify: `CHANGELOG.md` (add 1.0.0 section)
- Create: `tests/test_version.py`

- [ ] **Step 1: Write version consistency test**

Create `tests/test_version.py`:

```python
"""Verify version consistency between pyproject.toml and __init__.py."""

from __future__ import annotations

import re
from pathlib import Path


def test_version_matches_pyproject() -> None:
    import qwik

    pyproject = Path(__file__).parent.parent / "pyproject.toml"
    content = pyproject.read_text(encoding="utf-8")
    match = re.search(r'^version\s*=\s*"([^"]+)"', content, re.MULTILINE)
    assert match is not None, "version not found in pyproject.toml"
    pyproject_version = match.group(1)
    assert qwik.__version__ == pyproject_version, (
        f"Version mismatch: __init__.py={qwik.__version__}, "
        f"pyproject.toml={pyproject_version}"
    )


def test_version_is_1_0_0() -> None:
    import qwik

    assert qwik.__version__ == "1.0.0", f"Expected 1.0.0, got {qwik.__version__}"
```

- [ ] **Step 2: Bump version**

In `pyproject.toml`:
- Line 7: `version = "1.0.0"`
- Line 17: `"Development Status :: 5 - Production/Stable",`
- After line 23, add: `"Programming Language :: Python :: 3.13",`

In `qwik/__init__.py` line 24: `__version__ = "1.0.0"`

- [ ] **Step 3: Update README.md**

1. Update the Installation section (replace lines 32-42):

```markdown
## Installation

```bash
pipx install qwik
```

Or with `uv`:

```bash
uv tool install qwik
```
```

2. Update line 7 to add Nushell and Xonsh:

```markdown
Create, manage, and run shell aliases from a single interface. Works cross-platform with bash, zsh, fish, PowerShell, cmd, Nushell, and Xonsh.
```

3. Add overlay and completion command docs in the Commands section (add after the sync command docs):

```markdown
### `qwik overlay`

Team/shared read-only alias store:

```bash
qwik overlay add --url https://github.com/team/qwik-aliases --branch main
qwik overlay list           # show overlay aliases
qwik overlay update         # git pull the overlay repo
qwik overlay copy --name gs # copy an overlay alias to your user store
qwik overlay remove         # remove the overlay
```

Overlay aliases appear in search, `qwik init`, and the picker, but cannot be
edited or removed (they're read-only). Running an overlay alias copies it to
your user store for usage tracking.

### `qwik completion`

Install shell completions for qwik itself:

```bash
qwik completion bash --install
qwik completion zsh --install
qwik completion fish --install
qwik completion pwsh --install
```

### Plugin System

qwik supports third-party shell renderers and CLI commands via Python entry points:

- **Shell renderers:** Register a class implementing `ShellRenderer` under the `qwik.shell_renderers` entry-point group in your `pyproject.toml`.
- **CLI commands:** Register a Typer-compatible callable under the `qwik.commands` entry-point group.

```toml
# In your plugin's pyproject.toml
[project.entry-points."qwik.shell_renderers"]
myshell = "my_package.shell:MyShellRenderer"
```
```

- [ ] **Step 4: Update CHANGELOG.md**

Add after line 6 (before `## [0.6.0]`):

```markdown
## [1.0.0] - 2026-07-22

### Added
- PyPI trusted publishing (OIDC) via `pypa/gh-action-pypi-publish` with PEP 740 attestations.
- Search performance benchmark at 1k/5k/10k alias counts (all under 200ms median).

### Changed
- `Development Status` classifier bumped to `5 - Production/Stable`.
- Python 3.13 classifier added.
- `publish.yml` split into `test` (OS matrix), `build`, and `publish` (OIDC) jobs.
- README updated with PyPI install instructions, Nushell/Xonsh shells, overlay/completion/plugin docs.

### Removed
- Long-lived `PYPI_API_TOKEN` secret (replaced by OIDC trusted publishing).
```

- [ ] **Step 5: Run version test**

Run: `& "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe" -m pytest tests/test_version.py -v`
Expected: PASS

- [ ] **Step 6: Run full suite + mypy**

Run: `& "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe" -m pytest -v`
Run: `& "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe" -m mypy qwik`
Expected: All pass, mypy clean

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml qwik/__init__.py README.md CHANGELOG.md tests/test_version.py
git commit -m "feat: 1.0.0 release — PyPI OIDC, Production/Stable, docs"
```