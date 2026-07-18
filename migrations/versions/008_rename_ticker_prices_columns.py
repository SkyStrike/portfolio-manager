"""Rename ticker_prices price columns for clarity and add date tracking columns

Revision ID: 008
Revises: 007
Create Date: 2026-07-18

Renames:
    intraday_price      -> intraday_current
    prev_close          -> intraday_prev_close
    closing_price       -> daily_close
    prev_closing_price  -> daily_prev_close

Adds:
    intraday_current_at       TEXT  -- datetime of last live price fetch
    intraday_prev_close_date  TEXT  -- YYYY-MM-DD of the intraday reference close
    daily_close_date          TEXT  -- YYYY-MM-DD of the daily_close price
    daily_prev_close_date     TEXT  -- YYYY-MM-DD of the daily_prev_close price

Note: `price` column is intentionally preserved as a legacy alias for backward
compatibility with seed inserts in importer.py / transactions.py. It mirrors
intraday_current and is updated on every upsert.
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '008'
down_revision: Union[str, None] = '007'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('ticker_prices') as batch_op:
        # Renames
        batch_op.alter_column('intraday_price',     new_column_name='intraday_current')
        batch_op.alter_column('prev_close',         new_column_name='intraday_prev_close')
        batch_op.alter_column('closing_price',      new_column_name='daily_close')
        batch_op.alter_column('prev_closing_price', new_column_name='daily_prev_close')
        # New date/timestamp tracking columns
        batch_op.add_column(sa.Column('intraday_current_at',      sa.Text, nullable=True))
        batch_op.add_column(sa.Column('intraday_prev_close_date', sa.Text, nullable=True))
        batch_op.add_column(sa.Column('daily_close_date',         sa.Text, nullable=True))
        batch_op.add_column(sa.Column('daily_prev_close_date',    sa.Text, nullable=True))
        
        batch_op.drop_column('last_price_mode') # no longer used


def downgrade() -> None:
    with op.batch_alter_table('ticker_prices') as batch_op:
        # Drop added columns
        batch_op.drop_column('daily_prev_close_date')
        batch_op.drop_column('daily_close_date')
        batch_op.drop_column('intraday_prev_close_date')
        batch_op.drop_column('intraday_current_at')
        # Reverse renames
        batch_op.alter_column('intraday_current',   new_column_name='intraday_price')
        batch_op.alter_column('intraday_prev_close', new_column_name='prev_close')
        batch_op.alter_column('daily_close',        new_column_name='closing_price')
        batch_op.alter_column('daily_prev_close',   new_column_name='prev_closing_price')
