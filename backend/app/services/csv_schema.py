# central csv schema definition for universal tender extraction sheet
# this schema defines column types and logical ordering suitable for DictWriter

# ==============================================================================
# Helper Columns (Not stored directly in tender_information, used for tracking)
# ==============================================================================
HELPER_COLUMNS = [
    "document_source_format",  # [helper] Identifies document origin format (e.g. GeM, CPPP, Custom)
    "extracted_by_version"     # [helper] Tracks version of extraction engine
]

# ==============================================================================
# DB-Mapped Columns (Maps 1-to-1 with public.tender_information columns)
# ==============================================================================

# 1. Document Tracking Columns
DOCUMENT_TRACKING_COLUMNS = [
    "id",                      # [auto / serial] DB Primary Key
    "tender_id",               # [auto / bigint] Internal DB foreign key tracking tender document ID
]

# 2. Tender Identity Columns
TENDER_IDENTITY_COLUMNS = [
    "tender_value"             # [auto / numeric] Estimated contract value/tender value
]

# 3. Bid Timing Columns
BID_TIMING_COLUMNS = [
    "bid_validity_days",       # [auto / int4] Offer validity days
    "physical_docs_deadline"   # [auto / timestamp] Deadline to submit paper documents offline
]

# 4. Commercial & Financial Columns
COMMERCIAL_FINANCIAL_COLUMNS = [
    "emd_amount",              # [auto / numeric] EMD security deposit amount
    "emd_mode",                # [derived / text[]] Multi-value array of accepted EMD instruments
    "tender_fee_amount",       # [auto / numeric] Tender purchase fee amount
    "tender_fee_mode",         # [derived / text[]] Accepted payment instruments for tender fee
    "processing_fee_amount",   # [auto / numeric] Portal processing transactional fee
    "processing_fee_mode",     # [derived / text[]] Accepted payment instruments for processing fee
    "pbg_percentage",          # [auto / numeric] Performance Bank Guarantee rate percentage
    "pbg_duration",            # [auto / int4] Performance Security duration in months
    "pbg_mode",                # [auto / text] Allowed instrument format for PBG
    "sd_percentage",           # [auto / numeric] Security Deposit / Retention rate percentage
    "sd_duration",             # [auto / int4] Defect liability period duration in months
    "sd_mode",                 # [auto / text] Allowed instrument format for Security Deposit
    "ld_percentage_per_week",  # [auto / numeric] Liquidated Damages penalty rate per week of delay
    "max_ld_percentage"        # [auto / numeric] Total ceiling cap on Liquidated Damages penalties
]

# 5. Eligibility Columns
ELIGIBILITY_COLUMNS = [
    "maf_required",            # [derived / varchar] Yes/No flag for Manufacturer Authorization Form
    "technical_eligibility_age",# [auto / int4] Minimum years of bidder corporate experience
    "oem_experience",          # [auto / varchar] Specific experience requirements binding on the OEM
    "avg_annual_turnover_value",# [auto / numeric] Bidder or OEM average annual turnover requirement value
    "avg_annual_turnover_type", # [auto / text] Target of the turnover constraint (Bidder vs OEM)
    "working_capital_value",   # [auto / numeric] Required liquidity or working capital limit
    "working_capital_type",    # [auto / varchar] Document format to prove working capital
    "solvency_certificate_value",# [auto / numeric] Bank solvency letter value constraint
    "solvency_certificate_type",# [auto / varchar] Tier of bank required to issue solvency letter
    "net_worth_value",         # [auto / numeric] Minimum net worth threshold required
    "net_worth_type",          # [auto / varchar] Certified net worth standards
    "order_value_1",           # [auto / numeric] Value of single similar completed work required (80%)
    "order_value_2",           # [auto / numeric] Value of two similar completed works required (50%)
    "order_value_3",           # [auto / numeric] Value of three similar completed works required (40%)
    "work_value_type",         # [auto / varchar] Classification tag defining similar work categories
    "custom_eligibility_criteria"# [auto / text] General pre-qualification text blocks
]

# 6. Delivery & Service Columns
DELIVERY_SERVICE_COLUMNS = [
    "delivery_time_supply",    # [auto / int4] Delivery window in days for materials supply
    "delivery_time_installation_days", # [auto / int4] Site setup/commissioning window in days
    "delivery_time_installation_inclusive", # [auto / bool] If installation days are inside supply days
    "payment_terms_supply",    # [auto / numeric] Percentage of payment released on material supply
    "payment_terms_installation" # [auto / numeric] Percentage of payment released on commissioning
]

