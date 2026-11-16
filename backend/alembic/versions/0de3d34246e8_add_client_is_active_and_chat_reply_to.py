"""add_client_is_active_and_chat_reply_to

Revision ID: 0de3d34246e8
Revises: d4e5f6a7b8c9
Create Date: 2026-11-16 14:32:43.218676

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0de3d34246e8"
down_revision: str | Sequence[str] | None = "d4e5f6a7b8c9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema: add clients.is_active and chat_messages.reply_to_message_id."""
    op.add_column(
        "clients",
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
    )
    op.add_column(
        "chat_messages",
        sa.Column("reply_to_message_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_chat_messages_reply_to_message_id",
        "chat_messages",
        "chat_messages",
        ["reply_to_message_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    """Downgrade schema: remove chat_messages.reply_to_message_id and clients.is_active."""
    op.drop_constraint(
        "fk_chat_messages_reply_to_message_id",
        "chat_messages",
        type_="foreignkey",
    )
    op.drop_column("chat_messages", "reply_to_message_id")
    op.drop_column("clients", "is_active")
