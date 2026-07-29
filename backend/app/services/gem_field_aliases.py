"""
GeM Platform Standard Bid Document (GEM_DOC) Concept Alias Definitions
Ground Truth Reference: GeM Standard Bid Document Layouts (Goods / Services / Works)
"""

from typing import Dict, List

MAIN_FIELD_ALIASES: Dict[str, List[str]] = {
    "pbg_percentage": [
        "PBG Percentage",
        "ePBG Percentage",
        "ePBG Detail",
        "Performance Bank Guarantee",
        "PBG %",
        "Percentage (%)",
        "pbg_percentage_display"
    ],
    "pbg_duration": [
        "PBG Duration (Months)",
        "pbg_duration_months",
        "pbg_duration",
        "Duration of ePBG required",
        "Duration of ePBG",
        "pbg_duration_display"
    ],
    "pbg_mode": [
        "PBG Mode",
        "pbg_mode",
        "pbg_mode_display"
    ],
    "sd_percentage": [
        "Security Deposit %",
        "Security Deposit Percentage",
        "SD Percentage",
        "sd_percentage",
        "sd_percentage_display"
    ],
    "sd_duration": [
        "Security Deposit Duration",
        "SD Duration (Months)",
        "sd_duration",
        "sd_duration_display"
    ],
    "sd_mode": [
        "Security Deposit Mode",
        "SD Mode",
        "sd_mode",
        "sd_mode_display"
    ],
    "payment_terms_supply": [
        "Payment Terms Supply (%)",
        "Payment Terms Supply",
        "payment_terms_supply",
        "payment_terms_supply_percent",
        "payment_terms_supply_display"
    ],
    "payment_terms_installation": [
        "Payment Terms Installation (%)",
        "Payment Terms Installation",
        "payment_terms_installation",
        "payment_terms_installation_percent",
        "payment_terms_installation_display"
    ],
    "delivery_time_supply": [
        "Delivery Time Supply (Days)",
        "Delivery Time Supply",
        "delivery_time_supply",
        "delivery_time_supply_days",
        "delivery_time_supply_display"
    ],
    "delivery_time_installation": [
        "Delivery Time Installation (Days)",
        "Delivery Time Installation",
        "delivery_time_installation",
        "delivery_time_installation_days",
        "delivery_time_installation_display"
    ],
    "eligibility_criterion_years": [
        "Eligibility Criterion (Years)",
        "Eligibility Criterion",
        "Years of Experience",
        "Minimum Experience (Years)",
        "Bidder Turnover",
        "Experience Criteria",
        "Experience Required",
        "Past Performance",
        "eligibility_criterion_years"
    ],
    "bid_validity": [
        "Bid Validity (Days)",
        "Bid Validity Period",
        "Bid Validity Days",
        "Bid Validity",
        "Validity of Offer",
        "bid_validity_days"
    ],
    "emd_amount": [
        "EMD Amount",
        "Earnest Money Deposit",
        "EMD Detail",
        "EMD",
        "emd_amount",
        "emd_amount_display"
    ],
    "emd_mode": [
        "EMD Mode",
        "emd_mode",
        "emd_mode_display"
    ],
    "tender_title": [
        "Tender Name / Title",
        "Tender Name",
        "item_category",
        "similar_category",
        "Bid Title",
        "Item Title",
        "tender_name"
    ],
    "nit_number": [
        "Reference ID / NIT No",
        "bid_number",
        "tender_id",
        "Tender No",
        "Bid Number",
        "NIT No",
        "tender_id_display"
    ],
    "client_name_1": [
        "Client Contact Person",
        "Client Name 1",
        "client_name_1",
        "client_contact_person",
        "Nodal Officer",
        "client_name_1_display"
    ],
    "client_email_1": [
        "Client Email",
        "Client Email 1",
        "client_email_1",
        "client_email",
        "client_email_1_display"
    ],
    "client_phone_1": [
        "Client Phone",
        "Client Phone 1",
        "client_phone_1",
        "client_phone",
        "client_phone_1_display"
    ],
    "courier_address": [
        "Courier Address",
        "courier_address",
        "full_courier_address_with_pincode",
        "courier_address_display"
    ],
    "custom_eligibility_criteria": [
        "Custom Eligibility Criteria",
        "custom_eligibility_criteria",
        "custom_eligibility_criteria_display"
    ]
}
