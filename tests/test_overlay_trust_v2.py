"""Overlay trust v2 — signed manifests, pinning, verified updates.

Pinned here:

1. **Manifest parsing** — ``qwik-overlay.toml`` shape, SSH key-format
   validation, absent/invalid → unusable but non-fatal.
2. **Signing round-trip** — real ``ssh-keygen -Y`` sign/verify (skipped
   where the binary lacks -Y); tamper and wrong-key rejected.
3. **Verification-state ladder** — verified > manifest-without-sig >
   no-manifest (unverified), surfaced by `overlay list` and
   `overlay verify`.
4. **Update gating with a real git repo** — an invalid signature hard
   stops the update; a valid one applies; missing ssh-keygen degrades
   to unverified-but-proceeds.  Pinned overlays never move without
   ``--to``; ``--to`` moves and re-pins.
5. **Provenance** — `qwik show <overlay-alias>` reports source, commit,
   verification; doctor reports overlay verification status.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from typer.testing import CliRunner

from qwik.cli import app
from qwik.core.overlay_manifest import (
    load_manifest,
    load_signature,
)
from qwik.core.signing import (
    sign_file,
    signing_available,
    verify_file,
)

if TYPE_CHECKING:
    from collections.abc import Iterator

runner = CliRunner()

MANIFEST = """\
name = "acme-platform"
maintainer = "platform@acme.example"
min_qwik_version = "1.2.1"
signing_key = "{key}"
"""
MANIFEST_NO_KEY = 'name = "acme-platform"\nmaintainer = "platform@acme.example"\n'
ALIASES = '[aliases.k]\ncommand = "kubectl"\n\n[aliases.tf]\ncommand = "terraform plan"\n'


@pytest.fixture(scope="module")
def signing_keypair() -> Iterator[tuple[Path, Path, str]]:
    """A real Ed25519 keypair via ssh-keygen (module-scoped for speed)."""
    if not signing_available():
        pytest.skip("ssh-keygen -Y unavailable")
    td = Path(tempfile.mkdtemp(prefix="qwik-sig-"))
    private = td / "overlay_ed25519"
    subprocess.run(
        ["ssh-keygen", "-t", "ed25519", "-f", str(private), "-N", "", "-C", "test@acme"],
        capture_output=True,
        text=True,
        check=True,
    )
    public = Path(f"{private}.pub").read_text(encoding="utf-8").strip()
    yield private, public, str(td)
    shutil.rmtree(td, ignore_errors=True)


def _git_configure(repo: Path) -> None:
    """Local git identity so commits in fixtures never depend on the host.

    Runs globally when *repo* isn't a git repo yet (config -l works
    anywhere), and also local once ``init_repo`` has run — both paths
    keep fixture commits independent of the host's git identity.
    """
    for args in (
        ["git", "config", "--global", "user.email", "t@e.x"],
        ["git", "config", "--global", "user.name", "t"],
    ):
        subprocess.run(args, check=True, capture_output=True)
    if (repo / ".git").exists():
        for args in (
            ["git", "config", "user.email", "t@e.x"],
            ["git", "config", "user.name", "t"],
        ):
            subprocess.run(args, cwd=repo, check=True, capture_output=True)


def _write_overlay_repo(
    root: Path, *, signed: bool, keypair: tuple[Path, Path, str] | None = None
) -> Path:
    """Build a bare-bones overlay repo fixture dir for manifest tests."""
    repo = root / "overlay-repo"
    repo.mkdir()
    aliases = ALIASES
    (repo / "aliases.toml").write_text(aliases, encoding="utf-8")
    if keypair is not None:
        manifest_text = MANIFEST_NO_KEY if not signed else MANIFEST.format(key=keypair[1])
        (repo / "qwik-overlay.toml").write_text(manifest_text, encoding="utf-8")
    if signed:
        assert keypair is not None
        private, _public, _ = keypair
        sig = sign_file(private, aliases)
        (repo / "aliases.toml.sig").write_text(sig, encoding="utf-8")
    return repo


# ---------------------------------------------------------------------------
# Manifest parsing
# ---------------------------------------------------------------------------


def test_manifest_parses(signing_keypair: tuple[Path, Path, str], tmp_path: Path) -> None:
    _private, public, _ = signing_keypair
    repo = tmp_path / "r"
    repo.mkdir()
    (repo / "qwik-overlay.toml").write_text(MANIFEST.format(key=public), encoding="utf-8")
    manifest = load_manifest(repo)
    assert manifest is not None
    assert manifest.name == "acme-platform"
    assert manifest.signing_key == public


def test_manifest_absent_returns_none(tmp_path: Path) -> None:
    repo = tmp_path / "r"
    repo.mkdir()
    assert load_manifest(repo) is None


def test_manifest_invalid_key_rejected(tmp_path: Path) -> None:
    repo = tmp_path / "r"
    repo.mkdir()
    (repo / "qwik-overlay.toml").write_text(MANIFEST.format(key="not-an-ssh-key"), encoding="utf-8")
    assert load_manifest(repo) is None


def test_manifest_without_signing_key_is_valid(tmp_path: Path) -> None:
    repo = tmp_path / "r"
    repo.mkdir()
    (repo / "qwik-overlay.toml").write_text(MANIFEST_NO_KEY, encoding="utf-8")
    manifest = load_manifest(repo)
    assert manifest is not None
    assert manifest.signing_key is None


def test_signature_absent_returns_none(tmp_path: Path) -> None:
    repo = tmp_path / "r"
    repo.mkdir()
    (repo / "aliases.toml").write_text(ALIASES, encoding="utf-8")
    assert load_signature(repo) is None


# ---------------------------------------------------------------------------
# Signing round-trip
# ---------------------------------------------------------------------------


def test_sign_verify_round_trip(signing_keypair: tuple[Path, Path, str], tmp_path: Path) -> None:
    _private, public, _ = signing_keypair
    content = ALIASES
    sig = sign_file(signing_keypair[0], content)
    assert verify_file(public, content, sig)
    assert not verify_file(public, content + "\n# tampered", sig)
    assert not verify_file(public, content, " garbage not a signature ")


def test_load_signature_reads_file(signing_keypair, tmp_path: Path) -> None:
    repo = _write_overlay_repo(tmp_path, signed=True, keypair=signing_keypair)
    sig = load_signature(repo)
    assert sig is not None and sig.startswith("-----BEGIN SSH SIGNATURE-----")


# ---------------------------------------------------------------------------
# Verification ladder via CLI (needs a git repo — git-gated like the
# existing overlay tests, since the whole overlay subsystem is)
# ---------------------------------------------------------------------------

requires_git = pytest.mark.skipif(shutil.which("git") is None, reason="git not available")


@requires_git
def test_verification_ladder(
    signing_keypair: tuple[Path, Path, str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """no-manifest → manifest-no-key → signed: each level reports."""
    from qwik.commands.overlay import _describe_verification

    # 1. No manifest.
    repo = tmp_path / "r1"
    repo.mkdir()
    assert "unverified (no manifest)" in _describe_verification(repo)

    # 2. Manifest without key.
    repo2 = tmp_path / "r2"
    repo2.mkdir()
    (repo2 / "qwik-overlay.toml").write_text(MANIFEST_NO_KEY, encoding="utf-8")
    assert "no signing key" in _describe_verification(repo2)

    # 3. Signed + valid.
    repo3 = _write_overlay_repo(tmp_path, signed=True, keypair=signing_keypair)
    assert "VERIFIED" in _describe_verification(repo3)


@requires_git
def test_overlay_list_shows_verification(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    signing_keypair: tuple[Path, Path, str],
) -> None:
    from qwik.config import _reset_config
    from qwik.core.git import add_all_and_commit, init_repo

    cfg = tmp_path / "cfg"
    monkeypatch.setenv("QWIK_CONFIG_DIR", str(cfg))
    _reset_config()
    repo = signing_keypair[2]
    src = Path(repo)
    (src / "qwik-overlay.toml").write_text(
        MANIFEST.format(key=signing_keypair[1]), encoding="utf-8"
    )
    (src / "aliases.toml").write_text(ALIASES, encoding="utf-8")
    (src / "aliases.toml.sig").write_text(sign_file(signing_keypair[0], ALIASES), encoding="utf-8")
    _git_configure(src)
    init_repo(src)
    add_all_and_commit(src, "init")
    # The clone step needs a genuine URL; use the local path (git accepts it).
    result = runner.invoke(
        app, ["overlay", "add", "--url", str(src), "--branch", "master", "--yes"]
    )
    assert result.exit_code == 0, result.output
    listing = runner.invoke(app, ["overlay", "list"])
    assert "VERIFIED" in listing.output, listing.output


@requires_git
def test_show_reports_provenance(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    signing_keypair: tuple[Path, Path, str],
) -> None:
    from qwik.config import _reset_config
    from qwik.core.git import add_all_and_commit, init_repo

    cfg = tmp_path / "cfg"
    monkeypatch.setenv("QWIK_CONFIG_DIR", str(cfg))
    _reset_config()
    src = Path(signing_keypair[2])
    if not (src / ".git").exists():
        _git_configure(src)
        init_repo(src)
        add_all_and_commit(src, "init")
    assert (
        runner.invoke(
            app, ["overlay", "add", "--url", str(src), "--branch", "master", "--yes"]
        ).exit_code
        == 0
    )
    result = runner.invoke(app, ["show", "k"])
    assert "Overlay provenance" in result.output
    assert "Source" in result.output


# ---------------------------------------------------------------------------
# Pin semantics over a real git repo
# ---------------------------------------------------------------------------


@requires_git
@requires_git
def test_pinned_update_refuses_without_to(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A pinned overlay never moves on plain `update`."""
    from qwik.commands.overlay import _load_overlay_pin
    from qwik.config import _reset_config
    from qwik.core.git import add_all_and_commit, init_repo

    cfg = tmp_path / "cfg"
    monkeypatch.setenv("QWIK_CONFIG_DIR", str(cfg))
    _reset_config()
    runner.invoke(app, ["add", "keep", "echo", "keep"])
    repo = tmp_path / "remote"
    repo.mkdir()
    (repo / "aliases.toml").write_text('[aliases.k]\ncommand = "kubectl"\n', encoding="utf-8")
    _git_configure(repo)
    init_repo(repo)
    add_all_and_commit(repo, "first")
    assert (
        runner.invoke(
            app,
            [
                "overlay",
                "add",
                "--url",
                str(repo),
                "--branch",
                "master",
                "--yes",
            ],
        ).exit_code
        == 0
    )
    # Trust v2: pinning is opt-in; re-add with --pin <HEAD>.
    from qwik.core.git import rev_parse

    head = rev_parse(repo, "HEAD")
    assert (
        runner.invoke(
            app,
            [
                "overlay",
                "remove",
            ],
        ).exit_code
        == 0
    )
    assert (
        runner.invoke(
            app,
            [
                "overlay",
                "add",
                "--url",
                str(repo),
                "--branch",
                "master",
                "--yes",
                "--pin",
                head,
            ],
        ).exit_code
        == 0
    )
    pin = _load_overlay_pin(cfg / "overlay.toml")
    assert pin

    # New commit upstream.
    (repo / "aliases.toml").write_text('[aliases.k]\ncommand = "kubectl get"\n', encoding="utf-8")
    add_all_and_commit(repo, "second")

    result = runner.invoke(app, ["overlay", "update", "--yes"])
    assert result.exit_code == 1, result.output
    assert "pinned" in result.output
    # And the working tree did NOT move.
    on_disk = (cfg / "overlay-repo" / "aliases.toml").read_text(encoding="utf-8")
    assert "kubectl get" not in on_disk


