"""add_scraper_sources_seen_urls_and_runs

Revision ID: f1a2b3c4d5e6
Revises: 0de3d34246e8
Create Date: 2026-11-16 21:45:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f1a2b3c4d5e6"
down_revision: str | Sequence[str] | None = "0de3d34246e8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema: create scraper_sources, scraper_seen_urls, and scraper_runs tables."""
    op.create_table(
        "scraper_sources",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("source_key", sa.String(length=100), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column(
            "catalog_urls",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
        sa.Column(
            "adapter_type",
            sa.String(length=30),
            server_default="html_list",
            nullable=False,
        ),
        sa.Column(
            "card_url_patterns",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
        sa.Column(
            "exclude_url_patterns",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
        sa.Column("b2b_filter_enabled", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("russia_online_only", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("use_jina_reader", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("encoding", sa.String(length=50), server_default="utf-8", nullable=False),
        sa.Column(
            "required_cookies",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column("max_urls_per_run", sa.Integer(), server_default="10", nullable=False),
        sa.Column("is_enabled", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("is_builtin", sa.Boolean(), server_default="false", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_key"),
    )

    op.create_table(
        "scraper_seen_urls",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("url", sa.String(length=1000), nullable=False),
        sa.Column("source_key", sa.String(length=100), nullable=False),
        sa.Column("outcome", sa.String(length=50), nullable=False),
        sa.Column("event_id", sa.Integer(), nullable=True),
        sa.Column("recheck_attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "last_checked_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["event_id"], ["events.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("url"),
    )
    op.create_index("ix_scraper_seen_urls_source_key", "scraper_seen_urls", ["source_key"])
    op.create_index("ix_scraper_seen_urls_outcome", "scraper_seen_urls", ["outcome"])

    op.create_table(
        "scraper_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("target_source_key", sa.String(length=100), nullable=False),
        sa.Column("triggered_by", sa.String(length=30), server_default="manual", nullable=False),
        sa.Column("sources_total", sa.Integer(), server_default="0", nullable=False),
        sa.Column("sources_done", sa.Integer(), server_default="0", nullable=False),
        sa.Column("urls_discovered", sa.Integer(), server_default="0", nullable=False),
        sa.Column("events_created", sa.Integer(), server_default="0", nullable=False),
        sa.Column("events_updated", sa.Integer(), server_default="0", nullable=False),
        sa.Column("rejected_b2c", sa.Integer(), server_default="0", nullable=False),
        sa.Column("rejected_geo", sa.Integer(), server_default="0", nullable=False),
        sa.Column("rejected_past", sa.Integer(), server_default="0", nullable=False),
        sa.Column("errors_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "source_logs",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_scraper_runs_status", "scraper_runs", ["status"])


def downgrade() -> None:
    """Downgrade schema: drop scraper_runs, scraper_seen_urls, and scraper_sources in reverse order."""
    op.drop_index("ix_scraper_runs_status", table_name="scraper_runs")
    op.drop_table("scraper_runs")

    op.drop_index("ix_scraper_seen_urls_outcome", table_name="scraper_seen_urls")
    op.drop_index("ix_scraper_seen_urls_source_key", table_name="scraper_seen_urls")
    op.drop_table("scraper_seen_urls")

    op.drop_table("scraper_sources")
