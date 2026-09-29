"""Chunk keyword index: chunks.fts_rowid + SQLite FTS5 table chunks_fts.

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-28 16:22:09.596962
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '0002'
down_revision: str | None = '0001'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table('chunks', schema=None) as batch_op:
        batch_op.add_column(sa.Column('fts_rowid', sa.Integer(), nullable=False, server_default='0'))
    with op.batch_alter_table('chunks', schema=None) as batch_op:
        batch_op.alter_column('fts_rowid', server_default=None)
        batch_op.create_index('ix_chunks_fts_rowid', ['fts_rowid'], unique=True)

    if op.get_bind().dialect.name == 'sqlite':
        # Standalone FTS5 table (stores its own copy of the text); rowid = chunks.fts_rowid.
        # porter + unicode61 gives stemming ("terminate" matches "termination") and accent folding.
        op.execute(
            "CREATE VIRTUAL TABLE chunks_fts USING fts5("
            "text, kb_id UNINDEXED, tokenize = 'porter unicode61 remove_diacritics 2')"
        )


def downgrade() -> None:
    if op.get_bind().dialect.name == 'sqlite':
        op.execute("DROP TABLE IF EXISTS chunks_fts")
    with op.batch_alter_table('chunks', schema=None) as batch_op:
        batch_op.drop_index('ix_chunks_fts_rowid')
        batch_op.drop_column('fts_rowid')
