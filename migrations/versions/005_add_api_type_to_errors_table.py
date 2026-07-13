"""Modify ticker_api_errors table for composite unique on ticker and api_type

Revision ID: 005
Revises: 004
Create Date: 2026-07-06
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '005'
down_revision: Union[str, None] = '004'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    # Recreate the table with api_type and composite unique constraint
    op.drop_table('ticker_api_errors')
    op.create_table(
        'ticker_api_errors',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('ticker', sa.Text, nullable=False),
        sa.Column('api_type', sa.Text, nullable=False),
        sa.Column('error_count', sa.Integer, server_default='0'),
        sa.Column('last_error_time', sa.Text),
        sa.UniqueConstraint('ticker', 'api_type', name='uq_ticker_api_type')
    )

def downgrade() -> None:
    op.drop_table('ticker_api_errors')
    op.create_table(
        'ticker_api_errors',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('ticker', sa.Text, nullable=False, unique=True),
        sa.Column('error_count', sa.Integer, server_default='0'),
        sa.Column('last_error_time', sa.Text),
    )
