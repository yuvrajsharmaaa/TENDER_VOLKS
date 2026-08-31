"""initial baseline migration

Revision ID: 0001_initial_baseline
Revises: 
Create Date: 2026-08-27 13:25:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '0001_initial_baseline'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    # 1. tender_projects
    op.create_table(
        'tender_projects',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('project_id', sa.String(length=255), nullable=False),
        sa.Column('tender_name', sa.String(length=255), nullable=True),
        sa.Column('source_label', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False)
    )
    op.create_index(op.f('ix_tender_projects_project_id'), 'tender_projects', ['project_id'], unique=False)

    # 2. documents
    op.create_table(
        'documents',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('tender_project_id', sa.String(length=36), sa.ForeignKey('tender_projects.id', ondelete='CASCADE'), nullable=False),
        sa.Column('original_filename', sa.String(length=255), nullable=False),
        sa.Column('storage_bucket', sa.String(length=255), nullable=False),
        sa.Column('storage_key', sa.String(length=512), nullable=False),
        sa.Column('mime_type', sa.String(length=100), nullable=False),
        sa.Column('size_bytes', sa.Integer(), nullable=False),
        sa.Column('upload_status', sa.String(length=50), nullable=False, server_default='uploaded'),
        sa.Column('processing_status', sa.String(length=50), nullable=False, server_default='pending'),
        sa.Column('document_type', sa.String(length=100), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False)
    )
    op.create_index(op.f('ix_documents_tender_project_id'), 'documents', ['tender_project_id'], unique=False)

    # 3. jobs
    op.create_table(
        'jobs',
        sa.Column('job_id', sa.String(length=36), primary_key=True),
        sa.Column('status', sa.String(length=50), nullable=False, server_default='pending'),
        sa.Column('original_filename', sa.String(length=255), nullable=True),
        sa.Column('file_path', sa.String(length=512), nullable=True),
        sa.Column('pdf_path', sa.String(length=512), nullable=True),
        sa.Column('result_path', sa.String(length=512), nullable=True),
        sa.Column('page_count', sa.Integer(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('retry_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('email_recipient', sa.String(length=255), nullable=True),
        sa.Column('tender_id', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=False)
    )
    op.create_index(op.f('ix_jobs_created_at'), 'jobs', ['created_at'], unique=False)
    op.create_index(op.f('ix_jobs_status'), 'jobs', ['status'], unique=False)

    # 4. tender_information
    op.create_table(
        'tender_information',
        sa.Column('id', sa.Integer(), autoincrement=True, primary_key=True),
        sa.Column('tender_id', sa.Integer(), nullable=False),
        sa.Column('tender_name', sa.String(length=255), nullable=True),
        sa.Column('nit_number', sa.String(length=255), nullable=True),
        sa.Column('client', sa.String(length=255), nullable=True),
        sa.Column('department', sa.String(length=255), nullable=True),
        sa.Column('organization', sa.String(length=255), nullable=True),
        sa.Column('publish_date', sa.DateTime(), nullable=True),
        sa.Column('pre_bid_meeting_date', sa.DateTime(), nullable=True),
        sa.Column('bid_submission_start_date', sa.DateTime(), nullable=True),
        sa.Column('bid_submission_end_date', sa.DateTime(), nullable=True),
        sa.Column('bid_opening_date', sa.DateTime(), nullable=True),
        sa.Column('emd_amount', sa.Numeric(), nullable=True),
        sa.Column('tender_fee', sa.Numeric(), nullable=True),
        sa.Column('estimated_cost', sa.Numeric(), nullable=True),
        sa.Column('security_deposit', sa.Numeric(), nullable=True),


        sa.Column('technical_experience', sa.Text(), nullable=True),
        sa.Column('financial_turnover', sa.Numeric(), nullable=True),
        sa.Column('certifications_required', sa.String(length=255), nullable=True),
        sa.Column('oem_authorization', sa.String(length=255), nullable=True),
        sa.Column('technical_specifications_summary', sa.Text(), nullable=True),
        sa.Column('required_products_quantities', sa.Text(), nullable=True),
        sa.Column('compliance_schedule', sa.Text(), nullable=True),
        sa.Column('pan_card_proof', sa.String(length=255), nullable=True),
        sa.Column('gst_registration_certificate', sa.String(length=255), nullable=True),
        sa.Column('turnover_audited_balance_sheets', sa.String(length=255), nullable=True),
        sa.Column('experience_certificates', sa.String(length=255), nullable=True),
        sa.Column('contact_person', sa.String(length=255), nullable=True),
        sa.Column('email', sa.String(length=255), nullable=True),
        sa.Column('phone', sa.String(length=255), nullable=True),
        sa.Column('address', sa.Text(), nullable=True),
        sa.Column('work_delivery_location', sa.Text(), nullable=True),
        sa.Column('physical_submission_address', sa.Text(), nullable=True),
        sa.Column('liquidated_damages_percentage', sa.Numeric(), nullable=True),
        sa.Column('maximum_ld_cap', sa.Numeric(), nullable=True),
        sa.Column('warranty_period', sa.Integer(), nullable=True),
        sa.Column('blacklisting_clauses', sa.Text(), nullable=True),
        sa.Column('te_recommendation', sa.String(length=255), nullable=True),
        sa.Column('emd_required', sa.String(length=255), nullable=True),
        sa.Column('bid_validity_days', sa.Integer(), nullable=True),
        sa.Column('commercial_evaluation', sa.String(length=255), nullable=True),
        sa.Column('maf_required', sa.String(length=255), nullable=True),
        sa.Column('delivery_time_supply', sa.Integer(), nullable=True),
        sa.Column('delivery_time_installation_days', sa.Integer(), nullable=True),
        sa.Column('pbg_percentage', sa.Numeric(), nullable=True),
        sa.Column('pbg_duration', sa.Integer(), nullable=True),
        sa.Column('sd_duration', sa.Integer(), nullable=True),
        sa.Column('max_ld_percentage', sa.Numeric(), nullable=True),
        sa.Column('physical_docs_required', sa.String(length=255), nullable=True),
        sa.Column('physical_docs_deadline', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('te_rejection_reason', sa.Integer(), nullable=True),
        sa.Column('te_rejection_remarks', sa.Text(), nullable=True),
        sa.Column('tender_fee_amount', sa.Numeric(), nullable=True),
        sa.Column('tender_fee_mode', postgresql.ARRAY(sa.String()), nullable=True),
        sa.Column('emd_mode', postgresql.ARRAY(sa.String()), nullable=True),
        sa.Column('reverse_auction_applicable', sa.String(length=255), nullable=True),
        sa.Column('payment_terms_supply', sa.Numeric(), nullable=True),
        sa.Column('payment_terms_installation', sa.Numeric(), nullable=True),
        sa.Column('sd_percentage', sa.Numeric(), nullable=True),
        sa.Column('ld_percentage_per_week', sa.Numeric(), nullable=True),
        sa.Column('technical_eligibility_age', sa.Integer(), nullable=True),
        sa.Column('order_value_1', sa.Numeric(), nullable=True),
        sa.Column('order_value_2', sa.Numeric(), nullable=True),
        sa.Column('order_value_3', sa.Numeric(), nullable=True),
        sa.Column('avg_annual_turnover_value', sa.Numeric(), nullable=True),
        sa.Column('working_capital_value', sa.Numeric(), nullable=True),
        sa.Column('solvency_certificate_value', sa.Numeric(), nullable=True),
        sa.Column('net_worth_value', sa.Numeric(), nullable=True),
        sa.Column('avg_annual_turnover_type', sa.Text(), nullable=True),
        sa.Column('processing_fee_amount', sa.Numeric(), nullable=True),
        sa.Column('processing_fee_mode', postgresql.ARRAY(sa.String()), nullable=True),
        sa.Column('delivery_time_installation_inclusive', sa.Boolean(), nullable=True),
        sa.Column('pbg_required', sa.String(length=255), nullable=True),
        sa.Column('sd_required', sa.String(length=255), nullable=True),
        sa.Column('working_capital_type', sa.String(length=255), nullable=True),
        sa.Column('solvency_certificate_type', sa.String(length=255), nullable=True),
        sa.Column('net_worth_type', sa.String(length=255), nullable=True),
        sa.Column('courier_address', sa.Text(), nullable=True),
        sa.Column('te_final_remark', sa.Text(), nullable=True),
        sa.Column('processing_fee_required', sa.String(length=255), nullable=True),
        sa.Column('tender_fee_required', sa.String(length=255), nullable=True),
        sa.Column('pbg_mode', sa.Text(), nullable=True),
        sa.Column('sd_mode', sa.Text(), nullable=True),
        sa.Column('ld_required', sa.String(length=255), nullable=True),
        sa.Column('work_value_type', sa.String(length=255), nullable=True),
        sa.Column('custom_eligibility_criteria', sa.Text(), nullable=True),
        sa.Column('oem_experience', sa.String(length=255), nullable=True),
        sa.Column('physical_docs_type', sa.String(length=255), nullable=True),
        sa.Column('te_rejection_proof', postgresql.ARRAY(sa.String()), nullable=True),
        sa.Column('physical_doc_type', sa.String(length=255), nullable=True),
        sa.Column('courier_pincode', sa.String(length=255), nullable=True),
        sa.Column('courier_state', sa.String(length=255), nullable=True),
        sa.Column('courier_city', sa.String(length=255), nullable=True),
        sa.Column('courier_address_line_2', sa.Text(), nullable=True),
        sa.Column('courier_address_line_1', sa.Text(), nullable=True),
        sa.Column('courier_phone', sa.String(length=255), nullable=True),
        sa.Column('courier_name', sa.String(length=255), nullable=True),
        sa.Column('client_details_present', sa.String(length=255), nullable=True),
        sa.Column('customer_in_contact', sa.String(length=255), nullable=True),
        sa.Column('courier_details_present', sa.String(length=255), nullable=True)
    )
    op.create_index(op.f('ix_tender_information_tender_id'), 'tender_information', ['tender_id'], unique=True)

def downgrade() -> None:
    op.drop_table('tender_information')
    op.drop_table('jobs')
    op.drop_table('documents')
    op.drop_table('tender_projects')
