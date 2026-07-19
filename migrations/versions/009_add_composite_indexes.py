"""Add composite indexes for transaction and dividend queries

Revision ID: 009
Revises: 008
Create Date: 2026-07-19
"""
from typing import Sequence, Union
from alembic import op

revision: str = '009'
down_revision: Union[str, None] = '008'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index('idx_tx_port_date', 'transactions', ['portfolio_id', 'date'], if_not_exists=True)
    op.create_index('idx_tx_ticker', 'transactions', ['ticker_id'], if_not_exists=True)
    op.create_index('idx_div_ticker_date', 'dividends', ['ticker_id', 'date'], if_not_exists=True)
    op.create_index('idx_div_port', 'dividends', ['portfolio_id'], if_not_exists=True)


def downgrade() -> None:
    op.drop_index('idx_tx_port_date', table_name='transactions', if_exists=True)
    op.drop_index('idx_tx_ticker', table_name='transactions', if_exists=True)
    op.drop_index('idx_div_ticker_date', table_name='dividends', if_exists=True)
    op.drop_index('idx_div_port', table_name='dividends', if_exists=True)
