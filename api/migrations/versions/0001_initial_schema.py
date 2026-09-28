"""Initial schema.

Revision ID: 0001
Revises: 
Create Date: 2026-09-28 15:51:05.580085
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = '0001'
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('jobs',
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('type', sa.String(length=32), nullable=False),
    sa.Column('payload_json', sa.Text(), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('attempts', sa.Integer(), nullable=False),
    sa.Column('error', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('started_at', sa.DateTime(), nullable=True),
    sa.Column('finished_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('jobs', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_jobs_status'), ['status'], unique=False)
        batch_op.create_index(batch_op.f('ix_jobs_type'), ['type'], unique=False)

    op.create_table('workspaces',
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('provider_connections',
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('workspace_id', sa.String(length=32), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('api_base', sa.String(length=512), nullable=False),
    sa.Column('api_key_enc', sa.Text(), nullable=False),
    sa.Column('kind', sa.String(length=16), nullable=False),
    sa.Column('models_json', sa.Text(), nullable=False),
    sa.Column('selected_model', sa.String(length=200), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('provider_connections', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_provider_connections_workspace_id'), ['workspace_id'], unique=False)

    op.create_table('settings',
    sa.Column('workspace_id', sa.String(length=32), nullable=False),
    sa.Column('chunk_size', sa.Integer(), nullable=False),
    sa.Column('chunk_overlap', sa.Integer(), nullable=False),
    sa.Column('top_k', sa.Integer(), nullable=False),
    sa.Column('hybrid', sa.Boolean(), nullable=False),
    sa.Column('rerank', sa.Boolean(), nullable=False),
    sa.Column('keep_local', sa.Boolean(), nullable=False),
    sa.Column('ocr', sa.Boolean(), nullable=False),
    sa.Column('embedding_provider', sa.String(length=32), nullable=False),
    sa.Column('embedding_model', sa.String(length=200), nullable=False),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('workspace_id')
    )
    op.create_table('knowledge_bases',
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('workspace_id', sa.String(length=32), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('description', sa.Text(), nullable=False),
    sa.Column('runtime', sa.String(length=8), nullable=False),
    sa.Column('default_connection_id', sa.String(length=32), nullable=True),
    sa.Column('default_model', sa.String(length=200), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['default_connection_id'], ['provider_connections.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('knowledge_bases', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_knowledge_bases_workspace_id'), ['workspace_id'], unique=False)

    op.create_table('users',
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('workspace_id', sa.String(length=32), nullable=False),
    sa.Column('email', sa.String(length=320), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('password_hash', sa.String(length=255), nullable=False),
    sa.Column('role', sa.String(length=16), nullable=False),
    sa.Column('theme', sa.String(length=8), nullable=False),
    sa.Column('default_kb_id', sa.String(length=32), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['default_kb_id'], ['knowledge_bases.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('email')
    )
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_users_workspace_id'), ['workspace_id'], unique=False)

    op.create_table('events',
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('workspace_id', sa.String(length=32), nullable=False),
    sa.Column('user_id', sa.String(length=32), nullable=True),
    sa.Column('category', sa.String(length=16), nullable=False),
    sa.Column('title', sa.String(length=300), nullable=False),
    sa.Column('detail', sa.Text(), nullable=False),
    sa.Column('tone', sa.String(length=8), nullable=True),
    sa.Column('tag', sa.String(length=40), nullable=True),
    sa.Column('ref_type', sa.String(length=16), nullable=True),
    sa.Column('ref_id', sa.String(length=32), nullable=True),
    sa.Column('ip', sa.String(length=64), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('events', schema=None) as batch_op:
        batch_op.create_index('ix_events_ws_created', ['workspace_id', 'created_at'], unique=False)

    op.create_table('sessions',
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('user_id', sa.String(length=32), nullable=False),
    sa.Column('token_hash', sa.String(length=64), nullable=False),
    sa.Column('user_agent', sa.String(length=512), nullable=False),
    sa.Column('ip', sa.String(length=64), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('last_seen_at', sa.DateTime(), nullable=False),
    sa.Column('revoked_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('token_hash')
    )
    with op.batch_alter_table('sessions', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_sessions_user_id'), ['user_id'], unique=False)

    op.create_table('chats',
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('workspace_id', sa.String(length=32), nullable=False),
    sa.Column('user_id', sa.String(length=32), nullable=False),
    sa.Column('kb_id', sa.String(length=32), nullable=True),
    sa.Column('title', sa.String(length=300), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['kb_id'], ['knowledge_bases.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('chats', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_chats_user_id'), ['user_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_chats_workspace_id'), ['workspace_id'], unique=False)

    op.create_table('documents',
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('kb_id', sa.String(length=32), nullable=False),
    sa.Column('filename', sa.String(length=512), nullable=False),
    sa.Column('mime', sa.String(length=128), nullable=False),
    sa.Column('size_bytes', sa.BigInteger(), nullable=False),
    sa.Column('sha256', sa.String(length=64), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('progress', sa.Integer(), nullable=False),
    sa.Column('error', sa.Text(), nullable=True),
    sa.Column('chunk_count', sa.Integer(), nullable=False),
    sa.Column('suggestions_json', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['kb_id'], ['knowledge_bases.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('documents', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_documents_kb_id'), ['kb_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_documents_sha256'), ['sha256'], unique=False)

    op.create_table('chunks',
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('document_id', sa.String(length=32), nullable=False),
    sa.Column('kb_id', sa.String(length=32), nullable=False),
    sa.Column('ordinal', sa.Integer(), nullable=False),
    sa.Column('text', sa.Text(), nullable=False),
    sa.Column('page', sa.Integer(), nullable=True),
    sa.Column('section', sa.String(length=512), nullable=True),
    sa.Column('token_count', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['document_id'], ['documents.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['kb_id'], ['knowledge_bases.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('chunks', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_chunks_document_id'), ['document_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_chunks_kb_id'), ['kb_id'], unique=False)

    op.create_table('messages',
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('chat_id', sa.String(length=32), nullable=False),
    sa.Column('role', sa.String(length=16), nullable=False),
    sa.Column('content', sa.Text(), nullable=False),
    sa.Column('model', sa.String(length=200), nullable=True),
    sa.Column('connection_id', sa.String(length=32), nullable=True),
    sa.Column('confidence', sa.String(length=8), nullable=True),
    sa.Column('citations_json', sa.Text(), nullable=False),
    sa.Column('followups_json', sa.Text(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['chat_id'], ['chats.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['connection_id'], ['provider_connections.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('messages', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_messages_chat_id'), ['chat_id'], unique=False)

    op.create_table('shares',
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('token', sa.String(length=64), nullable=False),
    sa.Column('message_id', sa.String(length=32), nullable=True),
    sa.Column('include_sources', sa.Boolean(), nullable=False),
    sa.Column('snapshot_json', sa.Text(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('revoked_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['message_id'], ['messages.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('token')
    )


def downgrade() -> None:
    op.drop_table('shares')
    with op.batch_alter_table('messages', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_messages_chat_id'))

    op.drop_table('messages')
    with op.batch_alter_table('chunks', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_chunks_kb_id'))
        batch_op.drop_index(batch_op.f('ix_chunks_document_id'))

    op.drop_table('chunks')
    with op.batch_alter_table('documents', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_documents_sha256'))
        batch_op.drop_index(batch_op.f('ix_documents_kb_id'))

    op.drop_table('documents')
    with op.batch_alter_table('chats', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_chats_workspace_id'))
        batch_op.drop_index(batch_op.f('ix_chats_user_id'))

    op.drop_table('chats')
    with op.batch_alter_table('sessions', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_sessions_user_id'))

    op.drop_table('sessions')
    with op.batch_alter_table('knowledge_bases', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_knowledge_bases_workspace_id'))

    op.drop_table('knowledge_bases')
    with op.batch_alter_table('events', schema=None) as batch_op:
        batch_op.drop_index('ix_events_ws_created')

    op.drop_table('events')
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_users_workspace_id'))

    op.drop_table('users')
    op.drop_table('settings')
    with op.batch_alter_table('provider_connections', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_provider_connections_workspace_id'))

    op.drop_table('provider_connections')
    op.drop_table('workspaces')
    with op.batch_alter_table('jobs', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_jobs_type'))
        batch_op.drop_index(batch_op.f('ix_jobs_status'))

    op.drop_table('jobs')
