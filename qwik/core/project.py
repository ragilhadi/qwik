"""Project-scoped aliases: ``.qwik.toml`` discovery and trust management.

A repository can ship a ``.qwik.toml`` defining aliases that only apply
for shells running inside that tree (precedence: project → user →
overlay).  Because a ``.qwik.toml`` arrives by ``git clone`` — from
whoever wrote the repo — it is **untrusted code by definition**: a
newly-seen file is *inert* until ``qwik project trust`` is run in that
directory.  Trust is recorded per absolute path plus a SHA-256 content
hash; when the file's content changes, trust reverts to inert and the
user is asked to review.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import tomlkit
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from tomlkit.exceptions import TOMLKitError

from qwik.core.models import Alias

__all__ = [
    "PROJECT_FILE_NAME",
    "ProjectFile",
    "ProjectLayer",
    "TrustState",
    "TrustStore",
    "discover_project",
    "hash_project_file",
    "load_project_layer",
    "save_trust_store",
]


PROJECT_FILE_NAME = ".qwik.toml"


class ProjectFile(BaseModel):
    """Parsed ``.qwik.toml``."""

    model_config = ConfigDict(extra="forbid")

    version: int = 1
    aliases: dict[str, Alias] = Field(default_factory=dict)


class TrustState(BaseModel):
    """One trusted directory entry in ``trusted.toml``."""

    model_config = ConfigDict(extra="forbid")

    sha256: str


class TrustStore(BaseModel):
    """Contents of ``<config_dir>/trusted.toml``."""

    model_config = ConfigDict(extra="forbid")

    version: int = 1
    trusted: dict[str, TrustState] = Field(default_factory=dict)  # path → sha256


def hash_project_file(content: str) -> str:
    """Return the SHA-256 hex digest of *content*."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


class ProjectLayer(BaseModel):
    """A discovered (but not necessarily trusted) project layer."""

    model_config = ConfigDict(extra="forbid")

    path: Path
    sha256: str
    file: ProjectFile | None  # None when the file failed to parse
    parse_error: str | None = None
    trust: str  # "trusted" | "stale" | "untrusted" | "none"


def discover_project(start: Path | None = None) -> ProjectLayer | None:
    """Find the active ``.qwik.toml`` from *start* (default cwd) upward.

    Stops at the filesystem root and at ``$HOME`` (a stray ``.qwik.toml``
    in the home directory itself is not treated as a project file — that
    is what the user store is for).  Returns ``None`` when nothing is
    found.
    """
    directory = (start or Path.cwd()).resolve()
    home = Path.home().resolve()
    while True:
        candidate = directory / PROJECT_FILE_NAME
        if candidate.is_file():
            return _classify(candidate)
        if directory == home or directory.parent == directory:
            return None
        directory = directory.parent


def load_project_layer(layer: ProjectLayer) -> dict[str, Alias]:
    """Return the trusted layer's aliases; empty when not fully trusted."""
    if layer.trust != "trusted" or layer.file is None:
        return {}
    return dict(layer.file.aliases)


def _classify(path: Path) -> ProjectLayer:
    """Read, parse, and trust-classify one candidate ``.qwik.toml``."""
    content = path.read_text(encoding="utf-8")
    sha = hash_project_file(content)
    file: ProjectFile | None = None
    parse_error: str | None = None
    try:
        parsed = tomlkit.parse(content).unwrap()
        file = ProjectFile.model_validate(parsed)
    except (TOMLKitError, ValidationError) as exc:
        parse_error = str(exc).splitlines()[0]

    trust_store = load_trust_store()
    entry = trust_store.trusted.get(str(path))
    if entry is None:
        trust = "untrusted"
    elif entry.sha256 == sha:
        trust = "trusted"
    else:
        trust = "stale"
    return ProjectLayer(
        path=path,
        sha256=sha,
        file=file,
        parse_error=parse_error,
        trust=trust,
    )


def _trust_file_path() -> Path:
    """Return the trust store path (``<config_dir>/trusted.toml``)."""
    from qwik.config import get_config

    return get_config().config_dir / "trusted.toml"


def _trust_doc_to_model(doc: object) -> TrustStore:
    data = doc.unwrap() if hasattr(doc, "unwrap") else doc
    if not isinstance(data, dict):  # pragma: no cover - defensive
        return TrustStore()
    try:
        return TrustStore.model_validate(data)
    except ValidationError:
        return TrustStore()


def _load_trust_doc() -> TrustStore:
    path = _trust_file_path()
    if not path.exists():
        return TrustStore()
    try:
        return _trust_doc_to_model(tomlkit.parse(path.read_text(encoding="utf-8")))
    except TOMLKitError:
        return TrustStore()


def _write_trust_doc(store: TrustStore) -> None:
    path = _trust_file_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = tomlkit.document()
    doc.add("version", store.version)
    table = tomlkit.table()
    for trusted_path in sorted(store.trusted):
        entry = tomlkit.table()
        entry.add("sha256", store.trusted[trusted_path].sha256)
        table.add(trusted_path, entry)
    doc.add("trusted", table)
    path.write_text(tomlkit.dumps(doc), encoding="utf-8")


def load_trust_store() -> TrustStore:
    """Return the trust store from ``<config_dir>/trusted.toml``.

    A missing or unparseable file yields an empty store (no trust
    recorded), never an error — the trust file is incidental state, and a
    corrupt one must not brick alias discovery.
    """
    try:
        doc = tomlkit.parse(_trust_file_path().read_text(encoding="utf-8")).unwrap()
    except (OSError, TOMLKitError):
        return TrustStore()
    if not isinstance(doc, dict):
        return TrustStore()
    try:
        return TrustStore.model_validate(doc)
    except ValidationError:
        return TrustStore()


def save_trust_store(store: TrustStore) -> None:
    """Persist *store* atomically enough for a single-user CLI."""
    _write_trust_doc(store)
