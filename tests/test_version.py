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
