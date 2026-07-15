from pathlib import Path


MIGRATION = (
    Path(__file__).parents[2]
    / "apps"
    / "backend"
    / "migrations"
    / "versions"
    / "0009_operational_consistency.py"
)


def test_operational_consistency_migration_aligns_ocr_coordinate_contract() -> None:
    source = MIGRATION.read_text(encoding="utf-8")

    assert 'down_revision = "0008_m8_support_privileges"' in source
    assert "idx_ocr_blocks_text_gin" in source
    assert "to_tsvector('simple', coalesce(normalized_text, ''))" in source
    assert "sa.Numeric(8, 7)" in source
    assert "sa.Numeric(6, 2)" in source
    for physical_name in ("x", "y", "width", "height"):
        assert f'"{physical_name}"' in source
