"""Fixture and input preflight only; do not initialize PostgreSQL here."""

from gitlab_group_native_fixture import schema_sql
from gitlab_ssh_native_fixture import literal


def test_group_tiny_fixture_has_only_current_projection_tables_and_raw_csv_variants() -> (
    None
):
    sql = schema_sql()
    assert sql.count(b"CREATE TABLE") == 5
    assert all(
        (b"CREATE TABLE " + name) in sql
        for name in (
            b"users",
            b"namespaces",
            b"members",
            b"namespace_settings",
            b"projects",
        )
    )
    assert b"'GroupMember'" in sql and b"'ProjectMember'" in sql and b"'User'" in sql
    assert b"'Original, project'" in sql and b"Line\\nbreak" in sql
    assert b"DROP " not in sql and b"UPDATE " not in sql
    assert literal("a'b") == "'a''b'"
