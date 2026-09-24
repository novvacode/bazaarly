"""assistant knowledge base and logs

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-24 18:23:14.519181

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
import pgvector.sqlalchemy

# revision identifiers, used by Alembic.
revision: str = '0006'
down_revision: Union[str, Sequence[str], None] = '0005'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('assistant_logs',
    sa.Column('tenant_id', sa.Uuid(), nullable=False),
    sa.Column('session_id', sa.Text(), nullable=False),
    sa.Column('question', sa.Text(), nullable=False),
    sa.Column('answer', sa.Text(), nullable=False),
    sa.Column('answered', sa.Boolean(), nullable=False),
    sa.Column('retrieved_chunk_ids', postgresql.ARRAY(sa.Uuid()), nullable=False),
    sa.Column('top_score', sa.REAL(), nullable=True),
    sa.Column('latency_ms', sa.Integer(), nullable=False),
    sa.Column('model', sa.Text(), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], name=op.f('fk_assistant_logs_tenant_id_tenants'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_assistant_logs'))
    )
    op.create_index('ix_assistant_logs_tenant_created', 'assistant_logs', ['tenant_id', 'created_at', 'id'], unique=False)
    op.create_table('kb_chunks',
    sa.Column('tenant_id', sa.Uuid(), nullable=False),
    sa.Column('source_type', sa.Enum('business_info', 'menu_item', 'faq', name='kb_source_type'), nullable=False),
    sa.Column('source_id', sa.Uuid(), nullable=False),
    sa.Column('title', sa.Text(), nullable=False),
    sa.Column('content', sa.Text(), nullable=False),
    sa.Column('content_hash', sa.Text(), nullable=False),
    sa.Column('embedding', pgvector.sqlalchemy.vector.VECTOR(dim=384), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], name=op.f('fk_kb_chunks_tenant_id_tenants'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_kb_chunks')),
    sa.UniqueConstraint('source_type', 'source_id', name=op.f('uq_kb_chunks_source_type_source_id'))
    )
    op.create_index('ix_kb_chunks_embedding_hnsw', 'kb_chunks', ['embedding'], unique=False, postgresql_using='hnsw', postgresql_ops={'embedding': 'vector_cosine_ops'})
    op.create_index(op.f('ix_kb_chunks_tenant_id'), 'kb_chunks', ['tenant_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_kb_chunks_tenant_id'), table_name='kb_chunks')
    op.drop_index('ix_kb_chunks_embedding_hnsw', table_name='kb_chunks', postgresql_using='hnsw', postgresql_ops={'embedding': 'vector_cosine_ops'})
    op.drop_table('kb_chunks')
    sa.Enum(name='kb_source_type').drop(op.get_bind(), checkfirst=True)
    op.drop_index('ix_assistant_logs_tenant_created', table_name='assistant_logs')
    op.drop_table('assistant_logs')
