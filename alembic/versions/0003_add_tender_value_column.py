"""add tender_value column to tender_information

Revision ID: 0003_add_tender_value
Revises: 0002_tender_outcomes
Create Date: 2026-08-27 13:33:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '0003_add_tender_value'
down_revision: Union[str, Sequence[str], None] = '0002_tender_outcomes'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    # Add tender_value column to tender_information table
    op.add_column('tender_information', sa.Column('tender_value', sa.Numeric(), nullable=True))

def downgrade() -> None:
    op.drop_column('tender_information', 'tender_value')
