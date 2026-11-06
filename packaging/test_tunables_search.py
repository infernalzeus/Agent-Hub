"""The inventory of numbers a search would tune stays in step with the code, and the baselines work. CMA-ES itself is deliberately not built."""
import pytest

from hub.yard import search as S, tunables as T


def test_every_listed_number_exists_in_the_javascript_and_sits_inside_its_range():
    now = T.current()
    for row in T.inventory():
        assert row["now"] is not None, ("not found in " + row["where"], row["name"])
        assert row["low"] <= row["now"] <= row["high"], (row["name"], row["now"], row["low"], row["high"])
    assert len(T.inventory()) >= 10 and not any(r["searched"] for r in T.inventory())      # nothing is tuned yet


def test_random_and_grid_search_find_the_peak_of_a_simple_score():
    space = {"a": (0.0, 1.0), "b": (0.0, 10.0)}
    peak = lambda c: -((c["a"] - 0.3) ** 2) - ((c["b"] - 7.0) / 10) ** 2     # noqa: E731
    r = S.random_search(peak, space, tries=400, seed=1)
    g = S.grid_search(peak, space, points=6)
    assert r["score"] > -0.02 and g["score"] > -0.05 and r["tries"] == 400 and g["tries"] == 36
    assert S.random_search(peak, space, tries=50, seed=7) == S.random_search(peak, space, tries=50, seed=7)      # repeatable
