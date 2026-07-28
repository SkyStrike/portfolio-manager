"""Refactor is_manual to ticker_price_history and drop from ticker_prices

Revision ID: 013
Revises: 012
Create Date: 2026-07-28
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '013'
down_revision: Union[str, None] = '012'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add is_manual column to ticker_price_history
    op.add_column(
        'ticker_price_history',
        sa.Column('is_manual', sa.Integer, server_default='0')
    )
    
    # 2. Drop is_manual from ticker_prices using batch mode (SQLite limitation)
    with op.batch_alter_table('ticker_prices') as batch_op:
        batch_op.drop_column('is_manual')


def downgrade() -> None:
    with op.batch_alter_table('ticker_prices') as batch_op:
        batch_op.add_column(sa.Column('is_manual', sa.Integer, server_default='0'))
        
    op.drop_column('ticker_price_history', 'is_manual')
