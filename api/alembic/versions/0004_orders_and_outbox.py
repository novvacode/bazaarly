"""orders and outbox

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-24 17:52:43.511985

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '0004'
down_revision: Union[str, Sequence[str], None] = '0003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('outbox',
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('job_type', sa.Text(), nullable=False),
    sa.Column('payload', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('idempotency_key', sa.Text(), nullable=False),
    sa.Column('run_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('published_at', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_outbox'))
    )
    op.create_index('ix_outbox_unpublished', 'outbox', ['id'], unique=False, postgresql_where='published_at IS NULL')
    op.create_table('orders',
    sa.Column('tenant_id', sa.Uuid(), nullable=False),
    sa.Column('code', sa.Integer(), nullable=False),
    sa.Column('public_token', sa.Text(), nullable=False),
    sa.Column('idempotency_key', sa.Text(), nullable=False),
    sa.Column('customer_name', sa.Text(), nullable=False),
    sa.Column('customer_phone', sa.Text(), nullable=False),
    sa.Column('customer_email', sa.Text(), nullable=True),
    sa.Column('fulfillment_mode', sa.Enum('pickup', 'delivery', name='fulfillment_mode'), nullable=False),
    sa.Column('delivery_address', sa.Text(), nullable=True),
    sa.Column('delivery_area', sa.Text(), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('status', sa.Enum('pending_payment', 'placed', 'confirmed', 'preparing', 'ready', 'out_for_delivery', 'completed', 'cancelled', name='order_status'), nullable=False),
    sa.Column('payment_method', sa.Enum('online', 'cod', name='payment_method'), nullable=False),
    sa.Column('payment_status', sa.Enum('pending', 'paid', 'failed', 'refunded', name='payment_status'), nullable=False),
    sa.Column('subtotal_paise', sa.Integer(), nullable=False),
    sa.Column('delivery_fee_paise', sa.Integer(), nullable=False),
    sa.Column('total_paise', sa.Integer(), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], name=op.f('fk_orders_tenant_id_tenants'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_orders')),
    sa.UniqueConstraint('public_token', name=op.f('uq_orders_public_token')),
    sa.UniqueConstraint('tenant_id', 'code', name=op.f('uq_orders_tenant_id_code')),
    sa.UniqueConstraint('tenant_id', 'idempotency_key', name=op.f('uq_orders_tenant_id_idempotency_key'))
    )
    op.create_index('ix_orders_tenant_created', 'orders', ['tenant_id', 'created_at', 'id'], unique=False)
    op.create_index('ix_orders_tenant_status', 'orders', ['tenant_id', 'status'], unique=False)
    op.create_table('order_status_events',
    sa.Column('order_id', sa.Uuid(), nullable=False),
    sa.Column('from_status', postgresql.ENUM('pending_payment', 'placed', 'confirmed', 'preparing', 'ready', 'out_for_delivery', 'completed', 'cancelled', name='order_status', create_type=False), nullable=True),
    sa.Column('to_status', postgresql.ENUM('pending_payment', 'placed', 'confirmed', 'preparing', 'ready', 'out_for_delivery', 'completed', 'cancelled', name='order_status', create_type=False), nullable=False),
    sa.Column('actor_user_id', sa.Uuid(), nullable=True),
    sa.Column('note', sa.Text(), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['actor_user_id'], ['users.id'], name=op.f('fk_order_status_events_actor_user_id_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['order_id'], ['orders.id'], name=op.f('fk_order_status_events_order_id_orders'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_order_status_events'))
    )
    op.create_index(op.f('ix_order_status_events_order_id'), 'order_status_events', ['order_id'], unique=False)
    op.create_table('order_items',
    sa.Column('order_id', sa.Uuid(), nullable=False),
    sa.Column('menu_item_id', sa.Uuid(), nullable=True),
    sa.Column('name_snapshot', sa.Text(), nullable=False),
    sa.Column('unit_price_paise', sa.Integer(), nullable=False),
    sa.Column('quantity', sa.Integer(), nullable=False),
    sa.Column('line_total_paise', sa.Integer(), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('quantity BETWEEN 1 AND 50', name=op.f('ck_order_items_quantity_range')),
    sa.ForeignKeyConstraint(['menu_item_id'], ['menu_items.id'], name=op.f('fk_order_items_menu_item_id_menu_items'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['order_id'], ['orders.id'], name=op.f('fk_order_items_order_id_orders'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_order_items'))
    )
    op.create_index(op.f('ix_order_items_order_id'), 'order_items', ['order_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_order_items_order_id'), table_name='order_items')
    op.drop_table('order_items')
    op.drop_index(op.f('ix_order_status_events_order_id'), table_name='order_status_events')
    op.drop_table('order_status_events')
    op.drop_index('ix_orders_tenant_status', table_name='orders')
    op.drop_index('ix_orders_tenant_created', table_name='orders')
    op.drop_table('orders')
    op.drop_index('ix_outbox_unpublished', table_name='outbox', postgresql_where='published_at IS NULL')
    op.drop_table('outbox')
    for name in ('order_status', 'fulfillment_mode', 'payment_method', 'payment_status'):
        sa.Enum(name=name).drop(op.get_bind(), checkfirst=True)
