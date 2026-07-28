"""
GAIL Master Contract & ATC Concept Alias Definitions
Ground Truth Reference: GAIL General Conditions of Contract (GCC-Goods Rev.1, April 2022)
http://gailonline.com/pdf/gcc/GCC-GoodsRev1.pdf
"""

from typing import Dict, List

ATC_CLAUSE_ALIASES: Dict[str, List[str]] = {
    "security_deposit": [
        "Contract Performance Security",
        "CPS",
        "Security Deposit",
        "CPS/SD",
        "Contract Performance Security/ Security Deposit",
        "Performance Bank Guarantee",
        "PBG",
        "Contract Performance Guarantee",
        "CPBG"
    ],
    "price_reduction_ld": [
        "Price Reduction Schedule",
        "PRS",
        "Price Reduction Schedule (PRS) for Delayed Delivery",
        "Liquidated Damages",
        "LD",
        "PRS FOR DELAYED DELIVERY"
    ],
    "payment_terms": [
        "Terms of Payment",
        "Payment Terms",
        "TERMS OF PAYMENT",
        "PAYMENT TERMS",
        "Mode of Payment"
    ],
    "maf_bec": [
        "Manufacturer Authorization Form",
        "MAF",
        "OEM Authorization Certificate",
        "Authorized Dealer",
        "Authorized Partner/ Distributor",
        "Manufacturer Authorization"
    ],
    "courier_address": [
        "Dealing GAIL's Office Address",
        "GAIL's Office Address",
        "Office Address",
        "Address for Submission of Physical Documents",
        "Cut-Out Slip",
        "Consignee Address",
        "Owner's Address"
    ],
    "client_contacts": [
        "Nodal Officer",
        "Tender Dealing Officer",
        "Contact Details of Tender Dealing Officer",
        "Designated Authority",
        "Contact Details of Nodal Officer"
    ]
}
