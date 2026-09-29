"""context budget per answer; more passages by default

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-29 22:30:00
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = '0005'
down_revision: str | None = '0004'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table('settings', schema=None) as batch_op:
        batch_op.add_column(sa.Column('context_tokens', sa.Integer(), server_default='8000', nullable=False))
    # The old default (5 passages) was too few for longer answers; workspaces still on it move to the new one.
    op.execute("UPDATE settings SET top_k = 8 WHERE top_k = 5")


def downgrade() -> None:
    with op.batch_alter_table('settings', schema=None) as batch_op:
        batch_op.drop_column('context_tokens')
