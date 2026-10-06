"""create initial urls table

Revision ID: 001_initial_urls_table
Revises: 
Create Date: 2026-10-05 20:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "001_initial_urls_table"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "urls",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("short_code", sa.String(length=30), nullable=False),
        sa.Column("long_url", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("custom_alias", sa.String(length=30), nullable=True),
        sa.Column("created_by", sa.String(length=255), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_urls")),
        sa.UniqueConstraint("custom_alias", name=op.f("uq_urls_custom_alias")),
        sa.UniqueConstraint("short_code", name=op.f("uq_urls_short_code")),
    )
    op.create_index(op.f("ix_urls_short_code"), "urls", ["short_code"], unique=True)
    op.create_index(op.f("ix_urls_expires_at"), "urls", ["expires_at"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_urls_expires_at"), table_name="urls")
    op.drop_index(op.f("ix_urls_short_code"), table_name="urls")
    op.drop_table("urls")
