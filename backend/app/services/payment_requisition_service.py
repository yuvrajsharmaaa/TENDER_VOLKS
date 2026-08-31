import os
import re
import io
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List
from jinja2 import Environment, FileSystemLoader
from pydantic import BaseModel, Field
from xhtml2pdf import pisa

logger = logging.getLogger(__name__)
ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent
TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"

# ─────────────────────────────────────────────────────────────────────────────
# Requisition Schemas & Exceptions
# ─────────────────────────────────────────────────────────────────────────────

class PaymentRequisitionInput(BaseModel):
    tender_no: str
    organization: str
    tender_title: str
    requisition_amount: Any  # float, int, or "Not Found" / None
    submission_deadline: Any
    beneficiary_name: Optional[str] = None
    payment_purpose: str = "Earnest Money Deposit (EMD)"
    payment_mode: str = "Bank Guarantee / RTGS"
    advisory_bank: Optional[str] = "State Bank of India / ICICI Bank"
    estimated_value: Optional[str] = "As per NIT"
    pbg_requirement: Optional[str] = "3% of contract value"
    exemption_status: Optional[str] = "Not Applicable (Non-MSE)"
    recommendation: Optional[str] = "bid"
    win_probability: Optional[float] = 0.50
    confidence: Optional[float] = 0.85


class IncompleteRequisitionError(Exception):
    """Raised when strict mode is active and mandatory payment fields are missing."""
    pass


# ─────────────────────────────────────────────────────────────────────────────
# Helper: Number to Indian Words
# ─────────────────────────────────────────────────────────────────────────────

