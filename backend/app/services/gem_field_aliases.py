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
        "Percentage (%)"
    ],
    "pbg_duration": [
        "PBG Duration (Months)",
        "pbg_duration_months",
        "pbg_duration",
        "Duration of ePBG required",
        "Duration of ePBG"
    ],
    "eligibility_criterion_years": [
        "Eligibility Criterion (Years)",
        "Eligibility Criterion",
        "Years of Experience",
        "Minimum Experience (Years)",
        "Bidder Turnover",
        "Experience Criteria",
        "Experience Required",
        "Past Performance"
    ],
    "bid_validity": [
        "Bid Validity (Days)",
        "Bid Validity Period",
        "Bid Validity Days",
        "Bid Validity",
        "Validity of Offer"
    ],
    "emd_amount": [
        "EMD Amount",
        "Earnest Money Deposit",
        "EMD Detail",
        "EMD"
    ],
    "tender_title": [
        "Tender Name / Title",
        "Tender Name",
        "item_category",
        "similar_category",
        "Bid Title",
        "Item Title"
    ],
    "nit_number": [
        "Reference ID / NIT No",
        "bid_number",
        "tender_id",
        "Tender No",
        "Bid Number",
        "NIT No"
    ]
}
