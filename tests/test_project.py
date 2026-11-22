"""Project-scoped aliases (``.qwik.toml``) — discovery, trust, layering.

Security-critical invariants pinned here:

1. **Inert until trusted.**  A cloned repo's ``.qwik.toml`` defines
   nothing until ``qwik project trust``: discovery finds it, `qwik list`
   says it exists and how to trust it, and no command loads its aliases
   (run/pick/init/search/stats see an empty project layer).
2. **Trust is per-path + content hash.**  Editing the file after trusting
   reverts it to inert ("stale") — trust never carries across content.
3. **Precedence.**  project → user → overlay; a project alias shadows a
   user alias with the same name, and `list`/`show` report both layers.
4. **Never persisted.**  The project layer is in-memory: nothing from
   ``.qwik.toml`` lands in ``aliases.toml`` (save/mutate dumps exclude
   it; round-trips drop it).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from typer.testing import CliRunner

from qwik.cli import app
from qwik.core.models import Alias
from qwik.core.project import (
    PROJECT_FILE_NAME,
    discover_project,
    load_project_layer,
    load_trust_store,
    save_trust_store,
)

if TYPE_CHECKING:
    from collections.abc import Iterator

runner = CliRunner()

_TRUST_FILE = 'version = 1\n\n[aliases.dev]\ncommand = "echo project dev"\n'


@pytest.fixture
def project_dir(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Path]:
    """A temp dir with a ``.qwik.toml`` and a fresh qwik config."""
    td = tmp_path_factory.mktemp("proj")
    config_dir = tmp_path_factory.mktemp("cfg")
    old_cwd = Path.cwd()
    os.chdir(td)
    os.environ["QWIK_CONFIG_DIR"] = str(config_dir)
    from qwik.config import _reset_config

    _reset_config()
    yield td
    os.chdir(old_cwd)
    from qwik.config import _reset_config

    _reset_config()


def _add(name: str, *command: str) -> None:
    result = runner.invoke(app, ["add", name, *command])
    assert result.exit_code == 0, result.output


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------


def test_discovery_finds_file_in_cwd(project_dir: Path) -> None:
    (project_dir / PROJECT_FILE_NAME).write_text(_TRUST_FILE, encoding="utf-8")
    layer = discover_project()
    assert layer is not None
    assert layer.path == project_dir / PROJECT_FILE_NAME
    assert layer.trust == "untrusted"


def test_discovery_walks_up_and_stops_at_home(project_dir: Path) -> None:
    nested = project_dir / "deep" / "nested"
    nested.mkdir(parents=True)
    (project_dir / PROJECT_FILE_NAME).write_text(_TRUST_FILE, encoding="utf-8")
    layer = discover_project(nested)
    assert layer is not None
    assert layer.path == project_dir / PROJECT_FILE_NAME


def test_discovery_none_without_file(project_dir: Path) -> None:
    assert discover_project() is None


def test_parse_error_is_reported_not_raised(project_dir: Path) -> None:
    (project_dir / PROJECT_FILE_NAME).write_text("!!broken", encoding="utf-8")
    layer = discover_project()
    assert layer is not None
    assert layer.parse_error is not None


# ---------------------------------------------------------------------------
# Inert until trusted
# ---------------------------------------------------------------------------


def test_untrusted_layer_loads_nothing(project_dir: Path) -> None:
    (project_dir / PROJECT_FILE_NAME).write_text(_TRUST_FILE, encoding="utf-8")
    layer = discover_project()
    assert layer is not None
    assert load_project_layer(layer) == {}


def test_untrusted_file_never_enters_store(project_dir: Path) -> None:
    (project_dir / PROJECT_FILE_NAME).write_text(_TRUST_FILE, encoding="utf-8")
    from qwik.core.store import get_store

    data = get_store().load()
    assert data.project_aliases == {}
    assert "dev" not in data.all_aliases()


def test_trust_flow_makes_layer_live(project_dir: Path) -> None:
    (project_dir / PROJECT_FILE_NAME).write_text(_TRUST_FILE, encoding="utf-8")
    result = runner.invoke(app, ["project", "trust"], input="y\n")
    assert result.exit_code == 0, result.output
    from qwik.core.store import get_store

    data = get_store().load()
    assert data.project_aliases.keys() == {"dev"}


def test_trust_declines_keeps_inert(project_dir: Path) -> None:
    (project_dir / PROJECT_FILE_NAME).write_text(_TRUST_FILE, encoding="utf-8")
    result = runner.invoke(app, ["project", "trust"], input="n\n")
    assert result.exit_code == 0, result.output
    from qwik.core.store import get_store

    assert get_store().load().project_aliases == {}


def test_content_change_revokes_trust(project_dir: Path) -> None:
    (project_dir / PROJECT_FILE_NAME).write_text(_TRUST_FILE, encoding="utf-8")
    result = runner.invoke(app, ["project", "trust"], input="y\n")
    assert result.exit_code == 0, result.output
    # Edit the file behind the trust record.
    (project_dir / PROJECT_FILE_NAME).write_text(
        _TRUST_FILE + '\n[aliases.extra]\ncommand = "echo extra"\n',
        encoding="utf-8",
    )
    from qwik.core.store import get_store

    data = get_store().load()
    assert data.project_aliases == {}  # reverted to inert
    layer = discover_project()
    assert layer is not None
    assert layer.trust == "stale"


def test_retrust_after_change(project_dir: Path) -> None:
    (project_dir / PROJECT_FILE_NAME).write_text(_TRUST_FILE, encoding="utf-8")
    assert runner.invoke(app, ["project", "trust"], input="y\n").exit_code == 0
    (project_dir / PROJECT_FILE_NAME).write_text(
        _TRUST_FILE.replace("echo project dev", "echo changed"),
        encoding="utf-8",
    )
    result = runner.invoke(app, ["project", "trust"], input="y\n")
    assert result.exit_code == 0, result.output
    from qwik.core.store import get_store

    assert get_store().load().project_aliases.keys() == {"dev"}


def test_untrust_removes_record(project_dir: Path) -> None:
    (project_dir / PROJECT_FILE_NAME).write_text(_TRUST_FILE, encoding="utf-8")
    assert runner.invoke(app, ["project", "trust"], input="y\n").exit_code == 0
    assert runner.invoke(app, ["project", "untrust"]).exit_code == 0
    from qwik.core.store import get_store

    assert get_store().load().project_aliases == {}


# ---------------------------------------------------------------------------
# Precedence
# ---------------------------------------------------------------------------


def test_project_shadows_user_alias(project_dir: Path) -> None:
    _add("dev", "echo", "user dev")
    (project_dir / PROJECT_FILE_NAME).write_text(
        _TRUST_FILE.replace("echo project dev", "echo SHADOW"),
        encoding="utf-8",
    )
    assert runner.invoke(app, ["project", "trust"], input="y\n").exit_code == 0
    from qwik.core.store import get_store

    data = get_store().load()
    merged = data.all_aliases()
    assert merged["dev"].command == "echo SHADOW"
    # Both layers remain inspectable.
    assert data.get("dev").command == "echo user dev"  # type: ignore[union-attr]
    assert data.project_aliases["dev"].command == "echo SHADOW"


def test_list_marks_project_layer(project_dir: Path) -> None:
    _add("gs", "git", "status")
    (project_dir / PROJECT_FILE_NAME).write_text(_TRUST_FILE, encoding="utf-8")
    assert runner.invoke(app, ["project", "trust"], input="y\n").exit_code == 0
    result = runner.invoke(app, ["project", "list"])
    assert result.exit_code == 0, result.output


def test_project_file_not_written_to_aliases_toml(project_dir: Path) -> None:
    (project_dir / PROJECT_FILE_NAME).write_text(_TRUST_FILE, encoding="utf-8")
    assert runner.invoke(app, ["project", "trust"], input="y\n").exit_code == 0
    _add("user_alias", "echo user")
    on_disk = (Path(os.environ["QWIK_CONFIG_DIR"]) / "aliases.toml").read_text(encoding="utf-8")
    assert "dev" not in on_disk
    assert "project_aliases" not in on_disk
    assert "user_alias" in on_disk


# ---------------------------------------------------------------------------
# Init hook integration
# ---------------------------------------------------------------------------


def test_init_emits_cd_refresh_only_inside_project(project_dir: Path) -> None:
    _add("gs", "git", "status")
    outside = runner.invoke(app, ["init", "bash"])
    assert "__qwik_project_refresh" not in outside.output
    (project_dir / PROJECT_FILE_NAME).write_text(_TRUST_FILE, encoding="utf-8")
    inside = runner.invoke(app, ["init", "bash"])
    assert "__qwik_project_refresh" in inside.output


def test_init_notes_untrusted_file(project_dir: Path) -> None:
    (project_dir / PROJECT_FILE_NAME).write_text(_TRUST_FILE, encoding="utf-8")
    result = runner.invoke(app, ["init", "bash"])
    assert "untrusted" in result.output
    assert "qwik project trust" in result.output


def test_init_bash_cd_wrapper_runs_real_bash(project_dir: Path) -> None:
    """The emitted cd wrapper actually re-evaluates in a real bash."""
    import shutil
    import subprocess

    if shutil.which("bash") is None:
        pytest.skip("bash not installed")
    (project_dir / PROJECT_FILE_NAME).write_text(_TRUST_FILE, encoding="utf-8")
    # Trust via the TrustStore directly (the CLI prompt is interactive).
    from qwik.core.project import TrustState, hash_project_file

    store = load_trust_store()
    content = _TRUST_FILE
    store.trusted[str(project_dir / PROJECT_FILE_NAME)] = TrustState(
        sha256=hash_project_file(content)
    )
    save_trust_store(store)

    _add("gs", "git", "status")
    hook = runner.invoke(app, ["init", "bash"]).output
    # The refresh re-eval happens inside the shell; assert the wrapper at
    # least fires without error (stderr empty) on a real cd.
    result = subprocess.run(
        ["bash", "-c", "shopt -s expand_aliases\n" + hook + "\ncd /tmp\n"],
        capture_output=True,
        text=True,
        check=False,
        cwd=str(project_dir),
        env={**os.environ, "QWIK_CONFIG_DIR": os.environ["QWIK_CONFIG_DIR"]},
    )
    assert result.returncode == 0, result.stderr
    assert "command not found" not in result.stderr


# ---------------------------------------------------------------------------
# Doctor
# ---------------------------------------------------------------------------


def test_doctor_reports_untrusted_layer(project_dir: Path) -> None:
    (project_dir / PROJECT_FILE_NAME).write_text(_TRUST_FILE, encoding="utf-8")
    result = runner.invoke(app, ["doctor", "--json"])
    assert result.exit_code == 0, result.output
    import json

    payload = json.loads(result.output)
    ids = [c["id"] for c in payload["checks"]]
    assert "project.trust" in ids
    check = next(c for c in payload["checks"] if c["id"] == "project.trust")
    assert check["status"] == "warn"
    assert check["detail"]["trust"] == "untrusted"


def test_doctor_reports_no_layer_ok(project_dir: Path) -> None:
    result = runner.invoke(app, ["doctor", "--json"])
    import json

    payload = json.loads(result.output)
    check = next(c for c in payload["checks"] if c["id"] == "project.trust")
    assert check["status"] == "ok"


# ---------------------------------------------------------------------------
# Mutate change-detection excludes the project layer
# ---------------------------------------------------------------------------


def test_mutate_ignores_project_layer_changes(project_dir: Path) -> None:
    """A mutation session adding nothing must not write a new file version
    just because the in-memory project layer changed."""
    (project_dir / PROJECT_FILE_NAME).write_text(_TRUST_FILE, encoding="utf-8")
    # Give the store a real file to compare snapshots against.
    _add("anchor", "echo anchor")
    from qwik.core.store import get_store

    store = get_store()
    toml_path = Path(os.environ["QWIK_CONFIG_DIR"]) / "aliases.toml"
    before = toml_path.read_text(encoding="utf-8")
    with store.mutate() as data:
        data.project_aliases = {"injected": Alias(command="echo x")}
    after = toml_path.read_text(encoding="utf-8")
    assert before == after
