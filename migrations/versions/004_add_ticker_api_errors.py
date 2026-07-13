"""Add ticker_api_errors table

Revision ID: 004
Revises: 003
Create Date: 2026-07-06
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '004'
down_revision: Union[str, None] = '003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    op.create_table(
        'ticker_api_errors',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('ticker', sa.Text, nullable=False, unique=True),
        sa.Column('error_count', sa.Integer, server_default='0'),
        sa.Column('last_error_time', sa.Text),
    )

def downgrade() -> None:
    op.drop_table('ticker_api_errors')
