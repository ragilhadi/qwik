"""SSH signing for overlay manifests (``ssh-keygen -Y sign`` / ``-Y verify``).

SSH signing rather than GPG: every developer already has an SSH key and
git already supports the same format.  All operations shell out to
``ssh-keygen``; a missing binary degrades to "unverified" (callers
treat unsigned/never-verified overlays as marked, not broken) — see
:func:`signing_available`.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

__all__ = [
    "SigningError",
    "generate_signing_key",
    "public_key_fingerprint",
    "sign_file",
    "signing_available",
    "verify_file",
]


class SigningError(RuntimeError):
    """A signing/verification subprocess failed."""


def signing_available() -> bool:
    """Return ``True`` when ``ssh-keygen`` supports the ``-Y`` mode.

    OpenSSH 8.0+ ships ``-Y``; older/absent binaries degrade to
    :data:`None` callers must treat as "unverified", never a crash.
    """
    binary = shutil.which("ssh-keygen")
    if binary is None:
        return False
    result = subprocess.run(
        [binary, "-Y", "sign", "-h"],
        capture_output=True,
        text=True,
        check=False,
    )
    # OpenSSH ≥8.2 exits 2 with the usage string; older exits 1 with
    # "unknown option".  Either way a *usage* response means -Y exists
    # (the command was parsed), vs. an unknown-option error.
    combined = (result.stdout + result.stderr).lower()
    return "unknown option" not in combined


def generate_signing_key(comment: str) -> tuple[Path, Path]:
    """Generate an Ed25519 signing keypair; return ``(private, public)``.

    The private key lives in the user's config dir under
    ``overlay-signing``; the public key is what goes into the overlay
    repo's ``qwik-overlay.toml``.
    """
    if not signing_available():
        raise SigningError("ssh-keygen with -Y support not found on PATH.")
    from qwik.config import get_config

    key_dir = get_config().config_dir / "overlay-signing"
    key_dir.mkdir(parents=True, exist_ok=True)
    private = key_dir / "overlay_ed25519"
    if private.exists():
        raise SigningError(f"Signing key already exists at {private}.")
    result = subprocess.run(
        ["ssh-keygen", "-t", "ed25519", "-f", str(private), "-N", "", "-C", comment],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise SigningError(f"ssh-keygen failed: {result.stderr.strip()}")
    public = Path(str(private) + ".pub")
    if not public.exists():
        raise SigningError(f"Public key not generated at {public}")
    return private, public


def sign_file(private_key: Path, content: str, namespace: str = "qwik-overlay") -> str:
    """Return the SSH signature (*content* signed by *private_key*).

    Uses a temp file; the signature (not the file) is what lands in the
    repo as ``aliases.toml.sig``.
    """
    if not signing_available():
        raise SigningError("ssh-keygen with -Y support not found on PATH.")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td) / "payload"
        tmp.write_text(content, encoding="utf-8")
        env = {**os.environ, "SSH_SK_PROVIDER": "internal"}
        result = subprocess.run(
            [
                "ssh-keygen",
                "-Y",
                "sign",
                "-f",
                str(private_key),
                "-n",
                namespace,
                str(tmp),
            ],
            capture_output=True,
            text=True,
            check=False,
            env=env,
        )
        if result.returncode != 0:
            raise SigningError(f"ssh-keygen -Y sign failed: {result.stderr.strip()}")
        return (Path(td) / "payload.sig").read_text(encoding="utf-8")


def verify_file(
    public_key: str,
    content: str,
    signature: str,
    namespace: str = "qwik-overlay",
) -> bool:
    """Return ``True`` when *signature* verifies *content* against *public_key*.

    *public_key* is the bare key string from ``qwik-overlay.toml`` (e.g.
    ``ssh-ed25519 AAAA… comment@host``).  Verification failure — wrong
    key, tampered content, malformed signature — is ``False``, not an
    exception; only infrastructure failure (ssh-keygen missing) raises.
    """
    if not signing_available():
        raise SigningError("ssh-keygen with -Y support not found on PATH.")
    with tempfile.TemporaryDirectory() as td:
        payload = Path(td) / "payload"
        payload.write_text(content, encoding="utf-8")
        sig_path = payload.with_name("payload.sig")
        sig_path.write_text(signature, encoding="utf-8")
        allowed = Path(td) / "allowed_signers"
        # allowed_signers line: principals + key
        principal = "*"
        allowed.write_text(f"{principal} {public_key}\n", encoding="utf-8")
        result = subprocess.run(
            [
                "ssh-keygen",
                "-Y",
                "verify",
                "-f",
                str(allowed),
                "-I",
                principal,
                "-n",
                namespace,
                "-s",
                str(sig_path),
            ],
            input=content,
            capture_output=True,
            text=True,
            check=False,
        )
        return result.returncode == 0


def public_key_fingerprint(public_key: str) -> str:
    """Return the key comment (last word of ``ssh-ed25519 AAAA… comment``).

    Used in UI surfaces; no subprocess needed.
    """
    parts = public_key.strip().split()
    return parts[-1] if len(parts) >= 3 else public_key[:24]
