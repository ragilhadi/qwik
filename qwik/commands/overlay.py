"""``qwik overlay`` — team/shared read-only overlay store management."""

from __future__ import annotations

import os
import shutil
import stat
from pathlib import Path
from typing import TYPE_CHECKING

import tomlkit
import typer

from qwik.commands.importer import preview_import
from qwik.config import Config, get_config
from qwik.core.git import (
    clone as git_clone,
)
from qwik.core.git import (
    fetch as git_fetch,
)
from qwik.core.git import (
    git_available,
)
from qwik.core.git import (
    reset_hard as git_reset_hard,
)
from qwik.core.git import (
    show_file as git_show_file,
)
from qwik.core.models import AliasStore
from qwik.core.store import get_store
from qwik.ui.prompts import (
    print_error,
    print_info,
    print_success,
    print_warning,
    prompt_confirm,
)
from qwik.ui.theme import get_console

if TYPE_CHECKING:
    from collections.abc import Callable

    from rich.console import Console

__all__ = ["overlay_command"]

_DEFAULT_BRANCH = "main"

_MSG_NO_OVERLAY = "No overlay configured."


def _force_rmtree(path: Path) -> None:
    """Best-effort recursive delete that also clears Windows' read-only bit.

    git marks objects under ``.git/objects/pack`` (and sometimes more)
    read-only on Windows after a clone. A bare ``shutil.rmtree`` fails on
    those with ``PermissionError`` there — never on POSIX, where mode
    bits don't block unlink the same way — so pairing it with
    ``ignore_errors=True`` silently left the clone on disk while every
    caller believed cleanup had succeeded.
    """

    def _clear_readonly_and_retry(
        func: Callable[[str], object], target: str, _exc_info: BaseException
    ) -> None:
        try:
            os.chmod(target, stat.S_IWRITE)
            func(target)
        except OSError:
            pass

    shutil.rmtree(path, onexc=_clear_readonly_and_retry)


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


def _load_overlay_pin(config_file: Path) -> str | None:
    """Return the pinned commit hash from overlay config, if set."""
    if not config_file.exists():
        return None
    parsed = tomlkit.parse(config_file.read_text(encoding="utf-8"))
    pin = parsed.get("pin")
    return str(pin) if pin else None


def _save_overlay_pin(config_file: Path, commit: str | None) -> None:
    """Set or clear the ``pin`` field in overlay config (preserving the rest)."""
    if not config_file.exists():
        return
    doc = tomlkit.parse(config_file.read_text(encoding="utf-8"))
    if commit is None:
        if "pin" in doc:
            del doc["pin"]
    else:
        doc["pin"] = commit
    config_file.write_text(tomlkit.dumps(doc), encoding="utf-8")


def _load_overlay_key(config_file: Path) -> str | None:
    """Return the pinned SSH public key from overlay config, if set."""
    if not config_file.exists():
        return None
    parsed = tomlkit.parse(config_file.read_text(encoding="utf-8"))
    key = parsed.get("signing_key")
    return str(key) if key else None


def _save_overlay_key(config_file: Path, key: str) -> None:
    """Record the pinned SSH public key in overlay config."""
    doc = (
        tomlkit.parse(config_file.read_text(encoding="utf-8"))
        if config_file.exists()
        else tomlkit.document()
    )
    doc["signing_key"] = key
    config_file.parent.mkdir(parents=True, exist_ok=True)
    config_file.write_text(tomlkit.dumps(doc), encoding="utf-8")


def _save_overlay_config(config_file: Path, url: str, branch: str) -> None:
    doc = tomlkit.document()
    doc.add("url", url)
    doc.add("branch", branch)
    doc.add("auto_update", True)
    config_file.parent.mkdir(parents=True, exist_ok=True)
    config_file.write_text(tomlkit.dumps(doc), encoding="utf-8")


