import sys
from pathlib import Path
import pytest

# Add scripts directory to path to import tender_extractr
sys.path.append(str(Path(__file__).resolve().parent.parent.parent / "scripts"))
import tender_extractr

def test_payment_terms_extraction():
    text = "Payment terms: 90% payment on delivery, 10% payment against installation and commissioning as per Cl.no.11 of Section-III (ITB)."
    res = tender_extractr.extract_payment_terms(text)
    assert "90%" in res["payment_terms_supply_pct"]
    assert "10%" in res["payment_terms_installation_pct"]
    assert res["payment_terms_raw_clause"] == "Cl.no.11 of Section-III (ITB)"

    # Single milestone case
    text_100 = "Payment shall be 100% payment on delivery."
    res_100 = tender_extractr.extract_payment_terms(text_100)
    assert "100%" in res_100["payment_terms_supply_pct"]
    assert res_100["payment_terms_installation_pct"] == tender_extractr.NOT_FOUND

def test_ld_extraction():
    text = "Liquidated Damages: 0.5% of contract value per week or part thereof, up to a maximum limit of 10% of contract value, as per Clause 9.2 GCC."
    res = tender_extractr.extract_ld(text)
    assert res["ld_applicable"] == "Yes"
    assert "0.5%" in res["ld_percentage_per_week"]
    assert "10%" in res["ld_max_percentage"]
    assert res["ld_clause_reference"] == "Clause 9.2"

def test_eligibility_extraction():
    # Word years and percentages
    text = "Bidder must have three years experience in similar nature of works. 1 similar work of 80% estimated value, 2 works of 50%, or 3 works of 40%."
    res = tender_extractr.extract_eligibility(text)
    assert "three years" in res["eligibility_criterion_years"]
    assert "80%" in res["eligibility_works_value_1"]
    assert "50%" in res["eligibility_works_value_2"]
    assert "40%" in res["eligibility_works_value_3"]

    # Absolute values
    text_abs = "One similar work of Rs. 40 Lakhs or two similar works of Rs. 25 Lakhs."
    res_abs = tender_extractr.extract_eligibility(text_abs)
    assert "Rs. 40 Lakhs" in res_abs["eligibility_works_value_1"]
    assert "Rs. 25 Lakhs" in res_abs["eligibility_works_value_2"]

def test_financials_extraction():
    text = "Average Annual Turnover of both Bidder and OEM should be 30% of estimated cost."
    res = tender_extractr.extract_financials(text)
    assert res["avg_annual_turnover_type"] == "Both"
    assert "30%" in res["avg_annual_turnover_value"]

    text_capital = "Working Capital of Bidder must be Rs. 10 Lakh."
    res_capital = tender_extractr.extract_financials(text_capital)
    assert res_capital["working_capital_type"] == "Bidder"
    assert "Rs. 10 Lakh" in res_capital["working_capital_value"]

def test_security_deposit_extraction():
    text = "ePBG shall be submitted in lieu of Security Deposit/Performance security."
    res = tender_extractr.extract_security_deposit(text)
    assert res["security_deposit_required"] == "Not Applicable - ePBG in lieu"

    text_sd = "Security Deposit shall be 3% of order value and valid for 12 months."
    res_sd = tender_extractr.extract_security_deposit(text_sd)
    assert res_sd["security_deposit_required"] == "Yes"
    assert "3%" in res_sd["security_deposit_pct"]
    assert "12 months" in res_sd["security_deposit_duration_months"]

def test_courier_and_physical_docs_extraction():
    # Valid address
    text = "Original documents must be sent to: Deputy General Manager (C&P), GAIL (India) Ltd, GAIL Bhawan, Sector 15, Noida, Uttar Pradesh, phone 0120-2441234, pincode 201301 within 7 days."
    res = tender_extractr.extract_courier_info(text)
    assert res["physical_docs_required"] == "Yes"
    assert res["courier_pincode"] == "201301"
    assert res["courier_phone"] == "0120-2441234"
    assert "Deputy General Manager" in res["courier_name"]
    assert "GAIL (India) Ltd" in res["courier_address_line1"]
    assert "Noida" in res["courier_city"]
    assert "Uttar Pradesh" in res["courier_state"]

    # False-positive boilerplate instructions (should be set to NOT_FOUND)
    text_fp = "Physical documents: hard copy of original EMD instrument to be sent within 7 days to the following address, pincode 530012."
    res_fp = tender_extractr.extract_courier_info(text_fp)
    assert res_fp["physical_docs_required"] == "Yes"
    assert res_fp["courier_pincode"] == "530012"
    assert res_fp["courier_name"] == tender_extractr.NOT_FOUND
    assert res_fp["courier_address_line1"] == tender_extractr.NOT_FOUND

def test_client_contacts_extraction():
    text = "Contact Person: Nodal Officer Mr. Rajesh Kumar, Phone: 9876543210. Also Contact Consignee Uppada V Prasad Reddy, Extn: 885-380."
    res = tender_extractr.extract_client_contacts(text)
    # Deduplicated by name (and designations prefix cleaned)
    names = [c["name"] for c in res]
    assert "Rajesh Kumar" in names
    assert "Uppada V Prasad Reddy" in names
    
    rajesh = next(c for c in res if "Rajesh" in c["name"])
    assert rajesh["designation"] == "Nodal Officer"
    assert rajesh["phone_or_extension"] == "9876543210"

    uppada = next(c for c in res if "Uppada" in c["name"])
    assert uppada["designation"] == "Consignee"
    assert uppada["phone_or_extension"] == "Extn: 885-380"
