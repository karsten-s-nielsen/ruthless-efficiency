from ruthless.config import GridConfig
from ruthless.strategies.grid_.plan import enumerate_points


def _cfg(**extra):
    base = {
        "kind": "grid",
        "metric": "loss",
        "design": "cartesian",
        "param_space": {
            "a": {"kind": "choice", "choices": ("x", "y")},
            "b": {"kind": "int", "lo": 1, "hi": 3},
        },
    }
    base.update(extra)
    return GridConfig.model_validate(base)


def test_cartesian_order_and_count():
    assert enumerate_points(_cfg()) == [
        {"a": "x", "b": 1},
        {"a": "x", "b": 2},
        {"a": "x", "b": 3},
        {"a": "y", "b": 1},
        {"a": "y", "b": 2},
        {"a": "y", "b": 3},
    ]


def test_one_at_a_time():
    pts = enumerate_points(_cfg(design="one_at_a_time", baseline={"a": "x", "b": 1}))
    assert pts == [
        {"a": "x", "b": 1},
        {"a": "y", "b": 1},
        {"a": "x", "b": 2},
        {"a": "x", "b": 3},
    ]


def test_points_as_given():
    pts = enumerate_points(_cfg(design="points", points=[{"a": "x", "b": 1}, {"a": "y", "b": 2}]))
    assert pts == [{"a": "x", "b": 1}, {"a": "y", "b": 2}]


def test_dedup_points():
    pts = enumerate_points(_cfg(design="points", points=[{"a": "x", "b": 1}, {"a": "x", "b": 1}]))
    assert pts == [{"a": "x", "b": 1}]


def test_oat_swap_dedup():
    # OAT over a Choice with a repeated non-baseline level exercises the OAT enumeration path: the two "y"
    # swaps collapse to one evaluated point (baseline "x" emitted once, then "y" once).
    cfg = GridConfig.model_validate(
        {
            "kind": "grid",
            "metric": "loss",
            "design": "one_at_a_time",
            "param_space": {"a": {"kind": "choice", "choices": ("x", "y", "y")}},
            "baseline": {"a": "x"},
        }
    )
    assert enumerate_points(cfg) == [{"a": "x"}, {"a": "y"}]


def test_ids_contiguous_after_dedup():
    pts = enumerate_points(_cfg(design="points", points=[{"a": "x", "b": 1}, {"a": "x", "b": 1}, {"a": "y", "b": 2}]))
    assert len(pts) == 2


def test_deterministic():
    assert enumerate_points(_cfg()) == enumerate_points(_cfg())