def _describe_verification(repo_dir: Path) -> str:
    """Return a human summary of the overlay's cryptographic trust state.

    Degradation ladder: ``verified`` (signed manifest with a pinned key
    and a valid signature over aliases.toml) → ``unsigned`` (manifest
    present, no signature) → ``unverified`` (no manifest at all).  A
    manifest whose signature is *invalid* is a hard problem and returns
    its own label.
    """
    from qwik.core.overlay_manifest import load_manifest, load_signature

    manifest = load_manifest(repo_dir)
    if manifest is None:
        return "unverified (no manifest)"
    if manifest.signing_key is None:
        return "manifest present, no signing key (unverified)"
    signature = load_signature(repo_dir)
    if signature is None:
        return "manifest present, no signature (unverified)"
    from qwik.core.signing import SigningError, signing_available, verify_file

    if not signing_available():
        return "signing unavailable (ssh-keygen -Y missing) — cannot verify"
    aliases_path = repo_dir / "aliases.toml"
    if not aliases_path.is_file():
        return "no aliases.toml to verify"
    try:
        ok = verify_file(
            manifest.signing_key,
            aliases_path.read_text(encoding="utf-8"),
            signature,
        )
    except SigningError as exc:
        return f"verification could not run ({exc})"
    if ok:
        return "VERIFIED (signature matches pinned key)"
    return "SIGNATURE INVALID — aliases.toml does not match its signature"


def _resolve_verify(repo_dir: Path) -> tuple[bool, str]:
    """Return ``(verified, status_text)`` used by update gating and UI."""
    text = _describe_verification(repo_dir)
    return (text.startswith("VERIFIED"), text)


def _read_overlay_aliases(overlay_file: Path) -> AliasStore:
    from qwik.core.migrations import migrate

    raw = overlay_file.read_text(encoding="utf-8")
    data = dict(tomlkit.parse(raw).unwrap())
    data = migrate(data)
    return AliasStore.model_validate(data)


def overlay_command(
    action: str = typer.Argument(..., help="add|remove|update|list|copy|verify"),
    name: str | None = typer.Argument(None, help="Alias name (for copy)."),
    url: str | None = typer.Option(None, "--url", help="Overlay repo URL (for add)."),
    branch: str = typer.Option(_DEFAULT_BRANCH, "--branch", help="Overlay repo branch."),
    key: str | None = typer.Option(
        None,
        "--key",
        help=(
            "Pinned SSH public key for the overlay (for add).  When set,"
            " updates verify aliases.toml's signature against this key."
        ),
    ),
    pin: str | None = typer.Option(
        None,
        "--pin",
        help=(
            "Pin to an exact commit (for add) — the overlay never moves"
            " with `update` until you pass `--to <commit>` explicitly."
        ),
    ),
    to: str | None = typer.Option(
        None,
        "--to",
        help="Move a pinned overlay to this commit (for update).",
    ),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation (for add/update)."),
) -> None:
    """Manage the team/shared read-only overlay store."""
    console = get_console()
    config = get_config()

    if action == "add":
        effective_url = url if url is not None else name
        _do_add(config, effective_url, branch, key=key, pin=pin, yes=yes, console=console)
    elif action == "remove":
        _do_remove(config, console=console)
    elif action == "update":
        _do_update(config, to_ref=to, yes=yes, console=console)
    elif action == "list":
        _do_list(config, console=console)
    elif action == "copy":
        if name is None:
            print_error("Usage: qwik overlay copy <name>", console=console)
            raise typer.Exit(1)
        _do_copy(config, name, console=console)
    elif action == "verify":
        _do_verify(config, console=console)
    else:
        print_error(
            f"Unknown overlay action '{action}'.",
            suggestion="Use one of: add, remove, update, list, copy, verify.",
            console=console,
        )
        raise typer.Exit(1)


