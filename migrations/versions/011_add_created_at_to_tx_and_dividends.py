"""Add created_at column to transactions and dividends tables

Revision ID: 011
Revises: 010
Create Date: 2026-07-25
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '011'
down_revision: Union[str, None] = '010'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'transactions',
        sa.Column('created_at', sa.Text, nullable=True)
    )
    op.execute("UPDATE transactions SET created_at = datetime('now') WHERE created_at IS NULL")
    
    op.add_column(
        'dividends',
        sa.Column('created_at', sa.Text, nullable=True)
    )
    op.execute("UPDATE dividends SET created_at = datetime('now') WHERE created_at IS NULL")


def downgrade() -> None:
    op.drop_column('transactions', 'created_at')
    op.drop_column('dividends', 'created_at')
