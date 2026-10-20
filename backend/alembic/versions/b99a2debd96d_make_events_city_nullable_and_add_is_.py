"""make_events_city_nullable_and_add_is_online

Revision ID: b99a2debd96d
Revises: ef2ffba968fe
Create Date: 2026-10-20 15:27:07.451347

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b99a2debd96d'
down_revision: Union[str, Sequence[str], None] = 'ef2ffba968fe'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('events', sa.Column('is_online', sa.Boolean(), server_default='false', nullable=False))
    op.alter_column('events', 'city',
               existing_type=sa.VARCHAR(length=100),
               nullable=True)
    op.create_check_constraint(
        'chk_events_city_or_online',
        'events',
        'city IS NOT NULL OR is_online = TRUE'
    )
    op.create_index(
        'idx_events_online',
        'events',
        ['is_online'],
        unique=False,
        postgresql_where=sa.text('is_active = TRUE AND is_online = TRUE')
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        'idx_events_online',
        table_name='events',
        postgresql_where=sa.text('is_active = TRUE AND is_online = TRUE')
    )
    op.drop_constraint('chk_events_city_or_online', 'events', type_='check')
    op.alter_column('events', 'city',
               existing_type=sa.VARCHAR(length=100),
               nullable=False)
    op.drop_column('events', 'is_online')
