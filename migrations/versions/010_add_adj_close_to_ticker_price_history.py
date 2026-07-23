"""Add adj_close column to ticker_price_history

Revision ID: 010
Revises: 009
Create Date: 2026-07-23
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '010'
down_revision: Union[str, None] = '009'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'ticker_price_history',
        sa.Column('adj_close', sa.Float, nullable=True)
    )
    # Clear legacy cached price history so fresh fetch downloads both unadjusted and adjusted prices
    op.execute("DELETE FROM ticker_price_history")


def downgrade() -> None:
    op.drop_column('ticker_price_history', 'adj_close')
