"""add_content_hash_to_scraper_seen_urls

Revision ID: a2b3c4d5e6f7
Revises: f1a2b3c4d5e6
Create Date: 2026-11-17 11:10:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a2b3c4d5e6f7"
down_revision: str | Sequence[str] | None = "f1a2b3c4d5e6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema: add nullable content_hash column to scraper_seen_urls."""
    op.add_column(
        "scraper_seen_urls",
        sa.Column("content_hash", sa.String(length=64), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema: remove content_hash column from scraper_seen_urls."""
    op.drop_column("scraper_seen_urls", "content_hash")