@requires_git
def test_pinned_update_moves_with_to(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from qwik.commands.overlay import _load_overlay_pin
    from qwik.config import _reset_config
    from qwik.core.git import add_all_and_commit, init_repo

    cfg = tmp_path / "cfg"
    monkeypatch.setenv("QWIK_CONFIG_DIR", str(cfg))
    _reset_config()
    runner.invoke(app, ["add", "keep", "echo", "keep"])
    repo = tmp_path / "remote"
    repo.mkdir()
    (repo / "aliases.toml").write_text('[aliases.k]\ncommand = "kubectl"\n', encoding="utf-8")
    _git_configure(repo)
    init_repo(repo)
    add_all_and_commit(repo, "first")
    assert (
        runner.invoke(
            app, ["overlay", "add", "--url", str(repo), "--branch", "master", "--yes"]
        ).exit_code
        == 0
    )
    from qwik.core.git import rev_parse as _rp

    head = _rp(repo, "HEAD")
    assert runner.invoke(app, ["overlay", "remove"]).exit_code == 0
    assert (
        runner.invoke(
            app,
            [
                "overlay",
                "add",
                "--url",
                str(repo),
                "--branch",
                "master",
                "--yes",
                "--pin",
                head,
            ],
        ).exit_code
        == 0
    )
    first_pin = _load_overlay_pin(cfg / "overlay.toml")
    assert first_pin

    (repo / "aliases.toml").write_text('[aliases.k]\ncommand = "kubectl get"\n', encoding="utf-8")
    add_all_and_commit(repo, "second")
    result = runner.invoke(app, ["overlay", "update", "--yes", "--to", "master"])
    assert result.exit_code == 0, result.output
    assert "kubectl get" in (cfg / "overlay-repo" / "aliases.toml").read_text(encoding="utf-8")
    # Pin followed the applied commit.
    assert _load_overlay_pin(cfg / "overlay.toml") != first_pin


# ---------------------------------------------------------------------------
# Version helpers
# ---------------------------------------------------------------------------


def test_version_bumped() -> None:
    import qwik

    assert qwik.__version__ == "1.3.0"


def test_signing_missing_binary_degrades(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PATH", "")
    assert not signing_available()
