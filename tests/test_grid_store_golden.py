from ruthless.strategies.grid_.store import GRID_META_DDL, GRID_RESULT_DDL, SCHEMA_VERSION


def test_grid_store_schema_is_pinned():
    # ADR-003: the on-disk store is a compatibility surface. A schema change must be deliberate — bump
    # SCHEMA_VERSION and this test together, and note the store invalidation in the CHANGELOG.
    assert SCHEMA_VERSION == "1"
    assert GRID_META_DDL == "CREATE TABLE IF NOT EXISTS grid_meta (key TEXT PRIMARY KEY, value TEXT)"
    assert GRID_RESULT_DDL == "CREATE TABLE IF NOT EXISTS grid_result (fp TEXT PRIMARY KEY, metrics_json TEXT)"
