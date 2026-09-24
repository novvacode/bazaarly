"""menu and faq

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-24 17:41:30.284614

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '0003'
down_revision: Union[str, Sequence[str], None] = '0002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('faq_entries',
    sa.Column('tenant_id', sa.Uuid(), nullable=False),
    sa.Column('question', sa.Text(), nullable=False),
    sa.Column('answer', sa.Text(), nullable=False),
    sa.Column('position', sa.Integer(), server_default='0', nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], name=op.f('fk_faq_entries_tenant_id_tenants'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_faq_entries'))
    )
    op.create_index('ix_faq_entries_tenant_position', 'faq_entries', ['tenant_id', 'position'], unique=False)
    op.create_table('menu_categories',
    sa.Column('tenant_id', sa.Uuid(), nullable=False),
    sa.Column('name', sa.Text(), nullable=False),
    sa.Column('position', sa.Integer(), server_default='0', nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], name=op.f('fk_menu_categories_tenant_id_tenants'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_menu_categories'))
    )
    op.create_index('ix_menu_categories_tenant_position', 'menu_categories', ['tenant_id', 'position'], unique=False)
    op.create_table('menu_items',
    sa.Column('tenant_id', sa.Uuid(), nullable=False),
    sa.Column('category_id', sa.Uuid(), nullable=True),
    sa.Column('name', sa.Text(), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('price_paise', sa.Integer(), nullable=False),
    sa.Column('image_url', sa.Text(), nullable=True),
    sa.Column('is_available', sa.Boolean(), server_default=sa.text('true'), nullable=False),
    sa.Column('is_veg', sa.Boolean(), server_default=sa.text('true'), nullable=False),
    sa.Column('tags', postgresql.ARRAY(sa.Text()), server_default=sa.text("'{}'"), nullable=False),
    sa.Column('position', sa.Integer(), server_default='0', nullable=False),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('price_paise > 0', name=op.f('ck_menu_items_price_positive')),
    sa.ForeignKeyConstraint(['category_id'], ['menu_categories.id'], name=op.f('fk_menu_items_category_id_menu_categories'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], name=op.f('fk_menu_items_tenant_id_tenants'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_menu_items'))
    )
    op.create_index('ix_menu_items_tenant_category_position', 'menu_items', ['tenant_id', 'category_id', 'position'], unique=False)
    op.create_index(op.f('ix_menu_items_tenant_id'), 'menu_items', ['tenant_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_menu_items_tenant_id'), table_name='menu_items')
    op.drop_index('ix_menu_items_tenant_category_position', table_name='menu_items')
    op.drop_table('menu_items')
    op.drop_index('ix_menu_categories_tenant_position', table_name='menu_categories')
    op.drop_table('menu_categories')
    op.drop_index('ix_faq_entries_tenant_position', table_name='faq_entries')
    op.drop_table('faq_entries')
