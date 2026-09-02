"""Add tags and ticker_tags tables and seed from ticker notes

Revision ID: 014
Revises: 013
Create Date: 2026-09-02
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '014'
down_revision: Union[str, None] = '013'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create tags table
    op.create_table(
        'tags',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('name', sa.String(length=100), nullable=False, unique=True),
        sa.Column('color', sa.String(length=30), server_default='#3b82f6'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'))
    )
    
    # 2. Create ticker_tags join table
    op.create_table(
        'ticker_tags',
        sa.Column('ticker_id', sa.Integer(), sa.ForeignKey('tickers.id', ondelete='CASCADE'), primary_key=True, nullable=False),
        sa.Column('tag_id', sa.Integer(), sa.ForeignKey('tags.id', ondelete='CASCADE'), primary_key=True, nullable=False)
    )
    
    # 3. Migrate existing notes in tickers table into tags and ticker_tags
    bind = op.get_bind()
    conn = bind.connect() if hasattr(bind, 'connect') else bind
    
    results = conn.execute(sa.text("SELECT id, notes FROM tickers WHERE notes IS NOT NULL AND notes != ''")).fetchall()
    tag_id_map = {}
    
    for row in results:
        ticker_id = row[0]
        notes_str = row[1] or ""
        # Split comma-separated tokens, normalize lowercase and strip whitespace
        raw_tags = [t.strip().lower() for t in notes_str.split(",") if t.strip()]
        for t_name in raw_tags:
            if t_name not in tag_id_map:
                existing = conn.execute(sa.text("SELECT id FROM tags WHERE name = :name"), {"name": t_name}).fetchone()
                if existing:
                    tag_id_map[t_name] = existing[0]
                else:
                    conn.execute(sa.text("INSERT INTO tags (name) VALUES (:name)"), {"name": t_name})
                    new_tag = conn.execute(sa.text("SELECT id FROM tags WHERE name = :name"), {"name": t_name}).fetchone()
                    tag_id_map[t_name] = new_tag[0]
            
            tag_id = tag_id_map[t_name]
            conn.execute(
                sa.text("INSERT OR IGNORE INTO ticker_tags (ticker_id, tag_id) VALUES (:ticker_id, :tag_id)"),
                {"ticker_id": ticker_id, "tag_id": tag_id}
            )


def downgrade() -> None:
    op.drop_table('ticker_tags')
    op.drop_table('tags')
