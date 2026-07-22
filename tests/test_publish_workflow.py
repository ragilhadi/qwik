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