def _do_add(
    config: Config,
    url: str | None,
    branch: str,
    *,
    key: str | None = None,
    pin: str | None = None,
    yes: bool,
    console: Console,
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
    if overlay_repo.exists():
        print_error(
            "Overlay already configured.",
            suggestion="Run `qwik overlay remove` first, or `qwik overlay update` to refresh.",
            console=console,
        )
        raise typer.Exit(1)

    overlay_repo.parent.mkdir(parents=True, exist_ok=True)
    try:
        # A fresh clone (rather than init + remote add + pull) always
        # leaves a proper upstream tracking branch and can never enter a
        # merge-conflict state — the overlay is read-only by design, so
        # there is nothing to merge.
        git_clone(url, overlay_repo, branch)
    except RuntimeError as exc:
        print_error(f"Failed to clone overlay: {exc}", console=console)
        _force_rmtree(overlay_repo)
        raise typer.Exit(1) from exc

    overlay_file = config.overlay_aliases_file
    if not overlay_file.exists():
        print_warning(
            f"No aliases.toml found in overlay repo at {overlay_file}.",
            console=console,
        )
        _save_overlay_config(config.overlay_config_file, url, branch)
        print_info("Run `qwik overlay update` to refresh.", console=console)
        return

    try:
        incoming = _read_overlay_aliases(overlay_file)
    except Exception as exc:
        print_error(f"Could not read overlay aliases: {exc}", console=console)
        _force_rmtree(overlay_repo)
        raise typer.Exit(1) from exc

    store = get_store()
    user_data = store.load()
    # Same trust-boundary preview `qwik import` and `qwik sync pull`
    # show — the overlay is the most remote of the three ingestion
    # paths (a repo controlled by someone else, refreshed on demand),
    # and was previously the only one without a gate. Declining leaves
    # nothing configured, matching import's "no partial state" behavior.
    if not preview_import(incoming, user_data, yes=yes, console=console):
        _force_rmtree(overlay_repo)
        raise typer.Exit(0)

    _save_overlay_config(config.overlay_config_file, url, branch)
    if key is not None or pin is not None:
        if key is not None:
            _save_overlay_key(config.overlay_config_file, key)
        if pin is not None:
            _save_overlay_pin(config.overlay_config_file, pin)
        if pin is not None:
            print_info(
                f"Overlay pinned to {pin}; `update` will not move it without `--to <commit>`.",
                console=console,
            )
        else:
            print_info(
                "Overlay key recorded; `update` verifies aliases.toml against it.",
                console=console,
            )
    print_success(
        f"Overlay configured with {len(incoming.aliases)} aliases.",
        console=console,
    )
    print_info("Run `qwik overlay update` to refresh.", console=console)


def _do_remove(config: Config, *, console: Console) -> None:
    config_file = config.overlay_config_file
    overlay_repo = config.overlay_repo_dir
    if not config_file.exists() and not overlay_repo.exists():
        print_error(_MSG_NO_OVERLAY, console=console)
        raise typer.Exit(1)

    if config_file.exists():
        config_file.unlink()
    if overlay_repo.exists():
        _force_rmtree(overlay_repo)
    print_success("Overlay removed.", console=console)


def _do_update(config: Config, *, to_ref: str | None, yes: bool, console: Console) -> None:
    config_file = config.overlay_config_file
    overlay_repo = config.overlay_repo_dir

    if not config_file.exists():
        print_error(_MSG_NO_OVERLAY, console=console)
        raise typer.Exit(1)

    url, branch, _ = _load_overlay_config(config_file)
    pinned = _load_overlay_pin(config_file)

    if not git_available():
        print_error("git not found on PATH.", console=console)
        raise typer.Exit(1)

    try:
        git_fetch(overlay_repo, "origin", branch)
    except RuntimeError as exc:
        print_error(f"Failed to fetch overlay: {exc}", console=console)
        raise typer.Exit(1) from exc

    from qwik.core.git import rev_parse

    # Pin semantics: a pinned overlay never moves without `--to`.  The
    # fetch is harmless (nothing in the working tree changed), but any
    # apply step below is gated on the explicit move.
    target_commit = None
    if to_ref is not None:
        # Resolution order: origin/<to> first (the clone's local branch
        # may lag the fetched remote), then the literal ref for
        # explicit hashes/tags.
        for candidate in (f"origin/{to_ref}", to_ref):
            try:
                target_commit = rev_parse(overlay_repo, candidate)
                break
            except RuntimeError:
                continue
        if target_commit is None:
            print_error(
                f"--to {to_ref}: not a commit, tag, or branch reachable after fetch.",
                console=console,
            )
            raise typer.Exit(1)
        if pinned is not None and target_commit != pinned:
            print_info(
                f"Overlay moves {pinned[:12]} → {target_commit[:12]} (explicit --to).",
                console=console,
            )
    elif pinned is not None:
        # Always compare against the fetched remote head: HEAD being at
        # the pin says nothing about whether upstream moved.
        remote_head = rev_parse(overlay_repo, f"origin/{branch}")
        if remote_head == pinned:
            print_info(
                f"Overlay is pinned to {pinned[:12]}; origin/{branch} is"
                " unchanged. Use `overlay update --to <commit>` to move.",
                console=console,
            )
            return
        print_error(
            f"Overlay is pinned to {pinned[:12]}; origin/{branch} is at {remote_head[:12]}.",
            suggestion="Move explicitly: qwik overlay update --to <commit>",
            console=console,
        )
        raise typer.Exit(1)

    # Signature verification (trust v2): when the overlay carries a
    # manifest with a pinned key and a signature, verify aliases.toml at
    # the *incoming* ref.  A signature that does not verify is a hard
    # stop — the update is never applied — but an overlay without
    # signing simply proceeds (marked unverified), keeping signing opt-in.
    from qwik.core.overlay_manifest import (
        ALIASES_FILE_NAME,
        load_manifest,
        load_signature,
    )

    manifest = load_manifest(overlay_repo)
    signature = load_signature(overlay_repo)
    verify_msg: str | None = None
    if manifest is not None and manifest.signing_key is not None and signature is not None:
        from qwik.core.signing import SigningError, signing_available, verify_file

        if not signing_available():
            verify_msg = "ssh-keygen -Y unavailable; overlay NOT verified (proceeding unverified)"
        else:
            try:
                incoming_raw = git_show_file(overlay_repo, f"origin/{branch}", ALIASES_FILE_NAME)
                incoming_ok = verify_file(manifest.signing_key, incoming_raw, signature)
            except (SigningError, RuntimeError) as exc:
                incoming_ok = False
                verify_msg = f"verification could not run ({exc})"
            if not incoming_ok:
                print_error(
                    f"Overlay signature does NOT verify against the pinned key"
                    f" for origin/{branch}. Update not applied.",
                    suggestion=(
                        "Check that the repo's aliases.toml was signed by the"
                        " maintainer key you pinned with `overlay add --key`;"
                        " if the key rotated, re-pin with `overlay remove` +"
                        " `overlay add --key <new>`."
                    ),
                    console=console,
                )
                raise typer.Exit(1)
            verify_msg = "signature VERIFIED"

    incoming = _read_incoming_at_ref(overlay_repo, f"origin/{branch}")
    current = (
        _read_overlay_aliases(config.overlay_aliases_file)
        if config.overlay_aliases_file.exists()
        else AliasStore()
    )

    added = sorted(set(incoming.aliases) - set(current.aliases))
    removed = sorted(set(current.aliases) - set(incoming.aliases))
    changed = sorted(
        n
        for n in set(incoming.aliases) & set(current.aliases)
        if incoming.aliases[n].command != current.aliases[n].command
        or incoming.aliases[n].command_variants != current.aliases[n].command_variants
    )

    if not added and not removed and not changed:
        print_info(f"Overlay already up to date ({url}, {branch}).", console=console)
        if verify_msg:
            print_info(verify_msg, console=console)
        return

    # Same trust-boundary preview qwik import/sync pull show, plus the
    # removal set (an update that only lists additions would hide that
    # an alias is disappearing from every member's shell hook).  Changed
    # commands show before → after: a modified command is the
    # highest-risk change and the easiest to miss in a name list.
    console.print(f"[qwik.warning]Overlay changes from {url} ({branch}):[/qwik.warning]")
    if verify_msg:
        console.print(f"  {verify_msg}")
    if added:
        console.print(f"[qwik.success]Added ({len(added)}):[/qwik.success] {', '.join(added)}")
    if changed:
        console.print(
            f"[qwik.warning]Changed ({len(changed)}):[/qwik.warning] {', '.join(changed)}"
        )
        for n in changed:
            console.print(f"    - {current.aliases[n].command!r}")
            console.print(f"    + {incoming.aliases[n].command!r}")
    if removed:
        console.print(f"[qwik.error]Removed ({len(removed)}):[/qwik.error] {', '.join(removed)}")
    console.print(
        "[qwik.warning]Overlay aliases are a trust boundary — stored commands "
        "will run under `shell=True` once rendered into your shell hook.[/qwik.warning]"
    )
    if not yes:
        if not prompt_confirm("Apply overlay update?", default=False, console=console):
            raise typer.Exit(0)

    # A hard reset (rather than a merge pull) is correct because the
    # overlay is read-only by design: the local checkout should always
    # exactly mirror the remote branch (or the explicitly requested
    # commit), never diverge from it.
    reset_target = target_commit or f"origin/{branch}"
    git_reset_hard(overlay_repo, reset_target)
    if pinned is not None and to_ref is not None:
        # The user explicitly moved a pinned overlay: the pin follows the
        # applied commit, otherwise the next update would report a stale
        # pin and require another --to to no effect.
        _save_overlay_pin(config_file, target_commit)
    print_success(
        f"Overlay updated to {reset_target}: "
        f"{len(added)} added, {len(changed)} changed, {len(removed)} removed.",
        console=console,
    )


def _read_incoming_at_ref(overlay_repo: Path, ref: str) -> AliasStore:
    """Read ``aliases.toml`` from *ref* without touching the working tree.

    Used to preview an incoming overlay update after ``fetch`` but before
    ``reset --hard`` applies it.
    """
    from qwik.core.migrations import migrate

    try:
        raw = git_show_file(overlay_repo, ref, "aliases.toml")
    except RuntimeError:
        return AliasStore()
    data = dict(tomlkit.parse(raw).unwrap())
    data = migrate(data)
    return AliasStore.model_validate(data)


def _do_verify(config: Config, *, console: Console) -> None:
    """Check the configured overlay's signature right now."""
    overlay_repo = config.overlay_repo_dir
    if not config.overlay_config_file.exists():
        print_error(_MSG_NO_OVERLAY, console=console)
        raise typer.Exit(1)
    status = _describe_verification(overlay_repo)
    ok = status.startswith("VERIFIED")
    if ok:
        print_success(f"Overlay signature: {status}", console=console)
    else:
        print_warning(f"Overlay signature: {status}", console=console)
        if not ok and "INVALID" in status:
            raise typer.Exit(1)


def _do_list(config: Config, *, console: Console) -> None:
    config_file = config.overlay_config_file

    if not config_file.exists():
        print_info(_MSG_NO_OVERLAY, console=console)
        return

    url, branch, auto_update = _load_overlay_config(config_file)
    console.print(f"[bold]Overlay:[/bold] {url} ({branch})")
    console.print(f"  Auto-update: {'on' if auto_update else 'off'}")
    from qwik.core.overlay_manifest import load_manifest as _load_manifest

    pinned = _load_overlay_pin(config_file)
    if pinned:
        console.print(f"  Pinned: {pinned} (--to to move)")
    manifest = _load_manifest(config.overlay_repo_dir)
    if manifest is not None:
        console.print(
            f"  Manifest: {manifest.name}"
            + (f" <{manifest.maintainer}>" if manifest.maintainer else "")
        )
    verification = _describe_verification(config.overlay_repo_dir)
    style = "dim" if not verification.startswith("VERIFIED") else "green"
    console.print(f"  Signature: [{style}]{verification}[/{style}]")

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


def _do_copy(config: Config, name: str, *, console: Console) -> None:
    overlay_file = config.overlay_aliases_file
    if overlay_file.exists():
        try:
            incoming = _read_overlay_aliases(overlay_file)
        except Exception as exc:
            print_error(f"Could not read overlay: {exc}", console=console)
            raise typer.Exit(1) from exc
    else:
        incoming = AliasStore()

    if name not in incoming.aliases:
        print_error(f"'{name}' is not an overlay alias.", console=console)
        raise typer.Exit(1)

    store = get_store()
    with store.mutate() as data:
        if name in data.aliases:
            print_warning(f"'{name}' already exists in user store.", console=console)
            raise typer.Exit(0)

        data.add(name, incoming.aliases[name])
    print_success(f"Copied '{name}' from overlay to user store.", console=console)
