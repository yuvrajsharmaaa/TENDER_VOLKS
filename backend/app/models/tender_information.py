from datetime import datetime
from sqlalchemy import Column, String, Integer, Numeric, Boolean, Text, DateTime, func
from sqlalchemy.dialects.postgresql import ARRAY
from backend.app.db.session import Base

class TenderInformation(Base):
    """
    SQLAlchemy model representing the public.tender_information table.
    Matches the PostgreSQL schema exactly.
    """
    __tablename__ = "tender_information"

    # Primary Key and Foreign Identifiers
    id = Column(Integer, primary_key=True, autoincrement=True)
    tender_id = Column(Integer, nullable=False, unique=True, index=True)
    tender_name = Column(String(255), nullable=True)

    # Basic Information
    nit_number = Column(String(255), nullable=True)
    client = Column(String(255), nullable=True)
    department = Column(String(255), nullable=True)
    organization = Column(String(255), nullable=True)
    publish_date = Column(DateTime, nullable=True)
    pre_bid_meeting_date = Column(DateTime, nullable=True)
    bid_submission_start_date = Column(DateTime, nullable=True)
    bid_submission_end_date = Column(DateTime, nullable=True)
    bid_opening_date = Column(DateTime, nullable=True)

    # Pricing
    emd_amount = Column(Numeric, nullable=True)
    tender_fee = Column(Numeric, nullable=True)
    estimated_cost = Column(Numeric, nullable=True)
    security_deposit = Column(Numeric, nullable=True)

    # Eligibility
    technical_experience = Column(Text, nullable=True)
    financial_turnover = Column(Numeric, nullable=True)
    certifications_required = Column(String(255), nullable=True)
    oem_authorization = Column(String(255), nullable=True)

    # Technical Requirements
    technical_specifications_summary = Column(Text, nullable=True)
    required_products_quantities = Column(Text, nullable=True)
    compliance_schedule = Column(Text, nullable=True)

    # Checklist Documents
    pan_card_proof = Column(String(255), nullable=True)
    gst_registration_certificate = Column(String(255), nullable=True)
    turnover_audited_balance_sheets = Column(String(255), nullable=True)
    experience_certificates = Column(String(255), nullable=True)

    # Contacts
    contact_person = Column(String(255), nullable=True)
    email = Column(String(255), nullable=True)
    phone = Column(String(255), nullable=True)
    address = Column(Text, nullable=True)

    # Delivery and Address
    work_delivery_location = Column(Text, nullable=True)
    physical_submission_address = Column(Text, nullable=True)

    # Risk / Commercial Terms
    liquidated_damages_percentage = Column(Numeric, nullable=True)
    maximum_ld_cap = Column(Numeric, nullable=True)
    warranty_period = Column(Integer, nullable=True)
    blacklisting_clauses = Column(Text, nullable=True)

    # Existing columns that are not in the CSV_COLUMNS of export.py (to preserve other functionality)
    te_recommendation = Column(String(255), nullable=True)
    emd_required = Column(String(255), nullable=True)
    bid_validity_days = Column(Integer, nullable=True)
    commercial_evaluation = Column(String(255), nullable=True)
    maf_required = Column(String(255), nullable=True)
    delivery_time_supply = Column(Integer, nullable=True)
    delivery_time_installation_days = Column(Integer, nullable=True)
    pbg_percentage = Column(Numeric, nullable=True)
    pbg_duration = Column(Integer, nullable=True)
    sd_duration = Column(Integer, nullable=True)
    max_ld_percentage = Column(Numeric, nullable=True)  # Note: kept for backward compatibility, but we now use maximum_ld_cap
    physical_docs_required = Column(String(255), nullable=True)
    physical_docs_deadline = Column(DateTime, nullable=True)

    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    te_rejection_reason = Column(Integer, nullable=True)
    te_rejection_remarks = Column(Text, nullable=True)
    tender_fee_amount = Column(Numeric, nullable=True)  # Note: kept for backward compatibility, but we now use tender_fee

    # Array fields (_text)
    tender_fee_mode = Column(ARRAY(String), nullable=True)
    emd_mode = Column(ARRAY(String), nullable=True)

    reverse_auction_applicable = Column(String(255), nullable=True)
    payment_terms_supply = Column(Numeric, nullable=True)
    payment_terms_installation = Column(Numeric, nullable=True)
    sd_percentage = Column(Numeric, nullable=True)
    ld_percentage_per_week = Column(Numeric, nullable=True)  # Note: kept for backward compatibility, but we now use liquidated_damages_percentage
    technical_eligibility_age = Column(Integer, nullable=True)
    order_value_1 = Column(Numeric, nullable=True)
    order_value_2 = Column(Numeric, nullable=True)
    order_value_3 = Column(Numeric, nullable=True)
    avg_annual_turnover_value = Column(Numeric, nullable=True)
    working_capital_value = Column(Numeric, nullable=True)
    solvency_certificate_value = Column(Numeric, nullable=True)
    net_worth_value = Column(Numeric, nullable=True)
    avg_annual_turnover_type = Column(Text, nullable=True)
    processing_fee_amount = Column(Numeric, nullable=True)
    processing_fee_mode = Column(ARRAY(String), nullable=True)
    delivery_time_installation_inclusive = Column(Boolean, nullable=True)
    pbg_required = Column(String(255), nullable=True)
    sd_required = Column(String(255), nullable=True)
    working_capital_type = Column(String(255), nullable=True)
    solvency_certificate_type = Column(String(255), nullable=True)
    net_worth_type = Column(String(255), nullable=True)
    courier_address = Column(Text, nullable=True)
    te_final_remark = Column(Text, nullable=True)
    processing_fee_required = Column(String(255), nullable=True)
    tender_fee_required = Column(String(255), nullable=True)
    pbg_mode = Column(Text, nullable=True)
    sd_mode = Column(Text, nullable=True)
    ld_required = Column(String(255), nullable=True)
    work_value_type = Column(String(255), nullable=True)
    custom_eligibility_criteria = Column(Text, nullable=True)
    oem_experience = Column(String(255), nullable=True)
    physical_docs_type = Column(String(255), nullable=True)
    te_rejection_proof = Column(ARRAY(String), nullable=True)
    physical_doc_type = Column(String(255), nullable=True)
    courier_pincode = Column(String(255), nullable=True)
    courier_state = Column(String(255), nullable=True)
    courier_city = Column(String(255), nullable=True)
    courier_address_line_2 = Column(Text, nullable=True)
    courier_address_line_1 = Column(Text, nullable=True)
    courier_phone = Column(String(255), nullable=True)
    courier_name = Column(String(255), nullable=True)
    client_details_present = Column(String(255), nullable=True)
    customer_in_contact = Column(String(255), nullable=True)
    courier_details_present = Column(String(255), nullable=True)