# 7. Consignee & Courier Columns
CONSIGNEE_COURIER_COLUMNS = [
    "courier_name",            # [auto / varchar] Designated recipient name for offline bids
    "courier_phone",           # [auto / varchar] Contact number of receiving officer
    "courier_address",         # [auto / text] Full address block for offline envelope delivery
    "courier_address_line_1",  # [derived / text] Split first segment of destination address
    "courier_address_line_2",  # [derived / text] Split second segment of destination address
    "courier_city",            # [auto / varchar] Resolved destination city
    "courier_state",           # [auto / varchar] Resolved destination state
    "courier_pincode"          # [derived / varchar] Extracted 6-digit postal pincode
]

# 8. Derived Flags Columns
DERIVED_FLAGS_COLUMNS = [
    "emd_required",            # [derived / varchar] Yes/No EMD required status
    "tender_fee_required",     # [derived / varchar] Yes/No Tender Fee required status
    "processing_fee_required", # [derived / varchar] Yes/No Portal Processing Fee required status
    "pbg_required",            # [derived / varchar] Yes/No Performance Bank Guarantee required status
    "sd_required",             # [derived / varchar] Yes/No Security Deposit required status
    "ld_required",             # [derived / varchar] Yes/No Liquidated Damages applicability
    "physical_docs_required",  # [derived / varchar] Yes/No offline paper submission required
    "physical_doc_type",       # [auto / varchar] Classification of physical submission items
    "physical_docs_type",      # [auto / varchar] Mapping fallback array
    "client_details_present",  # [derived / varchar] Yes/No client organisation detected
    "courier_details_present", # [derived / varchar] Yes/No delivery address detected
    "reverse_auction_applicable" # [auto / varchar] Yes/No/NA Reverse Auction status
]

# 9. Manual Review Columns (Initialized to Null, Audited Later by Evaluator)
MANUAL_REVIEW_COLUMNS = [
    "te_recommendation",       # [manual / varchar] Technical evaluator verdict (Accept/Reject)
    "te_rejection_reason",     # [manual / int4] Standardized disqualification reason code
    "te_rejection_remarks",    # [manual / text] Explanatory notes by assessor
    "te_rejection_proof",      # [manual / _text] Document URLs proving disqualification
    "te_final_remark",         # [manual / text] Technical compliance summary note
    "customer_in_contact",     # [manual / varchar] Yes/No CRM sales flag
    "commercial_evaluation"    # [manual / varchar] Financial L1/L2 rank assigned after opening
]

# 10. System Audit Columns
SYSTEM_AUDIT_COLUMNS = [
    "created_at",              # [helper / timestamp] DB creation stamp
    "updated_at"               # [helper / timestamp] DB edit stamp
]

# ==============================================================================
# Complete Sheet Ordering (Combines helpers + database payload layout)
# ==============================================================================
CSV_COLUMNS = (
    DOCUMENT_TRACKING_COLUMNS +
    TENDER_IDENTITY_COLUMNS +
    BID_TIMING_COLUMNS +
    COMMERCIAL_FINANCIAL_COLUMNS +
    ELIGIBILITY_COLUMNS +
    DELIVERY_SERVICE_COLUMNS +
    CONSIGNEE_COURIER_COLUMNS +
    DERIVED_FLAGS_COLUMNS +
    MANUAL_REVIEW_COLUMNS +
    SYSTEM_AUDIT_COLUMNS +
    HELPER_COLUMNS
)

# Minimal columns subset for simple validations
MINIMAL_MVP_CSV_COLUMNS = [
    "tender_id",
    "tender_value",
    "bid_validity_days",
    "emd_required",
    "emd_amount",
    "emd_mode",
    "tender_fee_amount",
    "pbg_required",
    "pbg_percentage",
    "pbg_duration",
    "maf_required",
    "technical_eligibility_age",
    "avg_annual_turnover_value",
    "order_value_1",
    "order_value_2",
    "order_value_3",
    "delivery_time_supply",
    "physical_docs_required",
    "physical_docs_deadline",
    "courier_address",
    "courier_pincode",
    "te_recommendation",
    "te_rejection_remarks",
    "te_final_remark"
]
