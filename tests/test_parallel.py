from ruthless.parallel import map_work_units


def _square(n: int) -> int:
    return n * n


def test_thread_map_preserves_order():
    assert map_work_units(_square, [1, 2, 3, 4], workers=2, executor="thread") == [1, 4, 9, 16]


def test_process_map_preserves_order():
    assert map_work_units(_square, [1, 2, 3], workers=2, executor="process") == [1, 4, 9]
