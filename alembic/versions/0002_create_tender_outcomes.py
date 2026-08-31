"""create tender_outcomes table

Revision ID: 0002_tender_outcomes
Revises: 0001_initial_baseline
Create Date: 2026-08-27 13:26:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '0002_tender_outcomes'
down_revision: Union[str, Sequence[str], None] = '0001_initial_baseline'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    op.create_table(
        'tender_outcomes',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('tender_no', sa.String(length=255), nullable=False),
        sa.Column('tender_id', sa.Integer(), sa.ForeignKey('tender_information.tender_id', ondelete='SET NULL'), nullable=True),
        sa.Column('outcome', sa.String(length=50), nullable=False),
        sa.Column('label_source', sa.String(length=100), nullable=False, server_default='outcome_labels_review_xlsx'),
        sa.Column('split_status', sa.String(length=50), nullable=False, server_default='not_applicable'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False)
    )
    op.create_index(op.f('ix_tender_outcomes_tender_no'), 'tender_outcomes', ['tender_no'], unique=True)
    op.create_index(op.f('ix_tender_outcomes_tender_id'), 'tender_outcomes', ['tender_id'], unique=False)
    op.create_index(op.f('ix_tender_outcomes_outcome'), 'tender_outcomes', ['outcome'], unique=False)

def downgrade() -> None:
    op.drop_index(op.f('ix_tender_outcomes_outcome'), table_name='tender_outcomes')
    op.drop_index(op.f('ix_tender_outcomes_tender_id'), table_name='tender_outcomes')
    op.drop_index(op.f('ix_tender_outcomes_tender_no'), table_name='tender_outcomes')
    op.drop_table('tender_outcomes')