def number_to_indian_words(num: float) -> str:
    """Converts a numerical amount into Indian currency words."""
    try:
        num = float(num)
        if num == 0:
            return "Zero"
        
        crores = int(num // 10000000)
        remainder = num % 10000000
        lakhs = int(remainder // 100000)
        remainder = remainder % 100000
        thousands = int(remainder // 1000)
        remainder = remainder % 1000
        hundreds = int(remainder // 100)
        units = int(remainder % 100)

        ones_map = ["", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine",
                    "Ten", "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen", "Sixteen",
                    "Seventeen", "Eighteen", "Nineteen"]
        tens_map = ["", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety"]

        def two_digits(n):
            if n < 20:
                return ones_map[n]
            return tens_map[n // 10] + (" " + ones_map[n % 10] if n % 10 != 0 else "")

        parts = []
        if crores > 0:
            parts.append(f"{two_digits(crores)} Crore")
        if lakhs > 0:
            parts.append(f"{two_digits(lakhs)} Lakh")
        if thousands > 0:
            parts.append(f"{two_digits(thousands)} Thousand")
        if hundreds > 0:
            parts.append(f"{ones_map[hundreds]} Hundred")
        if units > 0:
            parts.append(two_digits(units))

        return " ".join(parts).strip()
    except Exception:
        return "Amount in Words"


# ─────────────────────────────────────────────────────────────────────────────
# Payment Requisition PDF Service
# ─────────────────────────────────────────────────────────────────────────────

class PaymentRequisitionService:
    """
    Renders official, audit-ready Payment Requisition PDFs using Jinja2 and xhtml2pdf / reportlab.
    Enforces strict field completeness checks and missing-field alert banners.
    """

    MISSING_VALUES = {"not found", "none", "null", "undefined", "⚠️ missing", "missing", "", "0", "0.0", "0.00"}

    def __init__(self, templates_dir: Optional[Path] = None):
        self.templates_dir = templates_dir or TEMPLATES_DIR
        self.env = Environment(loader=FileSystemLoader(str(self.templates_dir)))
        self.output_dir = ROOT_DIR / "artifacts" / "payment_requisitions"
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate_requisition_pdf(
        self,
        req_data: PaymentRequisitionInput,
        output_filepath: Optional[Path] = None,
        strict: bool = False
    ) -> bytes:
        """
        Generates payment requisition PDF bytes and optionally saves to disk.
        If strict is True, raises IncompleteRequisitionError if mandatory fields are missing.
        """
        missing_fields = []

        # 1. Check Amount
        amt_raw = str(req_data.requisition_amount or "").strip()
        is_amount_missing = (not amt_raw) or (amt_raw.lower() in self.MISSING_VALUES)
        amount_val = 0.0
        if is_amount_missing:
            missing_fields.append("Requisition Amount (EMD / Tender Fee)")
        else:
            try:
                # Remove currency symbols and commas
                clean_amt = re.sub(r"[^\d.]", "", amt_raw)
                amount_val = float(clean_amt)
                if amount_val <= 0:
                    is_amount_missing = True
                    missing_fields.append("Requisition Amount (Zero or Invalid)")
            except ValueError:
                is_amount_missing = True
                missing_fields.append("Requisition Amount (Invalid Format)")

        # 2. Check Submission Deadline
        deadline_raw = str(req_data.submission_deadline or "").strip()
        is_deadline_missing = (not deadline_raw) or (deadline_raw.lower() in self.MISSING_VALUES)
        if is_deadline_missing:
            missing_fields.append("Submission / Payment Deadline")

        # 3. Check Beneficiary Name
        bene_raw = str(req_data.beneficiary_name or "").strip()
        is_beneficiary_missing = (not bene_raw) or (bene_raw.lower() in self.MISSING_VALUES)
        if is_beneficiary_missing:
            missing_fields.append("Beneficiary / Payee Name")

        # Strict Gate Enforcement
        if strict and len(missing_fields) > 0:
            err_msg = (
                f"[REQUISITION_BLOCKED] Cannot generate payment requisition for '{req_data.tender_no}'. "
                f"Mandatory payment fields missing: {missing_fields}."
            )
            logger.error(err_msg)
            raise IncompleteRequisitionError(err_msg)

        # Build Template Context
        req_id = re.sub(r"[^\w]", "", req_data.tender_no)[-8:].upper()
        context = {
            "tender_no": req_data.tender_no,
            "organization": req_data.organization,
            "tender_title": req_data.tender_title,
            "requisition_date": datetime.now().strftime("%d-%b-%Y"),
            "req_id": req_id,
            "missing_fields": missing_fields,
            "is_amount_missing": is_amount_missing,
            "formatted_amount": f"{amount_val:,.2f}" if not is_amount_missing else "",
            "amount_in_words": number_to_indian_words(amount_val) if not is_amount_missing else "",
            "is_deadline_missing": is_deadline_missing,
            "submission_deadline": deadline_raw if not is_deadline_missing else "",
            "is_beneficiary_missing": is_beneficiary_missing,
            "beneficiary_name": bene_raw if not is_beneficiary_missing else "As per GeM Portal / Client Account",
            "payment_purpose": req_data.payment_purpose,
            "payment_mode": req_data.payment_mode,
            "advisory_bank": req_data.advisory_bank or "State Bank of India",
            "estimated_value": req_data.estimated_value or "As per NIT",
            "pbg_requirement": req_data.pbg_requirement or "3%",
            "exemption_status": req_data.exemption_status or "Not Applicable",
            "recommendation": req_data.recommendation or "bid",
            "win_probability": req_data.win_probability or 0.5,
            "confidence": req_data.confidence or 0.85
        }

        # Render HTML
        template = self.env.get_template("payment_requisition.html")
        html_content = template.render(**context)

        # Render PDF via xhtml2pdf
        pdf_buffer = io.BytesIO()
        pisa_status = pisa.CreatePDF(
            src=io.StringIO(html_content),
            dest=pdf_buffer,
            encoding="utf-8"
        )

        if pisa_status.err:
            raise RuntimeError(f"xhtml2pdf rendering failed with error code: {pisa_status.err}")

        pdf_bytes = pdf_buffer.getvalue()

        # Save to disk if requested or in default artifacts folder
        safe_t_no = re.sub(r"[^\w\-]", "_", req_data.tender_no)
        target_path = output_filepath or (self.output_dir / f"payment_requisition_{safe_t_no}.pdf")
        with open(target_path, "wb") as f:
            f.write(pdf_bytes)

        logger.info(
            "[PaymentRequisition] Successfully generated PDF for %s at %s (%d bytes)",
            req_data.tender_no, target_path, len(pdf_bytes)
        )
        return pdf_bytes
