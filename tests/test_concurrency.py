"""Regression test for concurrent store writes (issue: lost updates).

Every mutating command used to perform an unlocked read-modify-write of
the whole store: two overlapping writers would each read the same
snapshot, mutate their own copy, and the last ``save`` would win, silently
discarding the loser's change even though it had already printed success.
``Store.mutate()`` closes that gap by acquiring the store's file lock
around a fresh load + save, so this test spawns real, concurrent ``qwik
add`` subprocesses and asserts every one of them survives.
"""

from __future__ import annotations

import os
import subprocess
import sys

import pytest


def _qwik_env(config_dir: str) -> dict[str, str]:
    env = dict(os.environ)
    env["QWIK_CONFIG_DIR"] = config_dir
    env.setdefault("PYTHONUTF8", "1")
    env.setdefault("PYTHONIOENCODING", "utf-8")
    return env


@pytest.mark.integration
def test_concurrent_add_does_not_lose_aliases(tmp_path) -> None:
    config_dir = str(tmp_path)
    env = _qwik_env(config_dir)

    seed = subprocess.run(
        [sys.executable, "-m", "qwik", "add", "seed", "echo", "seed"],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert seed.returncode == 0, seed.stderr

    n = 20
    procs = [
        subprocess.Popen(
            [sys.executable, "-m", "qwik", "add", f"race{i}", "echo", str(i)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=env,
        )
        for i in range(n)
    ]
    returncodes = [p.wait() for p in procs]
    assert all(rc == 0 for rc in returncodes), returncodes

    import tomlkit

    store_path = tmp_path / "aliases.toml"
    doc = tomlkit.parse(store_path.read_text(encoding="utf-8"))
    names = set(doc["aliases"].keys())  # type: ignore[union-attr]
    expected = {"seed"} | {f"race{i}" for i in range(n)}
    assert names == expected, f"missing: {expected - names}"
