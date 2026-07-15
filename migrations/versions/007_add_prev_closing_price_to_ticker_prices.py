"""Add prev_closing_price to ticker_prices

Revision ID: 007
Revises: 006
Create Date: 2026-07-15
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '007'
down_revision: Union[str, None] = '006'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    op.add_column('ticker_prices', sa.Column('prev_closing_price', sa.Float))

def downgrade() -> None:
    with op.batch_alter_table('ticker_prices') as batch_op:
        batch_op.drop_column('prev_closing_price')
