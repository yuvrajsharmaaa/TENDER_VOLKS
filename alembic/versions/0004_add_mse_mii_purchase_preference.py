"""add mse_purchase_preference and mii_purchase_preference columns

Revision ID: 0004_mse_mii_preference
Revises: 0003_add_tender_value
Create Date: 2026-09-03 08:30:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '0004_mse_mii_preference'
down_revision: Union[str, Sequence[str], None] = '0003_add_tender_value'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    # Add mse_purchase_preference and mii_purchase_preference columns to tender_information table
    op.add_column('tender_information', sa.Column('mse_purchase_preference', sa.Boolean(), nullable=True))
    op.add_column('tender_information', sa.Column('mii_purchase_preference', sa.Boolean(), nullable=True))

def downgrade() -> None:
    op.drop_column('tender_information', 'mii_purchase_preference')
    op.drop_column('tender_information', 'mse_purchase_preference')
