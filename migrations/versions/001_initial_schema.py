"""Initial schema baseline — represents the complete current database schema.

This migration captures the full schema as it exists in production.
Existing databases (without alembic_version) will be stamped at this revision
WITHOUT running any SQL. Only fresh databases will actually execute upgrade().

Revision ID: 001
Revises:
Create Date: 2026-07-03
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the full initial schema from scratch.
    
    NOTE: This only runs on a brand-new empty database.
    Existing production databases are stamped at this revision via
    core/migrations.py without executing any SQL here.
    """
    op.create_table(
        'portfolios',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('name', sa.Text, nullable=False, unique=True),
        sa.Column('sort_order', sa.Integer, server_default='0'),
        sa.Column('classification', sa.Text),
        sa.Column('broker', sa.Text),
    )

    op.create_table(
        'tickers',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('symbol', sa.Text, nullable=False, unique=True),
        sa.Column('friendly_name', sa.Text),
        sa.Column('tax_rate', sa.Float, server_default='0.0'),
        sa.Column('notes', sa.Text),
        sa.Column('exchange', sa.Text),
        sa.Column('underlying', sa.Text),
        sa.Column('category', sa.Text),
    )

    op.create_table(
        'exchange_rates',
        sa.Column('date', sa.Text, nullable=False),
        sa.Column('currency', sa.Text, nullable=False),
        sa.Column('rate', sa.Float, nullable=False),
        sa.Column('last_updated', sa.Text),
        sa.PrimaryKeyConstraint('date', 'currency'),
    )

    op.create_table(
        'transactions',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('portfolio_id', sa.Integer, nullable=False),
        sa.Column('ticker_id', sa.Integer, nullable=False),
        sa.Column('date', sa.Text, nullable=False),
        sa.Column('action', sa.Text, nullable=False),
        sa.Column('price', sa.Float, nullable=False),
        sa.Column('quantity', sa.Float, nullable=False),
        sa.Column('currency', sa.Text, nullable=False),
        sa.Column('commission', sa.Float, server_default='0.0'),
        sa.Column('cost_basis_after', sa.Float),
        sa.Column('realized_pl', sa.Float),
        sa.Column('realized_pl_sgd', sa.Float),
        sa.Column('notes', sa.Text),
        sa.ForeignKeyConstraint(['portfolio_id'], ['portfolios.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['ticker_id'], ['tickers.id'], ondelete='CASCADE'),
    )

    op.create_table(
        'dividends',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('portfolio_id', sa.Integer, nullable=False),
        sa.Column('ticker_id', sa.Integer, nullable=False),
        sa.Column('date', sa.Text, nullable=False),
        sa.Column('amount', sa.Float, nullable=False),
        sa.Column('currency', sa.Text, nullable=False),
        sa.Column('tax', sa.Float, nullable=False),
        sa.Column('notes', sa.Text),
        sa.ForeignKeyConstraint(['portfolio_id'], ['portfolios.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['ticker_id'], ['tickers.id'], ondelete='CASCADE'),
    )

    op.create_table(
        'ticker_prices',
        sa.Column('ticker_id', sa.Integer, primary_key=True),
        sa.Column('price', sa.Float, nullable=False),
        sa.Column('prev_close', sa.Float),
        sa.Column('closing_price', sa.Float),
        sa.Column('intraday_price', sa.Float),
        sa.Column('last_price_mode', sa.Text),
        sa.Column('currency', sa.Text, nullable=False),
        sa.Column('last_updated', sa.Text, nullable=False),
        sa.ForeignKeyConstraint(['ticker_id'], ['tickers.id'], ondelete='CASCADE'),
    )

    op.create_table(
        'upcoming_dividends',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('ticker_id', sa.Integer, nullable=False),
        sa.Column('ex_date', sa.Text, nullable=False),
        sa.Column('payment_date', sa.Text, nullable=False),
        sa.Column('amount', sa.Float, nullable=False),
        sa.Column('currency', sa.Text, nullable=False),
        sa.Column('status', sa.Text, nullable=False),
        sa.Column('last_updated', sa.Text, nullable=False),
        sa.ForeignKeyConstraint(['ticker_id'], ['tickers.id'], ondelete='CASCADE'),
        sa.UniqueConstraint('ticker_id', 'ex_date'),
    )

    op.create_table(
        'daily_portfolio_metrics',
        sa.Column('date', sa.Text, nullable=False),
        sa.Column('portfolio_id', sa.Integer, nullable=False),
        sa.Column('total_invested', sa.Float, nullable=False),
        sa.Column('current_value', sa.Float, nullable=False),
        sa.Column('total_returns', sa.Float, nullable=False),
        sa.PrimaryKeyConstraint('date', 'portfolio_id'),
        sa.ForeignKeyConstraint(['portfolio_id'], ['portfolios.id'], ondelete='CASCADE'),
    )

    op.create_table(
        'daily_options_metrics',
        sa.Column('date', sa.Text, primary_key=True),
        sa.Column('options_profit', sa.Float, nullable=False),
    )

    op.create_table(
        'daily_cash_report',
        sa.Column('date', sa.Text, nullable=False),
        sa.Column('broker', sa.Text, nullable=False),
        sa.Column('liquidation_value', sa.Float, nullable=False),
        sa.Column('base_capital', sa.Float, nullable=False),
        sa.Column('total_stock_value', sa.Float, nullable=False),
        sa.Column('cash_on_hand', sa.Float, nullable=False),
        sa.PrimaryKeyConstraint('date', 'broker'),
    )

    op.create_table(
        'broker_capital_entries',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('date', sa.Text, nullable=False),
        sa.Column('broker', sa.Text, nullable=False),
        sa.Column('amount', sa.Float, nullable=False),
        sa.Column('remarks', sa.Text),
        sa.UniqueConstraint('date', 'broker', 'amount', 'remarks'),
    )

    op.create_table(
        'settings',
        sa.Column('key', sa.Text, primary_key=True),
        sa.Column('value', sa.Text, nullable=False),
    )


def downgrade() -> None:
    """Drop all tables — reverts to an empty database."""
    op.drop_table('settings')
    op.drop_table('broker_capital_entries')
    op.drop_table('daily_cash_report')
    op.drop_table('daily_options_metrics')
    op.drop_table('daily_portfolio_metrics')
    op.drop_table('upcoming_dividends')
    op.drop_table('ticker_prices')
    op.drop_table('dividends')
    op.drop_table('transactions')
    op.drop_table('exchange_rates')
    op.drop_table('tickers')
    op.drop_table('portfolios')
