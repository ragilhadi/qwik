"""``qwik-overlay.toml`` — manifest parse/validate for overlay trust v2.

Lives in the overlay repo next to ``aliases.toml``:

    name = "acme-platform"
    maintainer = "platform@acme.example"
    min_qwik_version = "1.2.1"
    signing_key = "ssh-ed25519 AAAA… maintainer@host"

An overlay *without* a manifest keeps working (signing is opt-in) but is
marked ``unverified`` everywhere it appears — the degradation ladder is:
signed+verified > manifest-without-signature > no manifest (unverified).
"""

from __future__ import annotations

import re
from pathlib import Path

import tomlkit
from pydantic import BaseModel, ConfigDict, field_validator
from tomlkit.exceptions import TOMLKitError

__all__ = [
    "ALIASES_FILE_NAME",
    "MANIFEST_FILE_NAME",
    "SIGNATURE_FILE_NAME",
    "OverlayManifest",
    "load_manifest",
    "load_signature",
]

MANIFEST_FILE_NAME = "qwik-overlay.toml"
ALIASES_FILE_NAME = "aliases.toml"
SIGNATURE_FILE_NAME = "aliases.toml.sig"

_SSH_KEY_RE = re.compile(r"^(ssh-(ed25519|rsa|dss)|ecdsa-sha2-\S+|sk-\S+)\s+\S+(\s+\S.*)?$")


class OverlayManifest(BaseModel):
    """Validated ``qwik-overlay.toml``."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str
    maintainer: str = ""
    min_qwik_version: str = ""
    signing_key: str | None = None

    @field_validator("signing_key")
    @classmethod
    def _validate_key(cls, v: str | None) -> str | None:
        if v is not None and not _SSH_KEY_RE.match(v):
            raise ValueError(
                "signing_key must be a public SSH key line (e.g. 'ssh-ed25519 AAAA… comment')"
            )
        return v


def load_manifest(repo_dir: Path) -> OverlayManifest | None:
    """Parse the manifest from *repo_dir*; ``None`` when absent/invalid.

    Invalid manifests are not a hard error — the overlay keeps working,
    unverified — but the parse problem is surfaced in the UI (status).
    """
    path = repo_dir / MANIFEST_FILE_NAME
    if not path.is_file():
        return None
    try:
        data = tomlkit.parse(path.read_text(encoding="utf-8")).unwrap()
    except TOMLKitError:
        return None
    if not isinstance(data, dict):
        return None
    if "name" not in data:
        return None
    try:
        return OverlayManifest.model_validate(data)
    except Exception:
        return None


def load_signature(repo_dir: Path) -> str | None:
    """Return the detached signature text, or ``None`` when absent."""
    path = repo_dir / SIGNATURE_FILE_NAME
    if not path.is_file():
        return None
    return path.read_text(encoding="utf-8")
