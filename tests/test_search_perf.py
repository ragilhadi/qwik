"""Performance benchmarks for fuzzy search.

Not run by default CI (no marker gate); run manually with:
    pytest tests/test_search_perf.py -v -s
"""

from __future__ import annotations

import time

import pytest

from qwik.core.models import Alias, AliasStore
from qwik.core.search import search_aliases


def _build_store(n: int) -> AliasStore:
    store = AliasStore()
    for i in range(n):
        store.add(f"alias_{i:05d}", Alias(command=f"echo command_{i}"))
    return store


@pytest.mark.benchmark
@pytest.mark.parametrize("count", [1000, 5000, 10000])
def test_search_perf_under_200ms(count: int) -> None:
    store = _build_store(count)
    query = "alias_00"
    times: list[float] = []
    for _ in range(10):
        start = time.perf_counter()
        search_aliases(store, query, limit=50)
        elapsed = (time.perf_counter() - start) * 1000
        times.append(elapsed)
    median = sorted(times)[len(times) // 2]
    print(f"\n  {count} aliases: {median:.1f}ms median (limit: 200ms)")
    assert median < 200, f"Search too slow: {median:.1f}ms for {count} aliases"


@pytest.mark.benchmark
def test_search_empty_query_fast() -> None:
    store = _build_store(1000)
    start = time.perf_counter()
    search_aliases(store, "", limit=50)
    elapsed = (time.perf_counter() - start) * 1000
    assert elapsed < 50, f"Empty query too slow: {elapsed:.1f}ms"
