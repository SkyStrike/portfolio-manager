"""Add is_manual column to ticker_prices table

Revision ID: 012
Revises: 011
Create Date: 2026-07-28
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '012'
down_revision: Union[str, None] = '011'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'ticker_prices',
        sa.Column('is_manual', sa.Integer, server_default='0')
    )


def downgrade() -> None:
    op.drop_column('ticker_prices', 'is_manual')
