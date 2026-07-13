"""Add updated_at column to daily_cash_report

Stores the UTC wall-clock time when the row was last written, so the
dashboard can display a meaningful "last updated" timestamp (converted
to SGT) rather than the trading date column which is often the
prior business day.

Revision ID: 002
Revises: 001
Create Date: 2026-07-03
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '002'
down_revision: Union[str, None] = '001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'daily_cash_report',
        sa.Column('updated_at', sa.Text, nullable=True)
    )


def downgrade() -> None:
    op.drop_column('daily_cash_report', 'updated_at')
