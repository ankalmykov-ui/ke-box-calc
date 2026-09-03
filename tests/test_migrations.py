from ke_box_calc.db.migrator import load_migrations


def test_initial_migration_is_reversible_and_scoped() -> None:
    migrations = load_migrations()
    assert [migration.version for migration in migrations] == [
        "0001_identity_scope",
        "0002_materials_warehouse",
        "0003_calculation_references",
        "0004_price_quality",
    ]
    migration = migrations[0]
    for table in (
        "organizations",
        "sites",
        "warehouses",
        "users",
        "roles",
        "user_role_scopes",
        "audit_log",
    ):
        assert f"CREATE TABLE {table}" in migration.up_sql
        assert f"DROP TABLE IF EXISTS {table}" in migration.down_sql
    assert "INSERT INTO roles" in migration.up_sql
    assert migration.checksum
    warehouse = migrations[1]
    assert "CREATE TABLE materials" in warehouse.up_sql
    assert "CREATE TABLE stock_movements" in warehouse.up_sql
    assert "DROP TABLE IF EXISTS materials" in warehouse.down_sql
    references = migrations[2]
    assert "CREATE TABLE calculation_reference_versions" in references.up_sql
    assert "DROP TABLE IF EXISTS calculation_reference_versions" in references.down_sql
    assert "ADD COLUMN quality_status" in migrations[3].up_sql
