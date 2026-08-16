"""Shell detection helpers.

The functions here infer the current user's shell from an explicit
override, shell-specific environment variables, and (where available) the
parent process. They are used by ``qwik doctor`` and by the conflict-check
pipeline in ``qwik add``/``qwik rename`` to pick the right builtin set, and
by ``qwik run``'s argument-quoting strategy to pick the right quoting
rules for the shell that will actually execute the expanded command.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

__all__ = [
    "shell_name_from_override",
    "shell_name_from_version_env",
    "shell_name_from_env",
    "shell_name_from_proc",
    "detect_shell",
]

# Every shell qwik has a renderer for (qwik/shells/*.py), and therefore the
# only values `QWIK_SHELL` or a detector may legally produce.
_KNOWN_SHELLS = frozenset({"bash", "zsh", "fish", "pwsh", "cmd", "nu", "xonsh"})

_ENV_OVERRIDE_VAR = "QWIK_SHELL"


def shell_name_from_override() -> str | None:
    """Return the user-forced shell from ``$QWIK_SHELL``, if set and known.

    This always takes precedence over every other detection strategy, so
    a user can force the right behaviour when none of the heuristics
    below can (e.g. a shell running under an unusual launcher).

    Returns:
        A lowercase shell name, or ``None`` if unset or unrecognised.
    """
    value = os.environ.get(_ENV_OVERRIDE_VAR, "").strip().lower()
    return value if value in _KNOWN_SHELLS else None


def shell_name_from_version_env() -> str | None:
    """Detect Nushell/xonsh via the version variable each sets on itself.

    Both are cheap, reliable, and set on every platform they run on —
    checked ahead of ``$SHELL``, which for these two shells is often
    inherited unchanged from whatever POSIX shell launched them and so
    can misreport the actually-running shell.

    Returns:
        ``"nu"``, ``"xonsh"``, or ``None``.
    """
    if os.environ.get("NU_VERSION"):
        return "nu"
    if os.environ.get("XONSH_VERSION"):
        return "xonsh"
    return None


def shell_name_from_env() -> str | None:
    """Return shell name from ``$SHELL`` if present.

    ``$SHELL`` is a POSIX login-shell convention: Windows does not set
    it, and on any platform it reflects the user's *login* shell rather
    than whatever is actually running, so this is only ever one signal
    among several.

    Returns:
        A lowercase shell name (``bash``, ``zsh``, ``fish``, ``pwsh``),
        or ``None`` if ``$SHELL`` is unset or unrecognised.
    """
    shell_env = os.environ.get("SHELL", "").lower()
    if "bash" in shell_env:
        return "bash"
    if "zsh" in shell_env:
        return "zsh"
    if "fish" in shell_env:
        return "fish"
    if "pwsh" in shell_env or "powershell" in shell_env:
        return "pwsh"
    return None


_EXACT_EXE_NAMES: dict[str, str] = {
    "bash": "bash",
    "zsh": "zsh",
    "fish": "fish",
    "pwsh": "pwsh",
    "powershell": "pwsh",
    "xonsh": "xonsh",
    # "nu" and "cmd" are short enough that a substring match risks false
    # positives (e.g. "menu", "runuser") — only an exact basename counts.
    "nu": "nu",
    "cmd": "cmd",
}

_SUBSTRING_EXE_NAMES: tuple[tuple[str, str], ...] = (
    ("bash", "bash"),
    ("zsh", "zsh"),
    ("fish", "fish"),
    ("powershell", "pwsh"),
    ("pwsh", "pwsh"),
    ("xonsh", "xonsh"),
)


def _classify_exe_name(name: str) -> str | None:
    """Map a bare executable/image name to a qwik shell identifier."""
    name = name.lower()
    base = name[:-4] if name.endswith(".exe") else name
    exact = _EXACT_EXE_NAMES.get(base)
    if exact is not None:
        return exact
    for needle, shell in _SUBSTRING_EXE_NAMES:
        if needle in base:
            return shell
    return None


def _shell_name_from_linux_proc() -> str | None:
    """Resolve the parent process's executable via ``/proc`` (Linux only)."""
    try:
        with Path("/proc/self/status").open(encoding="utf-8") as f:
            for line in f:
                if line.startswith("PPid:"):
                    ppid = line.split()[1]
                    exe_link = Path(f"/proc/{ppid}/exe")
                    if exe_link.exists():
                        return _classify_exe_name(exe_link.resolve().name)
    except Exception:
        pass
    return None


def _shell_name_from_ps() -> str | None:
    """Resolve the parent process's command name via ``ps`` (macOS/BSD).

    Neither macOS nor the BSDs expose ``/proc`` by default, so Linux's
    fast path isn't available; ``ps`` is a POSIX-standard fallback that
    is present everywhere Linux's ``/proc`` isn't.
    """
    try:
        result = subprocess.run(
            ["ps", "-p", str(os.getppid()), "-o", "comm="],
            capture_output=True,
            text=True,
            timeout=1,
        )
        if result.returncode == 0 and result.stdout.strip():
            return _classify_exe_name(Path(result.stdout.strip()).name)
    except Exception:
        pass
    return None


