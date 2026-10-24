"""add_data_status_and_missing_data_warnings

Revision ID: c3d9a1f2e8b0
Revises: b99a2debd96d
Create Date: 2026-10-22 15:11:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'c3d9a1f2e8b0'
down_revision: Union[str, Sequence[str], None] = 'b99a2debd96d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema: add data_status and missing_data_warnings columns to events, fix telegram_chat_id to BigInteger."""
    op.add_column(
        'events',
        sa.Column('data_status', sa.String(length=50), server_default='ready', nullable=False)
    )
    op.add_column(
        'events',
        sa.Column('missing_data_warnings', postgresql.ARRAY(sa.String()), server_default='{}', nullable=False)
    )
    op.alter_column(
        'users',
        'telegram_chat_id',
        existing_type=sa.Numeric(),
        type_=sa.BigInteger(),
        existing_nullable=True,
        postgresql_using='telegram_chat_id::bigint'
    )


def downgrade() -> None:
    """Downgrade schema: drop data_status and missing_data_warnings columns from events, revert telegram_chat_id."""
    op.alter_column(
        'users',
        'telegram_chat_id',
        existing_type=sa.BigInteger(),
        type_=sa.Numeric(),
        existing_nullable=True
    )
    op.drop_column('events', 'missing_data_warnings')
    op.drop_column('events', 'data_status')

