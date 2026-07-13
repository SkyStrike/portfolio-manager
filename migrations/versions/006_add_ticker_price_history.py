"""Add ticker_price_history table

Revision ID: 006
Revises: 005
Create Date: 2026-07-11
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '006'
down_revision: Union[str, None] = '005'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    op.create_table(
        'ticker_price_history',
        sa.Column('symbol',   sa.Text,  nullable=False),
        sa.Column('date',     sa.Text,  nullable=False),   # YYYY-MM-DD
        sa.Column('interval', sa.Text,  nullable=False),   # '1d' or '1wk'
        sa.Column('open',     sa.Float),
        sa.Column('high',     sa.Float),
        sa.Column('low',      sa.Float),
        sa.Column('close',    sa.Float, nullable=False),
        sa.PrimaryKeyConstraint('symbol', 'date', 'interval'),
    )

def downgrade() -> None:
    op.drop_table('ticker_price_history')