def _shell_name_from_windows_env() -> str | None:
    """Cheap Windows heuristics that don't require walking the process tree.

    ``$PSModulePath`` is set by PowerShell (Windows PowerShell and pwsh
    alike) on every platform it runs on. ``$PROMPT`` is a cmd.exe
    convention — cmd sets it by default and PowerShell does not use it
    at all — so its presence without ``$PSModulePath`` is a reasonable
    signal for cmd specifically.
    """
    if os.environ.get("PSModulePath"):
        return "pwsh"
    if os.environ.get("PROMPT") is not None:
        return "cmd"
    return None


def _shell_name_from_windows_parent_process() -> str | None:
    """Best-effort Windows parent-process walk via the ToolHelp32 API.

    Only reached when the cheap environment-variable heuristics above
    found nothing. Uses ``ctypes`` directly to avoid a hard dependency
    on ``psutil``; any failure (including simply not running on Windows,
    where ``ctypes.windll`` doesn't exist) is swallowed and reported as
    "unknown" rather than raised.
    """
    try:
        import ctypes
        from ctypes import wintypes

        TH32CS_SNAPPROCESS = 0x00000002

        class PROCESSENTRY32(ctypes.Structure):
            _fields_ = [
                ("dwSize", wintypes.DWORD),
                ("cntUsage", wintypes.DWORD),
                ("th32ProcessID", wintypes.DWORD),
                ("th32DefaultHeapID", ctypes.POINTER(ctypes.c_ulong)),
                ("th32ModuleID", wintypes.DWORD),
                ("cntThreads", wintypes.DWORD),
                ("th32ParentProcessID", wintypes.DWORD),
                ("pcPriClassBase", ctypes.c_long),
                ("dwFlags", wintypes.DWORD),
                ("szExeFile", ctypes.c_char * 260),
            ]

        # getattr, not ctypes.windll.kernel32: `windll` only exists in the
        # Windows-specific typeshed stub, so a static attribute access
        # makes mypy's verdict depend on which OS happens to run it —
        # `attr-defined` on Linux/macOS, "unused ignore" on Windows. The
        # indirection sidesteps that platform-dependent check entirely;
        # the AttributeError this raises on non-Windows is still caught
        # below exactly like before.
        kernel32 = getattr(ctypes, "windll").kernel32  # noqa: B009 — see comment above
        snapshot = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
        if snapshot == -1 or snapshot == 0:
            return None
        try:
            pid_to_name: dict[int, str] = {}
            pid_to_parent: dict[int, int] = {}
            entry = PROCESSENTRY32()
            entry.dwSize = ctypes.sizeof(PROCESSENTRY32)
            if kernel32.Process32First(snapshot, ctypes.byref(entry)):
                while True:
                    pid_to_name[entry.th32ProcessID] = entry.szExeFile.decode(
                        errors="ignore"
                    ).lower()
                    pid_to_parent[entry.th32ProcessID] = entry.th32ParentProcessID
                    if not kernel32.Process32Next(snapshot, ctypes.byref(entry)):
                        break
        finally:
            kernel32.CloseHandle(snapshot)

        pid = os.getppid()
        seen: set[int] = set()
        while pid and pid not in seen:
            seen.add(pid)
            name = pid_to_name.get(pid)
            if name:
                classified = _classify_exe_name(name)
                if classified is not None:
                    return classified
            pid = pid_to_parent.get(pid, 0)
    except Exception:
        pass
    return None


def shell_name_from_proc() -> str | None:
    """Return shell name by inspecting the parent process.

    Uses ``/proc`` on Linux, environment heuristics plus a ToolHelp32
    process-tree walk on Windows, and ``ps`` on macOS/BSD — so this is
    not a POSIX-only or Linux-only signal.

    Returns:
        A lowercase shell name, or ``None`` if it cannot be determined.
    """
    if sys.platform == "win32":
        return _shell_name_from_windows_env() or _shell_name_from_windows_parent_process()
    if sys.platform == "darwin":
        return _shell_name_from_ps()
    return _shell_name_from_linux_proc() or _shell_name_from_ps()


def detect_shell() -> str | None:
    """Attempt to detect the current user's shell.

    Checks, in order: an explicit ``$QWIK_SHELL`` override, the
    Nushell/xonsh version variables, ``$SHELL``, and finally a
    platform-appropriate parent-process inspection. This is the only
    strategy that can identify ``cmd``, ``nu``, and ``xonsh`` at all, and
    the only one that works on Windows without ``$SHELL`` being set.

    Returns:
        A lowercase shell name (e.g. ``bash``, ``zsh``, ``pwsh``,
        ``cmd``, ``nu``, ``xonsh``), or ``None`` if nothing matched.
    """
    return (
        shell_name_from_override()
        or shell_name_from_version_env()
        or shell_name_from_env()
        or shell_name_from_proc()
    )
