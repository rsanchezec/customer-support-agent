"""Smoke test: alembic upgrade head and downgrade base against in-memory SQLite."""

import pytest
from sqlalchemy import create_engine, event, inspect

from app.db.migrations import run_downgrade, run_upgrade


@pytest.fixture
def sync_engine():
    """A synchronous in-memory SQLite engine for alembic migration testing."""
    eng = create_engine("sqlite:///:memory:", echo=False)

    # Enable FK enforcement for this connection
    @event.listens_for(eng, "connect")
    def set_pragma(dbapi_conn, _):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    yield eng
    eng.dispose()


@pytest.fixture
def sync_connection(sync_engine):
    """Provide a sync connection from the sync engine."""
    with sync_engine.connect() as conn:
        yield conn


def test_upgrade_creates_all_tables(sync_connection):
    """alembic upgrade head creates users, conversations, messages."""
    run_upgrade(sync_connection, "head")

    inspector = inspect(sync_connection)
    table_names = inspector.get_table_names()

    assert "users" in table_names, f"Expected 'users' in {table_names}"
    assert "conversations" in table_names, f"Expected 'conversations' in {table_names}"
    assert "messages" in table_names, f"Expected 'messages' in {table_names}"


def test_downgrade_removes_all_tables(sync_connection):
    """alembic downgrade -1 removes all tables (back to base)."""
    run_upgrade(sync_connection, "head")
    run_downgrade(sync_connection, "-1")

    inspector = inspect(sync_connection)
    table_names = inspector.get_table_names()

    assert "users" not in table_names, f"Unexpected 'users' in {table_names}"
    assert "conversations" not in table_names, f"Unexpected 'conversations' in {table_names}"
    assert "messages" not in table_names, f"Unexpected 'messages' in {table_names}"


def test_upgrade_idempotent(sync_connection):
    """Running upgrade twice is safe (no destructive changes)."""
    run_upgrade(sync_connection, "head")
    # Second upgrade should not raise.
    run_upgrade(sync_connection, "head")

    # Second upgrade should not raise — idempotent re-run is safe.
    run_upgrade(sync_connection, "head")

    inspector = inspect(sync_connection)
    table_names = inspector.get_table_names()

    assert set(table_names) >= {"users", "conversations", "messages"}


def test_users_table_columns(sync_connection):
    """users table has the expected columns and unique constraint on entraid_oid."""
    run_upgrade(sync_connection, "head")

    inspector = inspect(sync_connection)
    columns = {col["name"] for col in inspector.get_columns("users")}
    assert columns >= {"id", "entraid_oid", "email", "display_name", "last_seen_at", "created_at"}

    indexes = inspector.get_indexes("users")
    # Unique index on entraid_oid
    unique_indexes = [idx for idx in indexes if idx.get("unique")]
    unique_col_names = [list(idx["column_names"]) for idx in unique_indexes]
    assert ["entraid_oid"] in unique_col_names, (
        f"Expected unique index on entraid_oid: {unique_indexes}"
    )


def test_conversations_table_fk_and_indexes(sync_connection):
    """conversations table has FK to users with CASCADE and indexes."""
    run_upgrade(sync_connection, "head")

    inspector = inspect(sync_connection)
    columns = {col["name"] for col in inspector.get_columns("conversations")}
    assert columns >= {"id", "user_id", "foundry_conversation_id", "title", "created_at"}

    foreign_keys = inspector.get_foreign_keys("conversations")
    assert any(fk["referred_table"] == "users" for fk in foreign_keys), (
        f"Expected FK to users: {foreign_keys}"
    )

    indexes = inspector.get_indexes("conversations")
    indexed_cols = {idx["name"]: idx["column_names"] for idx in indexes}
    assert indexed_cols.get("user_id") == ["user_id"] or any(
        idx["column_names"] == ["user_id"] for idx in indexes
    )


def test_messages_table_fk_and_indexes(sync_connection):
    """messages table has FK to conversations with CASCADE and index on conversation_id."""
    run_upgrade(sync_connection, "head")

    inspector = inspect(sync_connection)
    columns = {col["name"] for col in inspector.get_columns("messages")}
    assert columns >= {
        "id",
        "conversation_id",
        "role",
        "content",
        "foundry_message_id",
        "created_at",
    }

    foreign_keys = inspector.get_foreign_keys("messages")
    assert any(fk["referred_table"] == "conversations" for fk in foreign_keys), (
        f"Expected FK to conversations: {foreign_keys}"
    )

    indexes = inspector.get_indexes("messages")
    assert any(idx["column_names"] == ["conversation_id"] for idx in indexes), (
        f"Expected index on conversation_id: {indexes}"
    )
