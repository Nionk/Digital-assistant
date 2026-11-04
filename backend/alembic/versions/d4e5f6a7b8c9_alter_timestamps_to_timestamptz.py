"""alter_timestamps_to_timestamptz

Revision ID: d4e5f6a7b8c9
Revises: c3d9a1f2e8b0
Create Date: 2026-11-04 17:30:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'd4e5f6a7b8c9'
down_revision: str | Sequence[str] | None = 'c3d9a1f2e8b0'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema: alter all datetime columns to TIMESTAMPTZ."""
    tables_columns = [
        ('users', 'created_at'),
        ('clients', 'created_at'),
        ('clients', 'updated_at'),
        ('events', 'last_scraped_at'),
        ('selections', 'created_at'),
        ('selection_items', 'updated_at'),
        ('chat_messages', 'created_at'),
        ('llm_cache', 'created_at'),
    ]

    for table, col in tables_columns:
        op.alter_column(
            table,
            col,
            type_=sa.DateTime(timezone=True),
            existing_type=sa.DateTime(timezone=False),
            existing_nullable=False,
            postgresql_using=f"{col} AT TIME ZONE 'UTC'"
        )


def downgrade() -> None:
    """Downgrade schema: revert TIMESTAMPTZ columns back to TIMESTAMP WITHOUT TIME ZONE."""
    tables_columns = [
        ('users', 'created_at'),
        ('clients', 'created_at'),
        ('clients', 'updated_at'),
        ('events', 'last_scraped_at'),
        ('selections', 'created_at'),
        ('selection_items', 'updated_at'),
        ('chat_messages', 'created_at'),
        ('llm_cache', 'created_at'),
    ]

    for table, col in tables_columns:
        op.alter_column(
            table,
            col,
            type_=sa.DateTime(timezone=False),
            existing_type=sa.DateTime(timezone=True),
            existing_nullable=False,
        )

