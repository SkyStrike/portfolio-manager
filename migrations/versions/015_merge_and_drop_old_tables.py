"""Merge daily_cash_report_old into daily_cash_report and drop legacy tables

Revision ID: 015
Revises: 014
Create Date: 2026-10-07
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '015'
down_revision: Union[str, None] = '014'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    conn = bind.connect() if hasattr(bind, 'connect') else bind

    # 1. Check if daily_cash_report_old exists, copy missing historical rows into daily_cash_report
    has_cash_old = conn.execute(
        sa.text("SELECT name FROM sqlite_master WHERE type='table' AND name='daily_cash_report_old'")
    ).fetchone()

    if has_cash_old:
        conn.execute(sa.text("""
            INSERT OR IGNORE INTO daily_cash_report (date, broker, liquidation_value, base_capital, total_stock_value, cash_on_hand)
            SELECT date, 'CONSOLIDATED', liquidation_value, base_capital, total_stock_value, cash_on_hand
            FROM daily_cash_report_old
            WHERE date NOT IN (SELECT DISTINCT date FROM daily_cash_report)
        """))
        op.drop_table('daily_cash_report_old')

    # 2. Check if daily_portfolio_metrics_old exists, drop it
    has_port_old = conn.execute(
        sa.text("SELECT name FROM sqlite_master WHERE type='table' AND name='daily_portfolio_metrics_old'")
    ).fetchone()

    if has_port_old:
        op.drop_table('daily_portfolio_metrics_old')


def downgrade() -> None:
    # Recreate legacy daily_cash_report_old structure if downgraded
    op.create_table(
        'daily_cash_report_old',
        sa.Column('date', sa.String(), primary_key=True),
        sa.Column('liquidation_value', sa.Float(), nullable=False),
        sa.Column('base_capital', sa.Float(), nullable=False),
        sa.Column('total_stock_value', sa.Float(), nullable=False),
        sa.Column('cash_on_hand', sa.Float(), nullable=False)
    )
    op.create_table(
        'daily_portfolio_metrics_old',
        sa.Column('date', sa.String(), nullable=False),
        sa.Column('classification', sa.String(), nullable=False),
        sa.Column('total_invested', sa.Float(), nullable=False),
        sa.Column('current_value', sa.Float(), nullable=False),
        sa.Column('options_profit', sa.Float()),
        sa.Column('total_returns', sa.Float(), nullable=False),
        sa.PrimaryKeyConstraint('date', 'classification')
    )
