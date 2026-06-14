"""0001_init — create users, conversations, messages tables.

Mirrors the SQLAlchemy declarative models in app/domain/*.py.
Uses sa.text("CURRENT_TIMESTAMP") for created_at defaults because
func.now() in server_default is not portable to SQLite (aiosqlite).
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers
revision: str = "0001"
down_revision: str | None = None
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    # --- users -----------------------------------------------------------
    op.create_table(
        "users",
        sa.Column("id", sa.CHAR(36), primary_key=True, nullable=False),
        # entraid_oid: unique, not null, indexed
        sa.Column("entraid_oid", sa.String(255), unique=True, nullable=False, index=True),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("display_name", sa.String(255), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        # created_at: separate DateTime column with SQLite-compatible server default
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
    )

    # --- conversations ----------------------------------------------------
    op.create_table(
        "conversations",
        sa.Column("id", sa.CHAR(36), primary_key=True, nullable=False),
        # FK to users.id with CASCADE delete
        sa.Column(
            "user_id",
            sa.CHAR(36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        # foundry_conversation_id: unique per user, indexed
        sa.Column(
            "foundry_conversation_id", sa.String(255), unique=True, nullable=True, index=True
        ),
        sa.Column("title", sa.String(255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
    )

    # --- messages --------------------------------------------------------
    op.create_table(
        "messages",
        sa.Column("id", sa.CHAR(36), primary_key=True, nullable=False),
        # FK to conversations.id with CASCADE delete
        sa.Column(
            "conversation_id",
            sa.CHAR(36),
            sa.ForeignKey("conversations.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("foundry_message_id", sa.String(255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    # Drop in reverse order of creation (FK dependency order)
    op.drop_table("messages")
    op.drop_table("conversations")
    op.drop_table("users")
